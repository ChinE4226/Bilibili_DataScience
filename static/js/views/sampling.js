import { postJSON } from "../api.js";
import { escapeHTML, preservePageHeight } from "../ui.js";
import { startProgressPolling, stopProgressPolling } from "../progress.js";
import { cohortTables } from "./weekly.js";
import { registerCollection } from '../collections.js';
import { renderSnapshotChoice } from '../snapshot-choice.js';

const fields = { keyword: "keyword", order: "order", sample_size: "size", pool_size: "pool-size",
  published_start: "published-start", published_end: "published-end", metric: "metric",
  minimum: "minimum", maximum: "maximum", category_id: "category-id", seed: "seed" };
const orders = { pubdate: "Newest first", totalrank: "Search relevance", click: "Most viewed" };

export function setupSampling() {
  const tabs = [...document.querySelectorAll("[data-sampling-mode]")];
  function select(tab) {
    preservePageHeight();
    for (const item of tabs) {
      const selected = item === tab;
      item.setAttribute("aria-selected", String(selected));
      item.tabIndex = selected ? 0 : -1;
      document.getElementById(`sampling-${item.dataset.samplingMode}`).hidden = !selected;
    }
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => select(tab));
    tab.addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === "Home" ? tabs[0] : event.key === "End" ? tabs.at(-1)
        : tabs[(index + (event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
      if (next.disabled) return;
      select(next);
      next.focus();
    });
  });
}

export function renderRandomSample(data) {
  registerCollection(data.dataset);
  document.getElementById('sample-result').dataset.collectionId = data.dataset?.collection_id || '';
  const s = data.sampling;
  const scope = [`Keyword: ${s.keyword}`, `Order: ${orders[s.order]}`, `Candidate limit: ${s.pool_size}`,
    `Published: ${s.published_start || "any start"} through ${s.published_end || "any end"} (Beijing time)`,
    `${s.metric}: ${s.minimum ?? 0}–${s.maximum ?? "unlimited"} (inclusive)`,
    `Category ID: ${s.category_id || "all"}`, `Seed: ${s.seed}`];
  document.getElementById("sample-result").innerHTML = `
    <h3>Random sample · ${escapeHTML(s.keyword)}</h3>
    <p class="muted">${scope.map(escapeHTML).join(" · ")}</p>
    <p class="muted">Collected ${escapeHTML(new Date(data.started_at).toLocaleString())} – ${escapeHTML(new Date(data.collected_at).toLocaleString())}. Metrics reflect this collection time.</p>
    <dl class="plot-summary weekly-summary">${[["Requested videos", s.sample_size], ["Sampled videos", s.sampled], ["Eligible candidates", s.eligible], ["Creators sampled", data.counts.creators]].map(([label, value]) => `<div><dt>${label}</dt><dd>${value.toLocaleString()}</dd></div>`).join("")}</dl>
    <p>${s.candidates} candidate entries · ${s.checked} details checked · ${s.invalid} invalid · ${s.duplicates} duplicates · ${s.filtered_out} outside filters.</p>
    ${renderSnapshotChoice(data.dataset)}
    ${s.shortfall ? `<p role="status">${s.shortfall} fewer videos than requested: the bounded pool contained only ${s.eligible} eligible videos. Increase the candidate limit or broaden the filters for a larger sample.</p>` : ""}
    ${data.dataset ? `<div class="actions"><button type="button" class="primary" data-use-collection="${escapeHTML(data.dataset.collection_id)}">Use in Analysis</button></div>` : ''}
    ${cohortTables(data)}
    <p class="muted">Averages describe the sampled videos from this search pool. Each eligible candidate has the same chance of selection, without replacement. Use in Analysis reuses this sample for charts and ratios. The creator dataset stays available. Collections stay in RAM; the newest four sampling collections are retained.</p>`;
}

export async function fetchRandomSample() {
  const payload = Object.fromEntries(Object.entries(fields).map(([key, id]) => [key, document.getElementById(`sample-${id}`).value]));
  startProgressPolling("Collecting random sample", "sample-progress");
  try {
    renderRandomSample(await postJSON("/api/random-sample", payload));
  } finally {
    await stopProgressPolling();
  }
}
