import { uiState } from "./state.js";

export async function performAction(button, task, { showProgress = true, disableAll = true } = {}) {
  if (uiState.actionBusy) return;
  uiState.actionBusy = true;
  const feedback = document.getElementById(document.getElementById("creator-menu").hidden ? "page-feedback" : "creator-menu-feedback");
  feedback.hidden = !showProgress;
  feedback.classList.remove("error-message");
  feedback.textContent = `${button.textContent.trim()}...`;
  const restoreFocus = !disableAll && document.activeElement === button;
  const states = (disableAll ? [...document.querySelectorAll("button:not([data-panel]):not([data-section])")] : [button])
    .map((item) => [item, item.disabled]);
  states.forEach(([item]) => { item.disabled = true; });
  try {
    await task();
    feedback.hidden = true;
  } catch (error) {
    feedback.hidden = false;
    feedback.textContent = error.message;
    feedback.classList.add("error-message");
  } finally {
    states.forEach(([item, disabled]) => { item.disabled = disabled; });
    if (restoreFocus && document.activeElement === document.body && button.isConnected) {
      button.focus({ preventScroll: true });
    }
    uiState.actionBusy = false;
  }
}

export function bindAction(id, task, onSettled) {
  const button = document.getElementById(id);
  button.addEventListener("click", () => performAction(button, task).finally(() => onSettled?.()));
}

export function formatBytes(value) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

export function escapeHTML(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

export function fillOptions(id, fields) {
  document.getElementById(id).innerHTML = fields
    .map(([value, label]) => `<option value="${value}">${label}</option>`)
    .join("");
}

export function table(headers, rows, rawLastColumn = false) {
  return `<table><thead><tr>${headers.map((h) => `<th scope="col">${escapeHTML(h)}</th>`).join("")}</tr></thead><tbody>${
    rows.map((row) => `<tr>${row.map((value, index) => {
      if (rawLastColumn && index === row.length - 1) return `<td>${value}</td>`;
      return `<td class="${typeof value === "number" ? "numeric" : ""}">${escapeHTML(formatValue(value))}</td>`;
    }).join("")}</tr>`).join("") || `<tr><td colspan="${headers.length}">No results.</td></tr>`
  }</tbody></table>`;
}

export function formatValue(value) {
  if (value === null || value === undefined || value === "") return "Unknown";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return value.toLocaleString(undefined, Number.isInteger(value) ? {} : { maximumSignificantDigits: 6 });
  return String(value);
}

export function renderDetailRows(target, rows) {
  document.getElementById(target).innerHTML = `<dl class="detail-list">${rows.map(([label, value]) =>
    `<div><dt>${escapeHTML(label)}</dt><dd>${escapeHTML(formatValue(value))}</dd></div>`
  ).join("")}</dl>`;
}
