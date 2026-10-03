import { movingAverage, exponentialAverage, rollingMedian, relativePerformance } from "../indicators.js";
export { movingAverage } from "../indicators.js";
import * as echarts from "../../vendor/echarts-5.6.0.esm.min.js";
import createIcon from "../../vendor/lucide/createElement.js";
import ZoomIn from "../../vendor/lucide/icons/zoom-in.js";
import ZoomOut from "../../vendor/lucide/icons/zoom-out.js";
import Reset from "../../vendor/lucide/icons/rotate-ccw.js";
import Save from "../../vendor/lucide/icons/save.js";
import Download from "../../vendor/lucide/icons/download.js";
import { bindAction, escapeHTML } from "../ui.js";
import { postJSON } from "../api.js";
import { uiState } from "../state.js";

let chart;
let snapshot;
let plotPoints = [];
let dated = false;
let saved = false;
let resizeObserver;
const maStyles = { 5: { color: "#b47732", type: "solid" }, 10: { color: "#8363a5", type: "dashed" }, 20: { color: "#b55d70", type: "dotted" } };
let movingAverages = new Map();

const indicatorDefinitions = {
  ema10: { label: "EMA10", period: 10, compute: exponentialAverage, color: "#3669ae", type: "solid" },
  ema20: { label: "EMA20", period: 20, compute: exponentialAverage, color: "#447b8b", type: "dashed" },
  median5: { label: "Median5", period: 5, compute: rollingMedian, color: "#a65a37", type: "dashed" },
  median10: { label: "Median10", period: 10, compute: rollingMedian, color: "#6b607d", type: "dotted" }
};
let extraOverlays = new Map();
let relativeValues = [];
let relativeChart;

function selectedIndicators() {
  return [...document.querySelectorAll('[data-indicator][aria-pressed="true"]')].map(button => button.dataset.indicator);
}

function hasRelative() { return selectedIndicators().includes("relative20"); }

function overlayEntries() {
  return [...[...movingAverages].map(([period, values]) => ({ id: `ma-${period}`, label: `MA${period}`, values, ...maStyles[period] })),
    ...[...extraOverlays].map(([id, values]) => ({ id, values, ...indicatorDefinitions[id] }))];
}

function selectedPeriods() {
  return [...document.querySelectorAll('[data-ma-period][aria-pressed="true"]')].map(button => Number(button.dataset.maPeriod));
}

function refreshAverages() {
  movingAverages = new Map(selectedPeriods().map(period => [period, movingAverage(plotPoints.map(point => point.value), period)]));
  const values = plotPoints.map(point => point.value);
  extraOverlays = new Map(selectedIndicators().filter(id => indicatorDefinitions[id]).map(id => {
    const definition = indicatorDefinitions[id];
    return [id, definition.compute(values, definition.period)];
  }));
  relativeValues = hasRelative() ? relativePerformance(values) : [];
  const missing = [...selectedPeriods().map(period => ({ label: `MA${period}`, period })),
    ...selectedIndicators().map(id => indicatorDefinitions[id] || { label: "Relative20", period: 21 })]
    .filter(item => item.period > plotPoints.length);
  const messages = missing.map(item => `${item.label} needs ${item.period} videos (${plotPoints.length} available).`);
  if (hasRelative() && values.length >= 21) {
    const undefinedCount = relativeValues.slice(20).filter(value => value === null).length;
    if (undefinedCount) messages.push(`${undefinedCount} relative values are unavailable because their baseline is zero or the ratio is not finite.`);
  }
  const status = document.getElementById("plot-ma-status");
  status.hidden = !messages.length;
  status.textContent = messages.join(" ");
}

function formatIndicator(value) {
  return new Intl.NumberFormat("en-US", { maximumSignificantDigits: 6 }).format(value);
}

function formatRelative(value) {
  return new Intl.NumberFormat("en-US", { maximumSignificantDigits: 4 }).format(value);
}

function averageDetails(index) {
  const details = overlayEntries().map(entry => `${entry.label}: ${entry.values[index] == null ? "—" : formatIndicator(entry.values[index])}`);
  if (hasRelative()) details.push(`Relative20: ${relativeValues[index] == null ? "—" : `${formatRelative(relativeValues[index])}×`}`);
  return details.join(" | ");
}

export function updatePlotControls() {
  const quotient = document.getElementById("plot-mode").value === "quotient";
  document.querySelectorAll(".plot-field-control").forEach((element) => { element.hidden = quotient; });
  document.querySelectorAll(".plot-quotient-control").forEach((element) => { element.hidden = !quotient; });
}

