import { uiState } from "./state.js";

export function preservePageHeight() {
  const main = document.querySelector("main");
  // Keep the viewport's bottom reachable before hiding the current content.
  // The floor can shrink again as the user scrolls upward.
  main.style.minHeight = `${Math.max(0, innerHeight - main.getBoundingClientRect().top)}px`;
}

export function setupPageHeight() {
  const main = document.querySelector("main");
  let previousScroll = scrollY;
  window.addEventListener("scroll", () => {
    const currentScroll = scrollY;
    if (currentScroll < previousScroll) {
      const required = Math.max(0, innerHeight - main.getBoundingClientRect().top);
      if (required < parseFloat(main.style.minHeight)) main.style.minHeight = `${required}px`;
    }
    previousScroll = currentScroll;
  }, { passive: true });
}

const feedbackStates = new WeakMap();

export function clearFeedback(feedback) {
  const state = feedbackStates.get(feedback);
  if (state) clearTimeout(state.timer);
  feedbackStates.delete(feedback);
  feedback.hidden = true;
  feedback.setAttribute('role', 'status');
}

export function showFeedback(feedback, message, { error = false, duration = error ? 0 : 4000 } = {}) {
  clearFeedback(feedback);
  feedback.textContent = message;
  feedback.classList.toggle("error-message", error);
  feedback.hidden = false;
  feedback.setAttribute('role', error ? 'alert' : 'status');
  if (error) {
    const dismiss = document.createElement('button');
    dismiss.type = 'button';
    dismiss.className = 'feedback-dismiss';
    dismiss.textContent = 'Dismiss';
    dismiss.addEventListener('click', () => clearFeedback(feedback));
    feedback.append(dismiss);
  }
  const state = { duration, timer: null };
  const schedule = () => {
    clearTimeout(state.timer);
    if (duration > 0) state.timer = setTimeout(() => { if (feedbackStates.get(feedback) === state) clearFeedback(feedback); }, duration);
  };
  if (!feedback.dataset.dismissBound) {
    feedback.dataset.dismissBound = "true";
    feedback.addEventListener("pointerenter", () => clearTimeout(feedbackStates.get(feedback)?.timer));
    feedback.addEventListener("pointerleave", () => {
      const current = feedbackStates.get(feedback);
      if (current) current.schedule();
    });
  }
  state.schedule = schedule;
  feedbackStates.set(feedback, state);
  schedule();
}

export async function performAction(button, task, { showProgress = true, disableAll = true } = {}) {
  if (uiState.actionBusy) return;
  uiState.actionBusy = true;
  document.documentElement.dataset.actionBusy = 'true';
  const feedback = document.getElementById(document.getElementById("creator-menu").hidden ? "page-feedback" : "creator-menu-feedback");
  clearFeedback(feedback);
  feedback.hidden = !showProgress;
  feedback.classList.remove("error-message");
  feedback.textContent = `${button.textContent.trim()}...`;
  const restoreFocus = !disableAll && document.activeElement === button;
  const states = (disableAll ? [...document.querySelectorAll("button:not([data-panel]):not([data-section]):not([data-group]):not(#menu-back):not(#stop-batch)")] : [button])
    .map((item) => [item, item.disabled]);
  states.forEach(([item]) => { item.disabled = true; });
  try {
    await task();
    clearFeedback(feedback);
  } catch (error) {
    showFeedback(feedback, error.message, { error: true });
  } finally {
    states.forEach(([item, disabled]) => { item.disabled = disabled; });
    if (restoreFocus && document.activeElement === document.body && button.isConnected) {
      button.focus({ preventScroll: true });
    }
    uiState.actionBusy = false;
    delete document.documentElement.dataset.actionBusy;
    document.dispatchEvent(new Event('action-settled'));
  }
}

export function bindAction(id, task, onSettled, options) {
  const button = document.getElementById(id);
  button.addEventListener("click", () => performAction(button, task, options).finally(() => onSettled?.()));
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
