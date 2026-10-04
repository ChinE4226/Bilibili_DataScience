import { bindAction } from "./ui.js";
import { uiState } from "./state.js";
import { videoActionPayload } from "./progress.js";
import { closeSelectMenus } from "./selects.js";

let captureTasks;
let running = false;
let stopRequested = false;

const selected = id => document.getElementById(`batch-${id}`).checked;
const optionLabel = id => document.getElementById(id).selectedOptions[0]?.textContent || "";

function taskState(id, state, text) {
  document.querySelector(`[data-batch-row="${id}"]`).dataset.state = state;
  document.getElementById(`batch-state-${id}`).textContent = text;
}

export function updateBatchSummary() {
  if (!captureTasks || running) return;
  const { selection, local_filter: filter } = videoActionPayload();
  const range = selection.kind === "position" ? `${selection.end - selection.start + 1} valid videos from position ${selection.start}`
    : selection.kind === "published" ? `${selection.start_time || "Start time"} to ${selection.end_time || "End time"}`
    : `${optionLabel("metric-field")} between ${selection.minimum || "no minimum"} and ${selection.maximum || "no maximum"}`;
  const views = filter.minimum_views || filter.maximum_views
    ? ` · views ${filter.minimum_views || "0"}–${filter.maximum_views || "unlimited"}` : " · no view limits";
  const creator = uiState.selectedCreator;
  document.getElementById("batch-context").textContent = uiState.collectionId
    ? `${uiState.analysisDataset?.source_label || 'Sampling collection'}${views} · collected rows only`
    : `Creator: ${creator?.name || creator?.uid || "choose a creator"}${views}`;
  document.getElementById("batch-config-fetch").textContent = uiState.collectionId ? 'Already collected · switch to Creator dataset to fetch' : `${range} · ${optionLabel('fetch-source')}`;
  document.getElementById("batch-config-division").textContent = `${optionLabel("division-numerator")} / ${optionLabel("division-denominator")} · ${document.getElementById("division-mode").value === "aggregate" ? "one pooled ratio" : "per video"}`;
  document.getElementById("batch-config-plot").textContent = `${document.getElementById("plot-mode").value === "field" ? optionLabel("plot-field") : `${optionLabel("plot-numerator")} / ${optionLabel("plot-denominator")}`} · ${optionLabel("plot-axis")}`;
  document.getElementById("run-batch").disabled = !captureTasks().some(task => selected(task.id));
}

export function setupBatch({ tasks, execute, syncControls }) {
  captureTasks = tasks;
  const stop = document.getElementById("stop-batch");
  const status = document.getElementById("batch-status");
  stop.addEventListener("click", () => {
    if (!running) return;
    stopRequested = true;
    stop.disabled = true;
    status.textContent = "Stopping after the current task finishes…";
  });
  document.addEventListener("change", event => {
    if (event.target.matches("input, select")) updateBatchSummary();
    if (!running && event.target.matches('[id^="batch-"]')) {
      const id = event.target.id.slice(6);
      taskState(id, "queued", selected(id) ? "Queued" : "Not selected");
      status.textContent = "Ready.";
    }
  });
  bindAction("run-batch", async () => {
    const queue = tasks().filter(task => selected(task.id));
    if (!queue.length) return;
    const payload = videoActionPayload();
    closeSelectMenus();
    const controls = [...document.querySelectorAll("input, select")].map(control => [control, control.disabled]);
    controls.forEach(([control]) => { control.disabled = true; });
    running = true;
    stopRequested = false;
    stop.disabled = false;
    document.getElementById("batch-progress").hidden = true;
    tasks().forEach(task => taskState(task.id, selected(task.id) ? "queued" : "idle", selected(task.id) ? "Queued" : "Not selected"));
    let completed = 0;
    try {
      for (const [index, task] of queue.entries()) {
        if (stopRequested) break;
        taskState(task.id, "running", "Running…");
        status.textContent = `Task ${index + 1} of ${queue.length}: ${task.label}…`;
        try {
          const data = await execute(task, payload, "batch-progress");
          completed++;
          const count = task.id === "fetch" ? data.dataset?.count ?? data.count
            : task.action === "plot" ? data.points.length : data.count ?? data.dataset?.count;
          const shortfall = task.id === "fetch" ? data.dataset?.collection?.shortfall : 0;
          taskState(task.id, "done", `Completed${count != null ? ` · ${count} videos` : ""}${shortfall ? ` · ${shortfall} short: no more available videos` : ""}`);
        } catch (error) {
          taskState(task.id, "failed", `Failed: ${error.message}`);
          queue.slice(index + 1).forEach(next => taskState(next.id, "skipped", "Skipped after failure"));
          status.textContent = `Stopped at ${task.label}: ${error.message} ${completed} of ${queue.length} tasks completed.`;
          return;
        }
      }
      if (completed < queue.length) {
        queue.slice(completed).forEach(task => taskState(task.id, "skipped", "Skipped by request"));
        status.textContent = `Stopped. ${completed} of ${queue.length} tasks completed. Completed results are available on their pages.`;
      } else {
        status.textContent = `Completed all ${completed} tasks. Results are available on their pages.`;
      }
    } finally {
      running = false;
      stop.disabled = true;
      controls.forEach(([control, disabled]) => { control.disabled = disabled; });
    }
  }, () => {
    syncControls();
    updateBatchSummary();
  });
  updateBatchSummary();
}
