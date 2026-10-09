import { setupSelects, closeSelectMenus } from "./selects.js";
import { metricFields, divisionFields } from "./constants.js";
import { uiState } from "./state.js";
import { getJSON, postJSON } from "./api.js";
import { performAction, bindAction, formatBytes, escapeHTML, fillOptions, table, preservePageHeight, setupPageHeight } from "./ui.js";
import { renderAccountDetail } from "./views/accounts.js";
import { renderCreatorDetail, renderSavedCreators, filterSavedCreators, renderCreatorOptions, closeCreatorMenu } from "./views/creators.js";
import { renderVideos, lookupSingleVideo } from "./views/videos.js";
import { updatePlotControls, renderPlot, setupPlot, syncPlotControls, resetPlot } from "./views/plots.js";
import { renderAnalysis, setupAnalysis, syncAnalysisControls, resetAnalysis } from "./views/analysis.js";
import { refreshCollections, setupCollections, renderAnalysisContext, recordDataset, chooseCollection } from './collections.js';
import { restoreSelection } from './selection.js';
import { runAction, startProgressPolling, stopProgressPolling } from "./progress.js";
import { setupBatch, updateBatchSummary, refreshBatch, configureBatch } from "./batch.js";
import { fetchWeekly, renderWeekly } from "./views/weekly.js";
import { fetchRandomSample, setupSampling, renderRandomSample } from "./views/sampling.js";
import { setupNodes, refreshNodes } from "./views/nodes.js";
import { setupTracking, refreshTracking, configureTracking } from "./views/tracking.js";
import { setupSnapshots, refreshSnapshots, configureSnapshots } from './views/snapshots.js';
import { refreshSnapshotChoices } from './snapshot-choice.js';
import { setupMemory, configureMemory } from './memory.js';

async function restoreFetchedData() {
  let data = await getJSON('/api/workspace-data');
  const render = () => {
    if (data.creator) {
      restoreSelection(data.creator.selection_controls);
      recordDataset(data.creator.dataset);
      renderVideos('videos-result', data.creator.videos);
      document.getElementById('dataset-source').open = false;
    }
    if (data.reports.weekly) renderWeekly(data.reports.weekly);
    if (data.reports.random) renderRandomSample(data.reports.random);
    updateBatchSummary();
  };
  render();
  if (!data.running) return;
  // The server owns a running fetch, so a tab refresh does not cancel it.
  await performAction(document.getElementById('fetch-dataset'), async () => {
    startProgressPolling('Reconnecting to the running collection', 'videos-progress');
    try {
      while (data.running) {
        await new Promise(resolve => setTimeout(resolve, 800));
        data.running = (await getJSON('/api/progress')).running;
      }
      data = await getJSON('/api/workspace-data');
      await refreshCollections();
      render();
    } finally {
      await stopProgressPolling();
    }
  }, { showProgress: false });
}

async function load({ restoreData = false } = {}) {
  const [health, creators, plots, accounts] = await Promise.all([
    getJSON("/api/health"),
    getJSON("/api/creators"),
    getJSON("/api/plots"),
    getJSON("/api/accounts")
  ]);

  document.getElementById("status").textContent =
    `${health.account} | ${health.request_frequency} requests/s`;

  uiState.requestFrequency = health.request_frequency;
  ["request-frequency", "dataset-request-frequency"].forEach(id => { document.getElementById(id).value = health.request_frequency; });
  document.getElementById("dataset-pacing-status").textContent = `Current pacing: ${health.request_frequency} requests/s for the next collection. Parallel work divides this rate across Macs; node caps may lower it.`;
  document.getElementById("fetch-source").dispatchEvent(new Event("change"));
  uiState.chartExportVersion = health.chart_export_version || 0;
  configureTracking(health.tracking_version || 0);
  configureSnapshots(health.dataset_snapshot_version || 0);
  configureBatch(health.mission_queue_version || 0);
  configureMemory(health.memory_usage_version || 0);
  await refreshSnapshotChoices();
  syncPlotControls();
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
  updateBatchSummary();
  if (health.collection_analysis_version >= 1) await refreshCollections();
  else document.getElementById('analysis-source-help').textContent = 'Restart the main dashboard to enable sampling collections in Analysis.';
  if (restoreData && health.workspace_restore_version >= 1) await restoreFetchedData();
  await refreshBatch();
}

