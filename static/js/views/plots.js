import { escapeHTML } from "../ui.js";

export function updatePlotControls() {
  const quotient = document.getElementById("plot-mode").value === "quotient";
  document.querySelectorAll(".plot-field-control").forEach((element) => {
    element.hidden = quotient;
  });
  document.querySelectorAll(".plot-quotient-control").forEach((element) => {
    element.hidden = !quotient;
  });
}

export function formatAxisNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "0";
  const abs = Math.abs(number);
  if (abs >= 1000000) {
    return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 2 }).format(number);
  }
  if (abs >= 1000) {
    return new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(number);
  }
  if (abs >= 1) {
    return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(number);
  }
  if (abs >= 0.01) {
    return new Intl.NumberFormat(undefined, { maximumFractionDigits: 4 }).format(number);
  }
  if (number === 0) return "0";
  return number.toExponential(2);
}

export function renderPlot(points, yLabel = "Value") {
  const host = document.getElementById("plot-chart");
  const plotPoints = points
    .map((point) => ({ ...point, value: Number(point.value) }))
    .filter((point) => Number.isFinite(point.value));
  if (!plotPoints.length) {
    host.innerHTML = "<p class='muted'>No points to plot.</p>";
    return;
  }
  const width = 1040;
  const height = 430;
  const padding = { top: 30, right: 28, bottom: 78, left: 96 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const values = plotPoints.map((point) => point.value);
  let min = Math.min(...values);
  let max = Math.max(...values);
  const spread = max - min;
  const pad = spread ? Math.max(spread * 0.12, Math.abs(max) * 0.03, 1) : Math.max(Math.abs(max) * 0.12, 1);
  min -= pad;
  max += pad;
  const domain = max - min || 1;
  const step = plotPoints.length > 1 ? plotWidth / (plotPoints.length - 1) : 0;
  const coords = plotPoints.map((point, index) => {
    const x = padding.left + step * index;
    const y = padding.top + plotHeight - ((point.value - min) / domain) * plotHeight;
    return { x, y, point };
  });
  const line = coords.map((coord) => `${coord.x},${coord.y}`).join(" ");
  const tickCount = 6;
  const yTicks = Array.from({ length: tickCount }, (_, index) => min + (domain * index) / (tickCount - 1));
  const xTickStep = Math.max(1, Math.ceil(plotPoints.length / 7));
  const xTicks = plotPoints
    .map((point, index) => ({ point, index }))
    .filter(({ index }) => index === 0 || index === plotPoints.length - 1 || index % xTickStep === 0);
  host.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHTML(yLabel)} by published time">
    <rect x="0" y="0" width="${width}" height="${height}" fill="#fff"/>
    ${yTicks.map((tick) => {
      const y = padding.top + plotHeight - ((tick - min) / domain) * plotHeight;
      return `<line x1="${padding.left}" y1="${y}" x2="${width - padding.right}" y2="${y}" stroke="#e5e5e5"/>
        <text x="${padding.left - 10}" y="${y + 4}" text-anchor="end" fill="#555" font-size="13">${escapeHTML(formatAxisNumber(tick))}</text>`;
    }).join("")}
    <line x1="${padding.left}" y1="${padding.top + plotHeight}" x2="${width - padding.right}" y2="${padding.top + plotHeight}" stroke="#111" stroke-width="1.5"/>
    <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${padding.top + plotHeight}" stroke="#111" stroke-width="1.5"/>
    ${xTicks.map(({ point, index }) => {
      const x = padding.left + step * index;
      const label = String(point.label || "").slice(0, 10);
      return `<line x1="${x}" y1="${padding.top + plotHeight}" x2="${x}" y2="${padding.top + plotHeight + 6}" stroke="#111"/>
        <text x="${x}" y="${padding.top + plotHeight + 24}" text-anchor="middle" fill="#555" font-size="12">${escapeHTML(label)}</text>`;
    }).join("")}
    <polyline points="${line}" fill="none" stroke="#111" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>
    ${coords.map((coord) => `<circle cx="${coord.x}" cy="${coord.y}" r="4.5" fill="#111"><title>${escapeHTML(coord.point.title)} | ${escapeHTML(coord.point.label)} | ${escapeHTML(formatAxisNumber(coord.point.value))}</title></circle>`).join("")}
    <text x="${padding.left + plotWidth / 2}" y="${height - 18}" text-anchor="middle" fill="#111" font-size="14">Published time</text>
    <text transform="translate(24 ${padding.top + plotHeight / 2}) rotate(-90)" text-anchor="middle" fill="#111" font-size="14">${escapeHTML(yLabel)}</text>
  </svg>`;
}
