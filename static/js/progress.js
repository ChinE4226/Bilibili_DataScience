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

export async function runAction(action, extra = {}, progressTarget = null) {
  const labels = { list: "Listing videos", analysis: "Analyzing videos", division: "Calculating division", plot: "Plotting data" };
  const targets = { list: "videos-progress", analysis: "analysis-progress", division: "division-progress", plot: "plot-progress" };
  startProgressPolling(labels[action] || "Running action", progressTarget || targets[action]);
  try {
    return await postJSON("/api/video-action", { action, selection: selectionPayload(), ...extra });
  } finally {
    await stopProgressPolling();
  }
}
