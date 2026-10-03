import { getJSON, postJSON } from "./api.js";
import { selectionPayload } from "./selection.js";

let progressTimer = null;
let progressStartedAt = null;
let activeProgressTarget = null;

export function progressLine(data) {
  const elapsed = progressStartedAt ? ` Elapsed: ${Math.max(0, Math.round((Date.now() - progressStartedAt) / 1000))}s.` : "";
  const count = data.count === null || data.count === undefined ? "" : ` Selected: ${data.count}.`;
  return `${data.message || "Running."}${elapsed}${count}`;
}

export function setProgressText(line) {
  document.getElementById("progress").textContent = line;
  if (activeProgressTarget) {
    const target = document.getElementById(activeProgressTarget);
    if (target) {
      target.hidden = false;
      target.textContent = line;
    }
  }
}

export async function refreshProgress() {
  const data = await getJSON("/api/progress");
  setProgressText(progressLine(data));
  return data;
}

export function startProgressPolling(label, targetId = null) {
  clearInterval(progressTimer);
  progressStartedAt = Date.now();
  activeProgressTarget = targetId;
  setProgressText(`${label}: request started.`);
  progressTimer = setInterval(() => {
    refreshProgress().catch(() => {});
  }, 800);
}

export async function stopProgressPolling() {
  clearInterval(progressTimer);
  progressTimer = null;
  await refreshProgress().catch(() => {});
  progressStartedAt = null;
  activeProgressTarget = null;
}

export function videoActionPayload() {
  return { selection: selectionPayload(), reuse_only: true, local_filter: {
    minimum_views: document.getElementById("local-min-views").value,
    maximum_views: document.getElementById("local-max-views").value
  } };
}

export async function runAction(action, extra = {}, progressTarget = null) {
  const labels = { list: "Listing videos", analysis: "Analyzing videos", division: "Calculating division", plot: "Plotting data" };
  const targets = { list: "videos-progress", analysis: "analysis-progress", division: "division-progress", plot: "plot-progress" };
  startProgressPolling(labels[action] || "Running action", progressTarget || targets[action]);
  try {
    const data = await postJSON("/api/video-action", { action, ...videoActionPayload(), ...extra });
    if (data.dataset) {
      const collection = data.dataset.collection;
      const collectionText = collection ? ` · ${collection.examined} checked · ${collection.skipped_invalid} invalid skipped${collection.skipped_duplicates ? ` · ${collection.skipped_duplicates} duplicates skipped` : ""}${collection.requested != null ? ` · ${collection.requested} requested` : ""}${collection.shortfall ? ` · ${collection.shortfall} short: no more available videos` : ""}` : "";
      document.getElementById("dataset-status").textContent = `${data.dataset.reused ? "Reused" : "Fetched"} ${data.dataset.count} valid videos${collectionText} · Creator ${data.dataset.uid || "sample"} · ${data.dataset.selection} · collected ${new Date(data.dataset.started_at).toLocaleString()} – ${new Date(data.dataset.collected_at).toLocaleString()}. In memory only.`;
    }
    const filterStatus = document.getElementById("dataset-filter-status");
    const counts = data.dataset?.filter_counts;
    filterStatus.hidden = !counts;
    if (counts) {
      const reasons = [];
      if (counts.view_range) reasons.push(`${counts.view_range} outside the view filter`);
      filterStatus.textContent = `${counts.fetched} fetched · ${counts.included} included · ${counts.excluded} excluded${reasons.length ? ` (${reasons.join("; ")})` : ""}.`;
    }
    return data;
  } finally {
    await stopProgressPolling();
  }
}
