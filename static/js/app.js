import { metricFields, divisionFields } from "./constants.js";
import { uiState } from "./state.js";
import { getJSON, postJSON } from "./api.js";
import { performAction, bindAction, formatBytes, escapeHTML, fillOptions, table } from "./ui.js";
import { renderAccountDetail } from "./views/accounts.js";
import { renderCreatorDetail, renderSavedCreators, renderCreatorOptions, closeCreatorMenu } from "./views/creators.js";
import { renderVideos, lookupSingleVideo } from "./views/videos.js";
import { updatePlotControls, renderPlot, setupPlot, syncPlotControls } from "./views/plots.js";
import { renderAnalysis, setupAnalysis } from "./views/analysis.js";
import { runAction } from "./progress.js";
import { enableLiveReload } from "./dev_reload.js";

async function load() {
  const [health, creators, plots, accounts] = await Promise.all([
    getJSON("/api/health"),
    getJSON("/api/creators"),
    getJSON("/api/plots"),
    getJSON("/api/accounts")
  ]);

  document.getElementById("status").textContent =
    `${health.account} | ${health.request_frequency} requests/s`;

  const selected = health.selected_creator;
  uiState.selectedCreator = selected;
  uiState.savedCreators = creators.creators;
  renderSavedCreators();

  document.getElementById("plots").innerHTML = `<div class="saved-plots-grid">${plots.plots.map((plot) => `
    <article class="saved-plot">
      <a href="${escapeHTML(plot.url)}" target="_blank" rel="noreferrer"><img src="${escapeHTML(plot.url)}" alt="${escapeHTML(plot.name)}"></a>
      <footer>
        <span>${escapeHTML(plot.name)}</span>
        <span>${formatBytes(plot.size)}</span>
      </footer>
    </article>
  `).join("") || `<p class="muted">No saved plots.</p>`}</div>`;
  document.getElementById("accounts-result").innerHTML = table(
    ["Name", "UID", "Source", "Active", "Action"],
    accounts.accounts.map((account) => [
      account.name,
      account.uid,
      account.source,
      account.active ? "Yes" : "No",
      `<button type="button" data-account="${escapeHTML(account.id)}">Select</button>`
    ]),
    true
  );
  document.querySelectorAll("button[data-account]").forEach((button) => {
    button.addEventListener("click", () => performAction(button, async () => {
      await postJSON("/api/account/select", { id: button.dataset.account });
      await load();
    }));
  });
}

const panelSections = { creators: "explore", creator: "explore", "single-video": "explore", videos: "workspace", analysis: "workspace", division: "workspace", plot: "workspace", "saved-plots": "workspace", settings: "settings" };
const lastPanel = { explore: "creators", workspace: "videos", settings: "settings" };
const sectionCopy = {
  explore: ["SEARCH · DISCOVER", "Explore", "Get to know a creator or inspect a single video before working with a dataset."],
  workspace: ["COLLECT · UNDERSTAND · COMPARE", "Workspace", "One dataset, several ways to explore it. Fetch once, then work locally."],
  settings: ["ACCOUNT · CONNECTION", "Settings", "Manage your account, sign-in options, and request frequency."]
};

const menuHistory = [];
const panelLabels = { creators: "Creators", creator: "Creator profile", "single-video": "Single video", videos: "Dataset", analysis: "Statistics", division: "Ratios", plot: "Charts", "saved-plots": "Saved charts", settings: "Settings" };