const panelSections = { creators: "explore", creator: "explore", "single-video": "explore", videos: "workspace", snapshots: "workspace", tracking: "workspace", analysis: "workspace", division: "workspace", plot: "workspace", sampling: "workspace", tasks: "workspace", nodes: "workspace", "saved-plots": "workspace", anomalies: "workspace", settings: "settings" };
const workspaceGroups = { videos: "data", sampling: "data", snapshots: "data", tracking: "tracking", analysis: "analysis", division: "analysis", plot: "analysis", anomalies: "analysis", "saved-plots": "analysis", tasks: "tasks", nodes: "nodes" };
const lastGroupPanel = { data: "videos", tracking: "tracking", analysis: "analysis", tasks: "tasks", nodes: "nodes" };
const lastPanel = { explore: "creators", workspace: "videos", settings: "settings" };
const sectionCopy = {
  explore: ["SEARCH · DISCOVER", "Explore", "Get to know a creator or inspect a single video before working with a dataset."],
  workspace: ["COLLECT · UNDERSTAND · COMPARE", "Workspace", "One dataset, several ways to explore it. Fetch once, then work locally."],
  settings: ["ACCOUNT · CONNECTION", "Settings", "Manage your account, sign-in options, and request frequency."]
};

const menuHistory = [];
const panelLabels = { creators: "Creators", creator: "Creator profile", "single-video": "Single video", videos: "Dataset", snapshots: "Dataset snapshots", tracking: "Tracking", analysis: "Statistics", division: "Ratios", plot: "Charts", sampling: "Sampling", tasks: "Tasks", nodes: "Nodes", "saved-plots": "Saved charts", anomalies: "Unusual values", settings: "Settings" };

