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
    button.disabled = !ready || (button.dataset.plotRange !== undefined && button.dataset.plotRange !== "all" && !dated);
  });
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
    `<strong title="${escapeHTML(point.title)}">${escapeHTML(point.title)}</strong><span>${escapeHTML(point.label)} | ${escapeHTML(snapshot.y_label || "Value")}: ${formatAxisNumber(point.value)}</span>`;
}

function rangeBounds() {
  const zoom = chart.getOption().dataZoom[0];
  const first = dated ? plotPoints[0].time : 0;
  const last = dated ? plotPoints.at(-1).time : plotPoints.length - 1;
  return [first + (last - first) * zoom.start / 100, first + (last - first) * zoom.end / 100];
}

function updateScale() {
  if (!plotPoints.length) return;
  const [start, end] = rangeBounds();
  const visible = plotPoints.filter((point, index) => {
    const x = dated ? point.time : index;
    return x >= start - 1 && x <= end + 1;
  });
  chart.setOption({ yAxis: niceYAxis((visible.length ? visible : plotPoints).map((point) => point.value)) });
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
  } else if (dated) {
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
    data: plotPoints.map((point) => dated ? [point.time, point.value] : point.value),
    symbolSize: 6, showSymbol: plotPoints.length <= 80, lineStyle: { width: 2 },
    barMaxWidth: 28, emphasis: { focus: "series" }, clip: true
  };
}

export function setupPlot(onSaved) {
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
  document.getElementById("plot-style").addEventListener("change", () => {
    chart?.setOption({ series: [seriesOptions()] });
  });
  document.getElementById("download-plot").addEventListener("click", () => {
    if (!chart || !plotPoints.length) return;
    chart.dispatchAction({ type: "hideTip" });
    const link = document.createElement("a");
    link.download = "bilibili-chart-view.png";
    link.href = chart.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#ffffff" });
    link.click();
  });
  bindAction("save-plot", async () => {
    const result = await postJSON("/api/plots/save", { plot_id: snapshot.plot_id });
    saved = true;
    document.getElementById("plot-save-status").innerHTML = `Saved: <a href="${escapeHTML(result.url)}" target="_blank" rel="noreferrer">${escapeHTML(result.name)}</a>`;
    await onSaved();
  }, syncPlotControls);
  const host = document.getElementById("plot-chart");
  resizeObserver = new ResizeObserver(() => {
    if (chart && host.clientWidth && host.clientHeight) {
      chart.resize({ width: host.clientWidth, height: host.clientHeight });
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
  dated = plotPoints.length > 0 && plotPoints.every((point) => Number.isFinite(point.time));
  const host = document.getElementById("plot-chart");
  document.getElementById("plot-workspace").hidden = false;
  document.getElementById("plot-title").textContent = data.y_label || data.plot_label || "Value";
  document.getElementById("plot-context").textContent = [data.selected_creator?.name, data.selection].filter(Boolean).join(" | ");
  document.getElementById("plot-save-status").textContent = "Not saved";
  document.getElementById("plot-inspection").textContent = "";
  document.getElementById("plot-summary").innerHTML = "";
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
  host.setAttribute("aria-label", `${data.y_label || "Value"} by published time, ${values.length} videos`);
  chart = echarts.init(host, null, { width: host.clientWidth || 800, height: host.clientHeight || 480 });
  chart.setOption({
    animation: false,
    backgroundColor: "#ffffff",
    color: ["#287956"],
    textStyle: { fontFamily: "-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif" },
    grid: { left: 12, right: 18, top: 36, bottom: 94, containLabel: true },
    tooltip: {
      trigger: "axis", confine: true,
      extraCssText: "max-width: min(280px, 70%); white-space: normal; overflow-wrap: anywhere;",
      axisPointer: { type: "cross", label: { show: false }, crossStyle: { color: "#89958e" } },
      formatter(params) {
        const point = plotPoints[params[0]?.dataIndex];
        if (!point) return "";
        inspect(point);
        return `<strong>${escapeHTML(point.title)}</strong><br>${escapeHTML(point.label)}<br>${escapeHTML(data.y_label || "Value")}: <b>${formatAxisNumber(point.value)}</b>`;
      }
    },
    xAxis: {
      type: dated ? "time" : "category",
      ...(dated ? { min: plotPoints[0].time, max: plotPoints.at(-1).time } : { data: plotPoints.map((point) => point.label) }),
      name: "Published time", nameLocation: "middle", nameGap: 36,
      splitNumber: host.clientWidth < 500 ? 3 : 6,
      axisLabel: { hideOverlap: true, color: "#5c6660" },
      axisLine: { lineStyle: { color: "#aab6af" } },
      splitLine: { show: true, lineStyle: { color: "#f1f3f2" } }
    },
    yAxis: {
      ...niceYAxis(values), type: "value", name: data.y_label || "Value", nameGap: 18,
      nameTextStyle: { align: "left", width: Math.max(160, host.clientWidth - 80), overflow: "truncate" },
      axisLabel: { formatter: formatAxisNumber, color: "#5c6660" },
      splitLine: { lineStyle: { color: "#e4e9e6" } }
    },
    dataZoom: [
      { type: "slider", xAxisIndex: 0, bottom: 8, height: 26, start: 0, end: 100, showDetail: false, borderColor: "#cbd5cf", fillerColor: "rgba(40,121,86,0.1)", filterMode: "none" },
      { type: "inside", xAxisIndex: 0, filterMode: "none", zoomOnMouseWheel: true, moveOnMouseMove: true }
    ],
    series: [seriesOptions()]
  });
  chart.on("datazoom", () => { markRange(null); updateScale(); });
  chart.getZr().on("globalout", () => inspect(plotPoints.at(-1)));
  markRange("all");
  inspect(plotPoints.at(-1));
}