export function formatAxisNumber(value) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 12 }).format(value);
}

export function niceYAxis(values) {
  const peak = values.reduce((maximum, value) => Number.isFinite(value) ? Math.max(maximum, value) : maximum, 0);
  const target = peak ? peak * 1.08 : 1;
  const rawStep = target / 5;
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const interval = [1, 2, 5, 10].map((factor) => factor * magnitude).find((step) => step >= rawStep);
  return { min: 0, max: Math.ceil(target / interval) * interval, interval };
}

export function preparePoints(points) {
  const valid = points.filter((point) => typeof point.value === "number" && Number.isFinite(point.value) && point.value >= 0)
    .map((point) => ({ ...point, time: Date.parse(String(point.label).replace(" ", "T")) }));
  return valid.every((point) => Number.isFinite(point.time)) ? valid.sort((a, b) => a.time - b.time) : valid;
}

export function syncPlotControls() {
  const ready = plotPoints.length > 0 && !uiState.actionBusy;
  document.querySelectorAll(".plot-toolbar button").forEach((button) => {
    button.disabled = !ready || (button.dataset.plotRange !== undefined && button.dataset.plotRange !== "all" && !timeAxis());
  });
  document.querySelectorAll("[data-ma-period], [data-indicator]").forEach(button => { button.disabled = !ready; });
  document.getElementById("plot-style").disabled = !ready;
  document.getElementById("save-plot").disabled = !ready || !snapshot?.plot_id || saved;
}

function markRange(range) {
  document.querySelectorAll("[data-plot-range]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.plotRange === range));
  });
}

function inspect(point) {
  if (!point) return;
  document.getElementById("plot-inspection").innerHTML =
    `<strong title="${escapeHTML(point.title)}">${escapeHTML(point.title)}</strong><span>${escapeHTML(point.label)} | ${escapeHTML(snapshot.y_label || "Value")}: ${formatAxisNumber(point.value)}${(overlayEntries().length || hasRelative()) ? ` | ${averageDetails(plotPoints.indexOf(point))}` : ""}</span>`;
}

function timeAxis() {
  return dated && document.getElementById("plot-axis").value === "time";
}

function rangeBounds() {
  const zoom = chart.getOption().dataZoom[0];
  const first = timeAxis() ? plotPoints[0].time : 0;
  const last = timeAxis() ? plotPoints.at(-1).time : plotPoints.length - 1;
  return [first + (last - first) * zoom.start / 100, first + (last - first) * zoom.end / 100];
}

function updateScale() {
  if (!plotPoints.length) return;
  const [start, end] = rangeBounds();
  const visible = plotPoints.flatMap((point, index) => {
    const x = timeAxis() ? point.time : index;
    return x >= start - 1 && x <= end + 1 ? [point.value, ...overlayEntries().map(entry => entry.values[index]).filter(value => value !== null)] : [];
  });
  chart.setOption({ yAxis: niceYAxis(visible.length ? visible : plotPoints.map(point => point.value)) });
}

function zoomBy(factor) {
  if (!chart || !plotPoints.length) return;
  const zoom = chart.getOption().dataZoom[0];
  const center = (zoom.start + zoom.end) / 2;
  const span = Math.min(100, Math.max(0.1, (zoom.end - zoom.start) * factor));
  const start = Math.max(0, Math.min(100 - span, center - span / 2));
  chart.dispatchAction({ type: "dataZoom", start, end: start + span });
}

function setRange(range) {
  if (!chart || !plotPoints.length) return;
  if (range === "all") {
    chart.dispatchAction({ type: "dataZoom", start: 0, end: 100 });
  } else if (timeAxis()) {
    const first = plotPoints[0].time;
    const last = plotPoints.at(-1).time;
    const start = Math.max(first, last - Number(range) * 86400000);
    chart.dispatchAction({ type: "dataZoom", start: last === first ? 0 : (start - first) / (last - first) * 100, end: 100 });
  }
  markRange(range);
}

function seriesOptions() {
  return {
    id: "videos", name: snapshot.y_label || "Value",
    type: document.getElementById("plot-style").value,
    data: plotPoints.map((point) => timeAxis() ? [point.time, point.value] : point.value),
    symbolSize: 6, showSymbol: plotPoints.length <= 80, lineStyle: { width: 2 },
    barMaxWidth: 28, emphasis: { focus: "series" }, clip: true
  };
}