function selectPanel(name, { remember = true } = {}) {
  const panel = document.getElementById(`panel-${name}`);
  if (!panel) return;
  preservePageHeight();
  const current = document.querySelector("main").dataset.activePanel;
  if (remember && current && current !== name) menuHistory.push(current);
  const back = document.getElementById("menu-back");
  back.disabled = menuHistory.length === 0;
  back.textContent = back.disabled ? "← Back" : `← Back to ${panelLabels[menuHistory.at(-1)] || "previous view"}`;
  back.title = back.disabled ? "No previous page" : back.textContent;
  const section = panelSections[name];
  lastPanel[section] = name;
  const group = workspaceGroups[name];
  if (group) lastGroupPanel[group] = name;
  document.querySelectorAll("[data-workspace-tools]").forEach(nav => { nav.hidden = section !== "workspace" || nav.dataset.workspaceTools !== group; });
  document.getElementById("analysis-dataset-context").hidden = section !== "workspace" || group !== "analysis";
  closeCreatorMenu();
  const creatorContext = document.getElementById('creator-context');
  const creatorSlot = document.getElementById(name === 'creator' ? 'profile-creator-slot' : 'dataset-creator-slot');
  if (creatorContext.parentElement !== creatorSlot) creatorSlot.append(creatorContext);
  creatorContext.hidden = !['videos', 'creator'].includes(name);
  document.getElementById('creator-context-label').textContent = name === 'creator' ? 'Profile creator' : 'Dataset creator';
  closeSelectMenus();
  document.querySelectorAll(".panel").forEach(item => item.classList.toggle("active", item === panel));
  document.querySelector(".selection-card").hidden = name !== "videos";
  document.querySelectorAll("[data-tools]").forEach(nav => { nav.hidden = nav.dataset.tools !== section; });
  document.querySelector(".workspace-subtools").hidden = section !== "workspace" || !["data", "analysis"].includes(group);
  document.querySelectorAll("button[data-section], button[data-panel], button[data-group]").forEach(button => {
    const active = button.dataset.section ? button.dataset.section === section : button.dataset.group ? section === "workspace" && button.dataset.group === group : button.dataset.panel === name;
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  const [eyebrow, title, description] = sectionCopy[section];
  document.getElementById("section-eyebrow").textContent = eyebrow;
  document.getElementById("section-title").textContent = title;
  document.getElementById("section-description").textContent = group === 'tracking'
    ? 'Monitor releases and performance over time with independent schedules and video histories.' : description;
  document.querySelector("main").dataset.activePanel = name;
  if (name === "tasks") { updateBatchSummary(); refreshBatch().catch(error => { document.getElementById('batch-status').textContent = error.message; }); }
  if (name === "nodes") refreshNodes();
  if (name === "tracking") refreshTracking().catch(error => {
    document.getElementById('tracking-feedback').textContent = error.message;
  });
  if (name === 'snapshots') refreshSnapshots().catch(error => {
    document.getElementById('snapshot-feedback').textContent = error.message;
  });
}

function workspaceTasks() {
  const value = id => document.getElementById(id).value;
  return [
    { id: "fetch", label: "Fetch dataset", action: "list", extra: { refresh: true, collection_id: null,
      local_filter: { minimum_views: value('local-min-views'), maximum_views: value('local-max-views') } }, render(data) {
      renderVideos("videos-result", data.videos);
      document.getElementById("dataset-source").open = false;
    } },
    { id: "division", label: "Calculate ratios", action: "division", extra: {
      mode: value("division-mode"), numerator: value("division-numerator"), denominator: value("division-denominator")
    }, render(data) {
      document.getElementById("division-result").innerHTML = data.mode === "aggregate"
        ? table(["Numerator", "Denominator", "Ratio", "Eligible", "Excluded"], [[data.numerator_total, data.denominator_total, data.ratio, data.eligible_count, data.excluded_count]])
        : table(["Title", "Published", "Numerator", "Denominator", "Ratio"], data.rows.map(row => [row.title, row.published_time, row.numerator, row.denominator, row.ratio]));
    } },
    { id: "analysis", label: "Calculate statistics", action: "analysis", extra: {}, render: renderAnalysis },
    { id: "plot", label: "Generate chart", action: "plot", extra: {
      plot_mode: value("plot-mode"), field: value("plot-field"), numerator: value("plot-numerator"), denominator: value("plot-denominator")
    }, render(data) {
      renderPlot(data);
      document.getElementById("plot-result").innerHTML = table(["Title", "Published", "Value"], data.points.map(point => [point.title, point.label, point.value]));
      document.getElementById("plot-data-label").textContent = `Data (${data.points.length.toLocaleString()} videos)`;
    } }
  ];
}

async function executeWorkspaceTask(task, payload = {}, progressTarget = null) {
  const data = await runAction(task.action, { ...payload, ...task.extra }, progressTarget);
  task.render(data);
  return data;
}

function chooseCollectionForMission(mission, view) {
  chooseCollection(mission.collection_id);
  document.getElementById('analysis-min-views').value = mission.config.local_filter.minimum_views ?? '';
  document.getElementById('analysis-max-views').value = mission.config.local_filter.maximum_views ?? '';
  const action = view === 'analysis-result' ? 'analysis' : view;
  const report = view === 'analysis' ? null : mission.results[action];
  if (report) {
    recordDataset(report.dataset);
    for (const [key,id] of [['field','plot-field'],['plot_mode','plot-mode'],['plot_axis','plot-axis'],['numerator','plot-numerator'],['denominator','plot-denominator'],['numerator','division-numerator'],['denominator','division-denominator'],['mode','division-mode']]) {
      document.getElementById(id).value = mission.config[key];
      document.getElementById(id).dispatchEvent(new Event('change'));
    }
    workspaceTasks().find(task => task.action === action).render(report);
  }
  selectPanel(action === 'division' ? 'division' : action === 'plot' ? 'plot' : 'analysis');
  syncAnalysisControls();
  syncPlotControls();
}

function setup() {
  setupPageHeight();
  setupPlot(load);
  setupAnalysis();
  ["metric-field", "plot-field", "analysis-field"].forEach((id) => fillOptions(id, metricFields));
  ["division-numerator", "division-denominator", "plot-numerator", "plot-denominator"].forEach((id) => fillOptions(id, divisionFields));
  document.addEventListener('click', event => {
    const button = event.target.closest('button[data-panel]');
    if (button && !button.disabled) selectPanel(button.dataset.panel);
  });
  document.querySelectorAll("button[data-section]").forEach(button => {
    button.addEventListener("click", () => selectPanel(lastPanel[button.dataset.section]));
  });
  document.querySelectorAll("button[data-config-panel]").forEach(button => {
    button.addEventListener("click", () => selectPanel(button.dataset.configPanel));
  });
  document.querySelectorAll("button[data-group]").forEach(button => {
    button.addEventListener("click", () => selectPanel(lastGroupPanel[button.dataset.group]));
  });
  document.addEventListener('analysis-source-changed', () => {
    preservePageHeight();
    resetAnalysis();
    resetPlot();
    document.getElementById('division-result').innerHTML = '<p class="empty-state">Calculate ratios for this collection.</p>';
    updateBatchSummary();
  });
  document.addEventListener('analysis-source-settled', () => { syncAnalysisControls(); syncPlotControls(); updateBatchSummary(); });
  document.addEventListener('collections-released', () => refreshBatch().catch(error => {
    document.getElementById('batch-status').textContent = error.message;
  }));
  setupCollections(async () => {
    selectPanel('analysis');
    await executeWorkspaceTask(workspaceTasks().find(task => task.id === 'analysis'));
  });
  renderAnalysisContext();
  selectPanel("videos");
  const menu = document.getElementById("creator-menu");
  document.getElementById("open-library").addEventListener("click", () => {
    if (!menu.hidden) return closeCreatorMenu({ restoreFocus: true });
    document.getElementById("creator-menu-feedback").hidden = true;
    closeSelectMenus();
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
    closeSelectMenus(event.target);
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
    const filters = [];
    if (minimum || maximum) filters.push(`Views ${minimum || "0"}–${maximum || "unlimited"}`);
    document.getElementById("filter-summary").textContent = `· ${filters.join(" · ") || "All fetched rows"} · run a tool to apply`;
  };
  ["local-min-views", "local-max-views"].forEach(id => {
    document.getElementById(id).addEventListener("input", updateFilterSummary);
    document.getElementById(id).addEventListener("change", updateFilterSummary);
  });
  updateFilterSummary();
  document.getElementById("creator-library-search").addEventListener("input", filterSavedCreators);
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
  bindAction("fetch-weekly", fetchWeekly);
  bindAction("fetch-random-sample", fetchRandomSample);
  setupSampling();
  setupNodes();
  setupTracking();
  setupSnapshots();
  document.getElementById("single-video-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter") document.getElementById("lookup-single-video").click();
  });
  bindAction("fetch-dataset", () => executeWorkspaceTask(workspaceTasks().find(task => task.id === "fetch")));
  bindAction("list-videos", async () => {
    const data = await runAction("list", { collection_id: null, local_filter: {
      minimum_views: document.getElementById('local-min-views').value, maximum_views: document.getElementById('local-max-views').value
    } });
    renderVideos("videos-result", data.videos);
  });
  bindAction("run-analysis", () => executeWorkspaceTask(workspaceTasks().find(task => task.id === "analysis")), syncAnalysisControls);
  bindAction("run-division", () => executeWorkspaceTask(workspaceTasks().find(task => task.id === "division")));
  bindAction("run-plot", () => executeWorkspaceTask(workspaceTasks().find(task => task.id === "plot")), syncPlotControls);
  setupBatch({ async viewResult(mission, view) {
    await refreshCollections();
    chooseCollectionForMission(mission, view);
  }, onSettled() { syncAnalysisControls(); syncPlotControls(); } });
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
  for (const [button, input] of [["set-frequency", "request-frequency"], ["set-dataset-frequency", "dataset-request-frequency"]]) {
    bindAction(button, async () => {
      const value = Number(document.getElementById(input).value);
      if (!Number.isFinite(value) || value < 0.1 || value > 4) throw Error("Use pacing from 0.1 to 4 requests/s.");
      await postJSON("/api/request-frequency", { value });
      await load();
    });
  }
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
setupMemory();
setupSelects();
document.addEventListener('creators-source-changed', () => load().catch(error => {
  document.getElementById('status').textContent = error.message;
}));
load({ restoreData: true }).then(() => {
  document.documentElement.dataset.dashboardReady = 'true';
  document.dispatchEvent(new Event('dashboard-ready'));
}).catch((error) => {
  document.getElementById("status").textContent = error.message;
});
