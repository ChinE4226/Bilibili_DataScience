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