function legendEntries() {
  if (!plotPoints.length || !(overlayEntries().length || hasRelative())) return [];
  return [{ label: snapshot.y_label || "Value", color: "#596b88", type: "solid" },
    ...overlayEntries(), ...(hasRelative() ? [{ label: "Relative20 (× prior mean)", color: "#53758c", type: "solid" }] : [])];
}

function renderLegend() {
  const legend = document.getElementById("plot-legend");
  const entries = legendEntries();
  legend.hidden = !entries.length;
  legend.innerHTML = entries.map(entry => `<li><span aria-hidden="true" style="border-color:${entry.color};border-top-style:${entry.type}"></span>${escapeHTML(entry.label)}</li>`).join("");
}

async function downloadChart() {
  const source = chart.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#ffffff" });
  const entries = legendEntries();
  if (!entries.length) return source;
  // Append a separate footer in memory; the chart and its current zoom never move.
  const relativeSource = relativeChart?.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#ffffff" });
  const picture = new Image();
  picture.src = source;
  await picture.decode();
  const relativePicture = relativeSource ? new Image() : null;
  if (relativePicture) { relativePicture.src = relativeSource; await relativePicture.decode(); }
  const imageHeight = picture.height + (relativePicture?.height || 0);
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  const width = picture.width / 2;
  context.font = "12px sans-serif";
  const rows = entries.map(entry => {
    const lines = [""];
    for (const character of entry.label) {
      if (context.measureText(lines.at(-1) + character).width > width - 64) lines.push("");
      lines[lines.length - 1] += character;
    }
    return { ...entry, lines };
  });
  canvas.width = picture.width;
  canvas.height = imageHeight + 2 * (24 + rows.reduce((height, row) => height + row.lines.length * 18 + 6, 0));
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(picture, 0, 0);
  if (relativePicture) context.drawImage(relativePicture, 0, picture.height);
  context.scale(2, 2);
  context.font = "12px sans-serif";
  context.textBaseline = "middle";
  let y = imageHeight / 2 + 20;
  for (const row of rows) {
    context.strokeStyle = row.color;
    context.lineWidth = 2;
    context.setLineDash(row.type === "dashed" ? [6, 4] : row.type === "dotted" ? [2, 3] : []);
    context.beginPath(); context.moveTo(16, y); context.lineTo(34, y); context.stroke();
    context.fillStyle = "#626b7a";
    row.lines.forEach((line, index) => context.fillText(line, 44, y + index * 18));
    y += row.lines.length * 18 + 6;
  }
  return canvas.toDataURL("image/png");
}

function allSeries() {
  return [seriesOptions(), ...overlayEntries().map(entry => ({
    id: entry.id, name: entry.label, type: "line",
    data: entry.values.map((value, index) => timeAxis() ? [plotPoints[index].time, value] : value),
    showSymbol: false, connectNulls: false, lineStyle: { width: 2, color: entry.color, type: entry.type },
    itemStyle: { color: entry.color }, z: 3, clip: true
  }))];
}

function syncRelativeZoom() {
  if (!relativeChart || !chart) return;
  const { start, end } = chart.getOption().dataZoom[0];
  relativeChart.dispatchAction({ type: "dataZoom", start, end }, { silent: true });
  const [lower, upper] = rangeBounds();
  const visible = relativeValues.filter((value, index) => {
    const x = timeAxis() ? plotPoints[index].time : index;
    return value !== null && x >= lower - 1 && x <= upper + 1;
  });
  relativeChart.setOption({ yAxis: niceYAxis([1, ...visible]) });
}

