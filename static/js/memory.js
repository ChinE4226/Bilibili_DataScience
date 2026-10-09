import { getJSON } from './api.js';
import { table } from './ui.js';
import { uiState } from './state.js';

const el = id => document.getElementById(id);
let enabled = false, loading = false;
const bytes = value => {
  if (value == null) return 'Unavailable';
  const unit = value < 1024 ? 'B' : value < 1048576 ? 'KiB' : 'MiB';
  const divisor = unit === 'B' ? 1 : unit === 'KiB' ? 1024 : 1048576;
  return `${(value / divisor).toLocaleString(undefined, {maximumFractionDigits: 1})} ${unit}`;
};

function setSummary(text, description) {
  el('memory-summary').textContent = text;
  const summary = el('memory-panel').querySelector('summary');
  summary.title = description;
  summary.setAttribute('aria-label', description);
}

function positionMemory() {
  if (!el('memory-panel').open) return;
  const top = document.querySelector('.global-navigation').getBoundingClientRect().bottom + 8;
  el('memory-panel').style.setProperty('--memory-panel-top', `${top}px`);
}

export async function refreshMemory() {
  if (!enabled || loading) return;
  loading = true;
  try {
    const data = await getJSON('/api/memory');
    setSummary(bytes(data.server.rss_bytes), `Software memory: server ${bytes(data.server.rss_bytes)} · ${data.retained_videos.toLocaleString()} retained videos. Open for details.`);
    el('memory-server').textContent = bytes(data.server.rss_bytes);
    el('memory-datasets').textContent = `≈ ${bytes(data.dataset_estimated_bytes)}`;
    el('memory-collections').textContent = data.collections.length.toLocaleString();
    const heap = performance.memory?.usedJSHeapSize;
    el('memory-browser').textContent = bytes(Number.isFinite(heap) && heap >= 0 ? heap : null);
    el('memory-time').textContent = `Server PID ${data.server.pid} · updated ${new Date(data.server.sampled_at).toLocaleTimeString()} · refreshes every 10 seconds while this tab is visible.`;
    el('memory-retained').innerHTML = data.collections.length
      ? table(['Loaded collection', 'Type', 'Videos', 'Estimated dataset RAM'], data.collections.map(row => [row.label, row.kind, row.videos, `≈ ${bytes(row.estimated_bytes)}`]))
      : '<p class="empty-state">No datasets retained in server memory.</p>';
    const c = data.cache_counts;
    el('memory-caches').textContent = `${c.missions} missions · ${c.unsaved_charts} temporary chart exports · ${c.node_tasks} node tasks. Their results and runtime buffers are included in server RAM.`;
    el('memory-nodes').innerHTML = data.nodes.length
      ? table(['Fetching node', 'Process RAM (RSS)', 'Received'], data.nodes.map(node => [node.name,
        node.rss_bytes == null ? 'Unavailable' : `${bytes(node.rss_bytes)}${node.stale ? ' · last reported' : ''}`,
        node.sampled_at ? new Date(node.sampled_at).toLocaleTimeString() : 'No measurement']))
      : '<p class="muted">No fetching nodes paired.</p>';
    el('memory-error').hidden = true;
  } catch (error) {
    setSummary('Unavailable', 'Software memory measurement unavailable. Open for details.');
    el('memory-error').textContent = `Memory status could not be updated: ${error.message}`;
    el('memory-error').hidden = false;
  } finally {
    loading = false;
  }
}

export function configureMemory(version) {
  enabled = version >= 1;
  el('memory-refresh').disabled = !enabled;
  if (enabled) refreshMemory();
  else setSummary('Restart required', 'Restart the server to enable software memory measurements.');
}

export function setupMemory() {
  el('memory-refresh').addEventListener('click', refreshMemory);
  const panel = el('memory-panel');
  panel.addEventListener('toggle', () => {
    if (panel.open) { positionMemory(); refreshMemory(); }
  });
  window.addEventListener('resize', positionMemory);
  document.addEventListener('click', event => {
    if (panel.open && !panel.contains(event.target)) panel.open = false;
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && panel.open) {
      panel.open = false;
      panel.querySelector('summary').focus();
    }
  });
  document.addEventListener('collections-released', refreshMemory);
  document.addEventListener('analysis-source-settled', refreshMemory);
  document.addEventListener('action-settled', refreshMemory);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refreshMemory(); });
  setInterval(() => { if (!document.hidden && !uiState.actionBusy) refreshMemory(); }, 10000);
}
