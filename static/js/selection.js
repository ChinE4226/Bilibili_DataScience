export function selectionPayload() {
  const kind = document.getElementById("selection-kind").value;
  if (kind === "position") {
    return {
      kind,
      start: document.getElementById("position-start").value,
      end: document.getElementById("position-end").value
    };
  }
  if (kind === "published") {
    return {
      kind,
      start_time: document.getElementById("published-start").value,
      end_time: document.getElementById("published-end").value
    };
  }
  return {
    kind,
    metric: document.getElementById("metric-field").value,
    minimum: document.getElementById("metric-min").value,
    maximum: document.getElementById("metric-max").value
  };
}

export function restoreSelection(selection) {
  const fields = { kind: 'selection-kind', start: 'position-start', end: 'position-end',
    start_time: 'published-start', end_time: 'published-end', metric: 'metric-field',
    minimum: 'metric-min', maximum: 'metric-max' };
  for (const [key, id] of Object.entries(fields)) {
    if (selection[key] == null) continue;
    const control = document.getElementById(id);
    control.value = selection[key];
    control.dispatchEvent(new Event('change', { bubbles: true }));
  }
}
