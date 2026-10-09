import { postJSON } from "../api.js";
import { escapeHTML, table } from "../ui.js";
import { startProgressPolling, stopProgressPolling } from "../progress.js";
import { registerCollection } from '../collections.js';
import { renderSnapshotChoice } from '../snapshot-choice.js';

const number = value => value == null ? "—" : value.toLocaleString(undefined, { maximumFractionDigits: 2 });
const percent = value => value == null ? "—" : `${(value * 100).toLocaleString(undefined, { maximumFractionDigits: 4 })}%`;
const scrollTable = (headers, rows) => `<div class="analysis-table">${table(headers, rows)}</div>`;

export function cohortTables(data) {
  const { counts } = data;
  return `${!counts.included ? '<p class="empty-state">No videos with complete valid metrics matched this collection.</p>' : ""}
    <h3>Average performance per video</h3>
    ${scrollTable(["Metric", "Videos", "Total", "Mean per video", "Median", "Min", "Max", "P90"], data.summaries.map(summary => [summary.label, summary.count, ...[summary.total, summary.mean, summary.median, summary.min, summary.max, summary.p90].map(number)]))}
    <h3>Average engagement per view</h3>
    <p class="muted">Mean per video gives each eligible video equal weight. Pooled = total interactions / total views. Zero-view videos are excluded from these ratios.</p>
    ${scrollTable(["Interaction", "Eligible videos", "Excluded", "Mean per video", "Median per video", "Pooled"], data.engagement.map(row => [row.label, row.count, row.excluded, percent(row.mean_per_video), percent(row.median_per_video), percent(row.pooled)]))}
    <details><summary>Included videos (${counts.included})</summary>
      ${scrollTable(["Title", "Creator", "Published", "Views", "Likes", "Replies", "Favorites", "Coins", "Shares", "BVID"], data.videos.map(video => [video.title, video.creator, video.published_time, video.views, video.likes, video.replies, video.favorites, video.coins, video.shares, video.bvid]))}
    </details>
    ${data.excluded.length ? `<details><summary>Skipped entries (${data.excluded.length})</summary>${scrollTable(["Title", "BVID", "Reason"], data.excluded.map(row => [row.title, row.bvid, row.reason]))}</details>` : ""}`;
}

export function renderWeekly(data) {
  registerCollection(data.dataset);
  const { issue, counts } = data;
  const views = data.summaries.find(summary => summary.field === "views");
  document.getElementById("weekly-result").innerHTML = `
    <div class="page-heading"><div><h3>${escapeHTML(issue.name)}</h3><p>${escapeHTML(issue.subject)}</p></div>
      <a href="${escapeHTML(issue.url)}" target="_blank" rel="noopener noreferrer">Open weekly list ↗</a></div>
    <p class="muted">Collected ${escapeHTML(new Date(data.started_at).toLocaleString())} – ${escapeHTML(new Date(data.collected_at).toLocaleString())}.</p>
    <dl class="plot-summary weekly-summary">${[["Listed videos", counts.listed], ["Included videos", counts.included], ["Creators included", counts.creators], ["Average views", views?.mean]].map(([label, value]) => `<div><dt>${label}</dt><dd>${number(value)}</dd></div>`).join("")}</dl>
    <p>${counts.invalid} invalid videos and ${counts.duplicates} duplicate entries skipped. Zero metric values are valid.</p>
    ${renderSnapshotChoice(data.dataset)}
    ${data.dataset ? `<div class="actions"><button type="button" class="primary" data-use-collection="${escapeHTML(data.dataset.collection_id)}">Use in Analysis</button></div>` : ''}
    ${cohortTables(data)}
    <p class="muted">This selected popular cohort describes the issue's videos. It is not an average across all Bilibili videos. Use in Analysis opens charts, ratios and unusual values on these collected rows. The creator dataset stays available.</p>`;
}

export async function fetchWeekly() {
  const source = document.getElementById("weekly-source").value;
  startProgressPolling("Fetching weekly popular", "weekly-progress");
  try {
    renderWeekly(await postJSON("/api/weekly-analysis", { source }));
  } finally {
    await stopProgressPolling();
  }
}