function selectPanel(name, { remember = true } = {}) {
  const panel = document.getElementById(`panel-${name}`);
  if (!panel) return;
  const current = document.querySelector("main").dataset.activePanel;
  if (remember && current && current !== name) menuHistory.push(current);
  const back = document.getElementById("menu-back");
  back.hidden = menuHistory.length === 0;
  back.textContent = `← Back to ${panelLabels[menuHistory.at(-1)] || "previous view"}`;
  document.getElementById("menu-back-hint").hidden = back.hidden;
  const section = panelSections[name];
  lastPanel[section] = name;
  document.getElementById("open-library").hidden = ["creators", "settings", "single-video", "saved-plots"].includes(name);
  document.querySelector(".creator-switcher").hidden = document.getElementById("open-library").hidden;
  closeCreatorMenu();
  document.querySelectorAll(".panel").forEach(item => item.classList.toggle("active", item === panel));
  document.querySelector(".selection-card").hidden = !["videos", "analysis", "division", "plot"].includes(name);
  document.querySelectorAll("[data-tools]").forEach(nav => { nav.hidden = nav.dataset.tools !== section; });
  document.querySelectorAll("button[data-section], button[data-panel]").forEach(button => {
    const active = button.dataset.section ? button.dataset.section === section : button.dataset.panel === name;
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  const [eyebrow, title, description] = sectionCopy[section];
  document.getElementById("section-eyebrow").textContent = eyebrow;
  document.getElementById("section-title").textContent = title;
  document.getElementById("section-description").textContent = description;
  document.querySelector("main").dataset.activePanel = name;
}

function setup() {
  setupPlot(load);
  setupAnalysis();
  ["metric-field", "plot-field", "analysis-field"].forEach((id) => fillOptions(id, metricFields));
  ["division-numerator", "division-denominator", "plot-numerator", "plot-denominator"].forEach((id) => fillOptions(id, divisionFields));
  document.querySelectorAll("button[data-panel]").forEach((button) => {
    button.addEventListener("click", () => selectPanel(button.dataset.panel));
  });
  document.querySelectorAll("button[data-section]").forEach(button => {
    button.addEventListener("click", () => selectPanel(lastPanel[button.dataset.section]));
  });
  selectPanel("videos");
  const menu = document.getElementById("creator-menu");
  document.getElementById("open-library").addEventListener("click", () => {
    if (!menu.hidden) return closeCreatorMenu({ restoreFocus: true });
    document.getElementById("creator-menu-feedback").hidden = true;
    menu.hidden = false;
    document.getElementById("open-library").setAttribute("aria-expanded", "true");
    document.getElementById("creator-search").focus();
  });
  document.getElementById("creator-search").addEventListener("input", renderCreatorOptions);
  document.getElementById("manage-creators").addEventListener("click", () => {
    selectPanel("creators");
    document.getElementById("add-creator-form").open = true;
    document.getElementById("new-creator-name").focus();
  });
  const goBack = () => {
    if (uiState.actionBusy || !menuHistory.length) return;
    selectPanel(menuHistory.pop(), { remember: false });
  };
  document.getElementById("menu-back").addEventListener("click", goBack);
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && !menu.hidden) closeCreatorMenu({ restoreFocus: true });
  });
  document.addEventListener("click", event => {
    if (!(event.target instanceof Element)) return;
    if (!menu.hidden && !event.target.closest(".creator-switcher")) {
      closeCreatorMenu();
      return;
    }
    if (window.getSelection()?.toString() || uiState.actionBusy) return;
    // Only bare layout surfaces count as blank; controls, charts and results do not.
    if (event.target.matches("body, main, .work, .workspace-heading, .panel, .page-heading, .tool-nav, .main-nav")) goBack();
  });
  const emptyMessages = {
    "creator-detail-result": "No profile loaded.", "single-video-result": "No video loaded.",
    "videos-result": "No videos loaded.", "analysis-result": "No analysis yet.",
    "division-result": "No ratios calculated.", "plot-result": "No plot generated.",
    "account-result": "No account detail loaded."
  };
  Object.entries(emptyMessages).forEach(([id, message]) => {
    document.getElementById(id).innerHTML = `<p class="empty-state">${message}</p>`;
  });
  document.querySelectorAll(".result").forEach((element) => {
    element.tabIndex = 0;
    element.setAttribute("aria-label", element.id.replaceAll("-", " "));
  });
  const updateFilterSummary = () => {
    const minimum = document.getElementById("local-min-views").value;
    const maximum = document.getElementById("local-max-views").value;
    document.getElementById("filter-summary").textContent = minimum || maximum
      ? `· Views ${minimum || "0"}–${maximum || "unlimited"} · run a tool to apply`
      : "· All fetched rows";
  };
  ["local-min-views", "local-max-views"].forEach(id => {
    document.getElementById(id).addEventListener("input", updateFilterSummary);
    document.getElementById(id).addEventListener("change", updateFilterSummary);
  });
  document.getElementById("creator-library-search").addEventListener("input", renderSavedCreators);
  document.getElementById("plot-mode").addEventListener("change", updatePlotControls);
  updatePlotControls();
  document.getElementById("selection-kind").addEventListener("change", (event) => {
    document.getElementById("selection-position").hidden = event.target.value !== "position";
    document.getElementById("selection-published").hidden = event.target.value !== "published";
    document.getElementById("selection-metric").hidden = event.target.value !== "metric";
  });
  bindAction("add-creator", async () => {
    await postJSON("/api/creators/add", {
      name: document.getElementById("new-creator-name").value,
      space: document.getElementById("new-creator-space").value
    });
    await load();
  });
  bindAction("lookup-single-video", lookupSingleVideo);
  document.getElementById("single-video-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter") document.getElementById("lookup-single-video").click();
  });
  bindAction("fetch-dataset", async () => {
    const data = await runAction("list", { refresh: true });
    renderVideos("videos-result", data.videos);
    document.getElementById("dataset-source").open = false;
    selectPanel("videos");
  });
  bindAction("list-videos", async () => {
    const data = await runAction("list");
    renderVideos("videos-result", data.videos);
  });
  bindAction("run-analysis", async () => {
    const data = await runAction("analysis");
    renderAnalysis(data);
  });
  bindAction("run-division", async () => {
    const data = await runAction("division", {
      mode: document.getElementById("division-mode").value,
      numerator: document.getElementById("division-numerator").value,
      denominator: document.getElementById("division-denominator").value
    });
    if (data.mode === "aggregate") {
      document.getElementById("division-result").innerHTML = table(["Numerator", "Denominator", "Ratio", "Eligible", "Excluded"], [[data.numerator_total, data.denominator_total, data.ratio, data.eligible_count, data.excluded_count]]);
    } else {
      document.getElementById("division-result").innerHTML = table(
        ["Title", "Published", "Numerator", "Denominator", "Ratio"],
        data.rows.map((row) => [row.title, row.published_time, row.numerator, row.denominator, row.ratio])
      );
    }
  });
  bindAction("run-plot", async () => {
    const data = await runAction("plot", {
      plot_mode: document.getElementById("plot-mode").value,
      field: document.getElementById("plot-field").value,
      numerator: document.getElementById("plot-numerator").value,
      denominator: document.getElementById("plot-denominator").value
    }, "plot-progress");
    renderPlot(data);
    document.getElementById("plot-result").innerHTML = table(["Title", "Published", "Value"], data.points.map((point) => [point.title, point.label, point.value]));
    document.getElementById("plot-data-label").textContent = `Data (${data.points.length.toLocaleString()} videos)`;
  }, syncPlotControls);
  bindAction("load-account", async () => {
    renderAccountDetail(await getJSON("/api/account-detail"));
  });
  bindAction("use-guest", async () => {
    await postJSON("/api/sign-out", { mode: "keep" });
    await load();
  });
  bindAction("sign-out-keep", async () => {
    await postJSON("/api/sign-out", { mode: "keep" });
    await load();
  });
  bindAction("sign-out-selected", async () => {
    await postJSON("/api/sign-out", { mode: "selected" });
    await load();
  });
  bindAction("sign-out-all", async () => {
    await postJSON("/api/sign-out", { mode: "all" });
    await load();
  });
  bindAction("set-frequency", async () => {
    await postJSON("/api/request-frequency", { value: document.getElementById("request-frequency").value });
    await load();
  });
  bindAction("start-qr", async () => {
    const data = await postJSON("/api/sign-in/qr/start", {});
    document.getElementById("qr-result").innerHTML = `<p class="muted">Scan this QR code with the Bilibili app, then click Check QR Status.</p><img src="${data.qr_code_url}?t=${Date.now()}" alt="Bilibili sign-in QR code">`;
  });
  bindAction("check-qr", async () => {
    const data = await postJSON("/api/sign-in/qr/status", {});
    document.getElementById("qr-result").innerHTML = table(["Field", "Value"], Object.entries(data).map(([key, value]) => [key, typeof value === "object" ? JSON.stringify(value) : value]));
    await load();
  });
  bindAction("load-creator-detail", async () => {
    renderCreatorDetail(await getJSON("/api/creator-detail"));
  });
}

setup();
enableLiveReload(load);
load().catch((error) => {
  document.getElementById("status").textContent = error.message;
});