function renderRelative() {
  const panel = document.getElementById("plot-relative-panel");
  relativeChart?.dispose();
  relativeChart = null;
  panel.hidden = !hasRelative() || !plotPoints.length;
  if (panel.hidden || !chart) return;
  const host = document.getElementById("plot-relative-chart");
  relativeChart = echarts.init(host, null, { width: host.clientWidth || 800, height: 220 });
  relativeChart.setOption({
    animation: false, backgroundColor: "#fff",
    grid: { left: 12, right: 18, top: 32, bottom: 42, containLabel: true },
    xAxis: { ...chart.getOption().xAxis[0], name: "", nameGap: 0 },
    yAxis: { type: "value", ...niceYAxis([1, ...relativeValues]), name: "Relative20 (×)",
      axisLabel: { formatter: value => `${formatAxisNumber(value)}×` }, splitLine: { lineStyle: { color: "#e5e8ee" } } },
    tooltip: { trigger: "axis", confine: true, formatter(params) {
      const index = params[0]?.dataIndex;
      const point = plotPoints[index];
      if (!point) return "";
      inspect(point);
      return `${escapeHTML(point.title)}<br>Relative20: ${relativeValues[index] == null ? "—" : `${formatRelative(relativeValues[index])}×`}`;
    } },
    dataZoom: [{ type: "inside", filterMode: "none", xAxisIndex: 0 }],
    series: [{ id: "relative20", type: "line", showSymbol: false, connectNulls: false,
      data: relativeValues.map((value, index) => timeAxis() ? [plotPoints[index].time, value] : value),
      lineStyle: { width: 2, color: "#53758c" }, itemStyle: { color: "#53758c" },
      markLine: { silent: true, symbol: "none", label: { show: false }, lineStyle: { color: "#8b94a3", type: "dashed" }, data: [{ yAxis: 1 }] }
    }]
  });
  syncRelativeZoom();
  relativeChart.on("datazoom", () => {
    const { start, end } = relativeChart.getOption().dataZoom[0];
    chart.dispatchAction({ type: "dataZoom", start, end });
  });
}

export function setupPlot(onSaved) {
  document.querySelectorAll("[data-ma-period], [data-indicator]").forEach(button => {
    button.addEventListener("click", () => {
      button.setAttribute("aria-pressed", String(button.getAttribute("aria-pressed") !== "true"));
      refreshAverages();
      renderLegend();
      chart?.setOption({ series: allSeries() }, { replaceMerge: ["series"] });
      updateScale();
      renderRelative();
      inspect(plotPoints.at(-1));
      saved = false;
      document.getElementById("plot-save-status").textContent = "Not saved";
      syncPlotControls();
    });
  });
  const icons = { "zoom-in": ZoomIn, "zoom-out": ZoomOut, reset: Reset, save: Save, download: Download };
  document.querySelectorAll("[data-plot-icon]").forEach((element) => {
    element.appendChild(createIcon(icons[element.dataset.plotIcon], { "aria-hidden": "true" }));
  });
  document.getElementById("plot-zoom-in").addEventListener("click", () => zoomBy(0.6));
  document.getElementById("plot-zoom-out").addEventListener("click", () => zoomBy(1.6));
  document.getElementById("plot-reset").addEventListener("click", () => setRange("all"));
  document.querySelectorAll("[data-plot-range]").forEach((button) => {
    button.addEventListener("click", () => setRange(button.dataset.plotRange));
  });
  document.getElementById("plot-axis").addEventListener("change", () => {
    if (snapshot) renderPlot(snapshot);
  });
  document.getElementById("plot-style").addEventListener("change", () => {
    chart?.setOption({ series: allSeries() });
  });
  document.getElementById("download-plot").addEventListener("click", async () => {
    if (!chart || !plotPoints.length) return;
    chart.dispatchAction({ type: "hideTip" });
    const link = document.createElement("a");
    link.download = "bilibili-chart-view.png";
    link.href = await downloadChart();
    link.click();
  });
  bindAction("save-plot", async () => {
    const result = await postJSON("/api/plots/save", { plot_id: snapshot.plot_id, axis_mode: timeAxis() ? "time" : "number", ma_periods: selectedPeriods(), indicators: selectedIndicators() });
    saved = true;
    document.getElementById("plot-save-status").innerHTML = `Saved: <a href="${escapeHTML(result.url)}" target="_blank" rel="noreferrer">${escapeHTML(result.name)}</a>`;
    await onSaved();
  }, syncPlotControls);
  const host = document.getElementById("plot-chart");
  resizeObserver = new ResizeObserver(() => {
    if (chart && host.clientWidth && host.clientHeight) {
      chart.resize({ width: host.clientWidth, height: host.clientHeight });
      relativeChart?.resize({ width: document.getElementById("plot-relative-chart").clientWidth, height: 220 });
      chart.setOption({
        xAxis: { splitNumber: host.clientWidth < 500 ? 3 : 6 },
        yAxis: { nameTextStyle: { width: Math.max(160, host.clientWidth - 80) } }
      });
    }
  });
  resizeObserver.observe(host);
  host.addEventListener("keydown", (event) => {
    if (event.key === "+" || event.key === "=") zoomBy(0.6);
    else if (event.key === "-") zoomBy(1.6);
    else if (event.key === "Home") setRange("all");
    else return;
    event.preventDefault();
  });
}

