import { metricFields, divisionFields } from "./constants.js";
import { uiState } from "./state.js";
import { getJSON, postJSON } from "./api.js";
import { performAction, bindAction, formatBytes, escapeHTML, fillOptions, table } from "./ui.js";
import { renderAccountDetail } from "./views/accounts.js";
import { renderUPDetail, renderSavedUPs } from "./views/creators.js";
import { renderVideos, lookupSingleVideo } from "./views/videos.js";
import { updatePlotControls, renderPlot } from "./views/plots.js";
import { runAction } from "./progress.js";
import { enableLiveReload } from "./dev_reload.js";

async function load() {
  const [health, ups, plots, accounts] = await Promise.all([
    getJSON("/api/health"),
    getJSON("/api/ups"),
    getJSON("/api/plots"),
    getJSON("/api/accounts")
  ]);

  document.getElementById("status").textContent =
    `${health.account} | ${health.request_frequency} requests/s`;

  const selected = health.selected_up;
  uiState.selectedUP = selected;
  uiState.savedUPs = ups.ups;
  document.getElementById("selected").textContent = selected
    ? `${selected.name} (UID ${selected.uid})`
    : "No UP selected.";

  renderSavedUPs(load);

  document.getElementById("plots").innerHTML = `<div class="saved-plots-grid">${plots.plots.map((plot) => `
    <article class="saved-plot">
      <a href="${escapeHTML(plot.url)}" target="_blank" rel="noreferrer"><img src="${escapeHTML(plot.url)}" alt="${escapeHTML(plot.name)}"></a>
      <footer>
        <span>${escapeHTML(plot.name)}</span>
        <span>${formatBytes(plot.size)}</span>
      </footer>
    </article>
  `).join("") || `<p class="muted">No plots generated yet.</p>`}</div>`;
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

function selectPanel(name) {
  const panel = document.getElementById(`panel-${name}`);
  document.querySelectorAll(".panel").forEach((item) => item.classList.toggle("active", item === panel));
  const selection = document.querySelector(".selection-card");
  const slot = panel.querySelector(".selection-slot");
  selection.hidden = !slot;
  if (slot) slot.appendChild(selection);
  document.querySelector("main").classList.toggle("wide-mode", ["settings", "single-video", "saved-plots"].includes(name));
  document.querySelectorAll("button[data-panel]").forEach((button) => {
    if (button.dataset.panel === name) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
}

function setup() {
  ["metric-field", "plot-field"].forEach((id) => fillOptions(id, metricFields));
  ["division-numerator", "division-denominator", "plot-numerator", "plot-denominator"].forEach((id) => fillOptions(id, divisionFields));
  document.querySelectorAll("button[data-panel]").forEach((button) => {
    button.addEventListener("click", () => selectPanel(button.dataset.panel));
  });
  const compact = matchMedia("(max-width: 1050px)");
  const updateLibrary = () => { document.getElementById("up-picker").open = !compact.matches; };
  compact.addEventListener("change", updateLibrary);
  updateLibrary();
  const emptyMessages = {
    "up-detail-result": "No profile loaded.", "single-video-result": "No video loaded.",
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
  document.getElementById("up-search").addEventListener("input", () => renderSavedUPs(load));
  document.getElementById("plot-mode").addEventListener("change", updatePlotControls);
  updatePlotControls();
  document.getElementById("selection-kind").addEventListener("change", (event) => {
    document.getElementById("selection-position").hidden = event.target.value !== "position";
    document.getElementById("selection-published").hidden = event.target.value !== "published";
    document.getElementById("selection-metric").hidden = event.target.value !== "metric";
  });
  bindAction("add-up", async () => {
    await postJSON("/api/ups/add", {
      name: document.getElementById("new-up-name").value,
      space: document.getElementById("new-up-space").value
    });
    await load();
  });
  bindAction("lookup-single-video", lookupSingleVideo);
  document.getElementById("single-video-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter") document.getElementById("lookup-single-video").click();
  });
  bindAction("list-videos", async () => {
    const data = await runAction("list");
    renderVideos("videos-result", data.videos);
  });
  bindAction("run-analysis", async () => {
    const data = await runAction("analysis");
    document.getElementById("analysis-result").innerHTML = table(
      ["Metric", "Count", "Mean", "Median"],
      data.summaries.map((item) => [item.label, item.count, item.mean, item.median])
    );
  });
  bindAction("run-division", async () => {
    const data = await runAction("division", {
      mode: document.getElementById("division-mode").value,
      numerator: document.getElementById("division-numerator").value,
      denominator: document.getElementById("division-denominator").value
    });
    if (data.mode === "aggregate") {
      document.getElementById("division-result").innerHTML = table(["Numerator", "Denominator", "Ratio"], [[data.numerator_total, data.denominator_total, data.ratio]]);
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
    renderPlot(data.points, data.y_label || data.plot_label || "Value");
    const savedPlot = data.plot_file ? `<p class="muted">Saved PNG: ${escapeHTML(data.plot_file)}</p>` : "";
    document.getElementById("plot-result").innerHTML = savedPlot + table(["Title", "Published", "Value"], data.points.map((point) => [point.title, point.label, point.value]));
    await load();
  });
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
  bindAction("load-up-detail", async () => {
    renderUPDetail(await getJSON("/api/up-detail"));
  });
}

setup();
enableLiveReload(load);
load().catch((error) => {
  document.getElementById("status").textContent = error.message;
});
