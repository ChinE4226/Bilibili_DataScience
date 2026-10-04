import { escapeHTML, formatValue, table } from "../ui.js";
import { uiState } from "../state.js";

let current = null;
export function resetAnalysis() {
  current = null;
  document.getElementById('analysis-result').innerHTML = '<p class="empty-state">Run Analyze Dataset for this collection.</p>';
  syncAnalysisControls();
}
const percent = value => value == null ? "—" : `${(value * 100).toFixed(2)}%`;
const scrollTable = (headers, rows) => `<div class="analysis-table">${table(headers, rows)}</div>`;

function charts(summary) {
  if (!summary?.count) return `<p class="empty-state">No valid values for this metric.</p>`;
  const bins = summary.bins;
  const peak = Math.max(...bins.map(bin => bin.count));
  const width = 600 / bins.length;
  const bars = bins.map((bin, i) => {
    const height = 130 * bin.count / peak;
    return `<rect x="${40 + i * width}" y="${165 - height}" width="${Math.max(1, width - 3)}" height="${height}" fill="currentColor"><title>${escapeHTML(`${formatValue(bin.low)}–${formatValue(bin.high)}: ${bin.count} videos`)}</title></rect>
      <text x="${40 + (i + .5) * width}" y="${157 - height}" text-anchor="middle">${bin.count}</text>`;
  }).join("");
  const span = summary.max - summary.min;
  const x = value => span ? 40 + (value - summary.min) / span * 600 : 340;
  return `<div class="analysis-charts">
    <figure><figcaption>${escapeHTML(summary.label)} distribution · ${summary.count} valid videos</figcaption>
      <svg viewBox="0 0 680 205" role="img" aria-label="Histogram of ${escapeHTML(summary.label)} with video counts per bin">
        ${bars}<line x1="40" y1="165" x2="640" y2="165" stroke="currentColor"/>
        <text x="40" y="191">${escapeHTML(formatValue(summary.min))}</text><text x="640" y="191" text-anchor="end">${escapeHTML(formatValue(summary.max))}</text>
      </svg>
      <details><summary>Histogram values</summary>${scrollTable(["From (inclusive)", "To (last bin inclusive)", "Videos"], bins.map(b => [b.low, b.high, b.count]))}</details>
    </figure>
    <figure><figcaption>Box plot · middle 50% and median</figcaption>
      <svg viewBox="0 0 680 115" role="img" aria-label="Box plot: Q1 ${summary.q1}, median ${summary.median}, Q3 ${summary.q3}">
        <line x1="${x(summary.whisker_low)}" y1="45" x2="${x(summary.whisker_high)}" y2="45" stroke="currentColor"/>
        <rect x="${x(summary.q1)}" y="25" width="${Math.max(1, x(summary.q3) - x(summary.q1))}" height="40" fill="var(--analysis-fill, #e1e7f0)" stroke="currentColor"/>
        ${[summary.whisker_low, summary.median, summary.whisker_high].map(v => `<line x1="${x(v)}" y1="20" x2="${x(v)}" y2="70" stroke="currentColor"/>`).join("")}
        <text x="40" y="98">${escapeHTML(formatValue(summary.min))}</text><text x="640" y="98" text-anchor="end">${escapeHTML(formatValue(summary.max))}</text>
      </svg>
      <p class="muted">Whiskers reach observed values inside the 1.5 × IQR fences. Flagged values appear in the outlier table. Fewer than four values: min–max whiskers, no outlier flags.</p>
    </figure>
  </div>`;
}

export function renderAnalysis(data) {
  current = data;
  document.getElementById("analysis-field").disabled = uiState.actionBusy;
  const field = document.getElementById("analysis-field").value;
  const metric = data.summaries.find(item => item.field === field) || data.summaries[0];
  const quality = data.quality;
  const outliers = data.outliers.filter(item => item.metric === metric?.label);
  document.getElementById("analysis-result").innerHTML = `
    <p>${escapeHTML(data.selection || "Fetched selection")}</p>
    <h3 id="analysis-metric-title">${escapeHTML(metric?.label || "Metric")} overview</h3>
    ${metric ? scrollTable(["Valid videos", "Mean", "Median", "Min", "Max", "P90"], [[metric.count, metric.mean, metric.median, metric.min, metric.max, metric.p90]]) : ""}
    ${charts(metric)}
    <h3>Unusual ${escapeHTML(metric?.label.toLowerCase() || "metric")} values</h3>
    <p class="muted">Descriptive flags, not errors or proof of unusual quality. No observations are removed. At least four valid values are required.</p>
    ${scrollTable(["Title", "BVID", "Value", "Reason"], outliers.map(r => [r.title, r.bvid, r.value, r.reason]))}
    <details><summary>Compare all metrics · ${quality.rows} videos</summary>
      <p class="muted">${quality.duplicate_rows} duplicate ID occurrences · ${quality.missing_identity} missing IDs. Zero is valid. Quartiles and P90 use linear interpolation.</p>
      ${scrollTable(["Metric", "Valid", "Missing / invalid", "Mean", "Min", "Q1", "Median", "Q3", "P90", "Max", "IQR"], data.summaries.map(s => [s.label, s.count, s.missing, s.mean, s.min, s.q1, s.median, s.q3, s.p90, s.max, s.iqr]))}
    </details>
    <h3>Engagement per view</h3>
    <p class="muted">Pooled = total interactions / total views on eligible rows. Median = typical per-video ratio. Missing counts and zero-view videos are excluded. These are interaction ratios, not unique-user conversion rates.</p>
    ${scrollTable(["Interaction", "Eligible", "Excluded", "Pooled", "Median per video"], data.engagement.map(r => [r.field, r.count, r.excluded, percent(r.pooled), percent(r.median)]))}
    <details><summary>Per-video engagement (${data.engagement_rows.length})</summary>
      <p class="muted">Low views means fewer than ${data.low_view_threshold} views, a display flag only. Ratios for these videos may be unstable.</p>
      ${scrollTable(["Title", "BVID", "Views", "Low views", "Likes / view", "Favorites / view", "Coins / view", "Shares / view"], data.engagement_rows.map(r => [r.title, r.bvid, r.views, r.low_views ? "Yes" : "", percent(r.likes), percent(r.favorites), percent(r.coins), percent(r.shares)]))}
    </details>
    <p class="muted">Metrics reflect the collection interval, not current growth. Older videos have had longer to accumulate interactions; compare similarly aged videos.</p>`;
}

export function setupAnalysis() {
  document.getElementById("analysis-field").addEventListener("change", () => {
    if (current) renderAnalysis(current);
  });
}

export function syncAnalysisControls() {
  document.getElementById("analysis-field").disabled = !current || uiState.actionBusy;
  document.getElementById("analysis-field").dispatchEvent(new Event("change"));
}