export function renderPlot(data) {
  snapshot = data;
  saved = false;
  plotPoints = preparePoints(data.points);
  refreshAverages();
  renderLegend();
  dated = plotPoints.length > 0 && plotPoints.every((point) => Number.isFinite(point.time));
  const host = document.getElementById("plot-chart");
  document.getElementById("plot-workspace").hidden = false;
  document.getElementById("plot-title").textContent = data.y_label || data.plot_label || "Value";
  document.getElementById("plot-context").textContent = [data.selected_creator?.name, data.selection].filter(Boolean).join(" | ");
  document.getElementById("plot-save-status").textContent = "Not saved";
  document.getElementById("plot-inspection").textContent = "";
  document.getElementById("plot-summary").innerHTML = "";
  relativeChart?.dispose();
  relativeChart = null;
  document.getElementById("plot-relative-panel").hidden = true;
  chart?.dispose();
  chart = null;
  host.replaceChildren();
  syncPlotControls();
  if (!plotPoints.length) {
    host.innerHTML = '<p class="empty-state">No points to plot.</p>';
    return;
  }
  const values = plotPoints.map((point) => point.value);
  const minimum = values.reduce((a, b) => Math.min(a, b));
  const maximum = values.reduce((a, b) => Math.max(a, b));
  const summary = [[dated ? "Latest video" : "Last video", values.at(-1)], ["Lowest", minimum], ["Highest", maximum], ["Videos", values.length]];
  document.getElementById("plot-summary").innerHTML = summary.map(([label, value]) =>
    `<div><dt>${label}</dt><dd>${formatAxisNumber(value)}</dd></div>`).join("");
  host.setAttribute("aria-label", `${data.y_label || "Value"} by ${timeAxis() ? "published time" : "video number"}, ${values.length} videos`);
  chart = echarts.init(host, null, { width: host.clientWidth || 800, height: host.clientHeight || 480 });
  chart.setOption({
    animation: false,
    backgroundColor: "#ffffff",
    color: ["#596b88"],
    textStyle: { fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif" },
    grid: { left: 12, right: 18, top: 36, bottom: 94, containLabel: true },
    tooltip: {
      trigger: "axis", confine: true,
      extraCssText: "max-width: min(280px, 70%); white-space: normal; overflow-wrap: anywhere;",
      axisPointer: { type: "cross", label: { show: false }, crossStyle: { color: "#8c96a7" } },
      formatter(params) {
        const point = plotPoints[params[0]?.dataIndex];
        if (!point) return "";
        inspect(point);
        return `<strong>${escapeHTML(point.title)}</strong><br>${escapeHTML(point.label)}<br>${escapeHTML(data.y_label || "Value")}: <b>${formatAxisNumber(point.value)}</b>${(overlayEntries().length || hasRelative()) ? `<br>${averageDetails(params[0].dataIndex)}` : ""}`;
      }
    },
    xAxis: {
      type: timeAxis() ? "time" : "category",
      ...(timeAxis() ? { min: plotPoints[0].time, max: plotPoints.at(-1).time } : { data: plotPoints.map((point, index) => index + 1) }),
      name: timeAxis() ? "Published time" : dated ? "Video number (oldest → newest)" : "Video number", nameLocation: "middle", nameGap: 36,
      splitNumber: host.clientWidth < 500 ? 3 : 6,
      axisLabel: { hideOverlap: true, color: "#626b7a" },
      axisLine: { lineStyle: { color: "#afb7c5" } },
      splitLine: { show: true, lineStyle: { color: "#f2f3f5" } }
    },
    yAxis: {
      ...niceYAxis(values), type: "value", name: data.y_label || "Value", nameGap: 18,
      nameTextStyle: { align: "left", width: Math.max(160, host.clientWidth - 80), overflow: "truncate" },
      axisLabel: { formatter: formatAxisNumber, color: "#626b7a" },
      splitLine: { lineStyle: { color: "#e5e8ee" } }
    },
    dataZoom: [
      { type: "slider", xAxisIndex: 0, bottom: 8, height: 26, start: 0, end: 100, showDetail: false, borderColor: "#cbd3df", fillerColor: "rgba(89,107,136,0.12)", filterMode: "none" },
      { type: "inside", xAxisIndex: 0, filterMode: "none", zoomOnMouseWheel: true, moveOnMouseMove: true }
    ],
    series: allSeries()
  });
  chart.on("datazoom", () => { markRange(null); updateScale(); syncRelativeZoom(); });
  renderRelative();
  chart.getZr().on("globalout", () => inspect(plotPoints.at(-1)));
  markRange("all");
  inspect(plotPoints.at(-1));
}
