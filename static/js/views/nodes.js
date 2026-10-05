import { getJSON, postJSON } from '../api.js';
import { bindAction, performAction, escapeHTML, table, preservePageHeight } from '../ui.js';
import { uiState } from '../state.js';
import { cohortTables } from './weekly.js';

const el = id => document.getElementById(id);
let snapshot, shownTask;

function renderFetchHint() {
  if (!snapshot) return;
  const ready = snapshot.nodes.filter(node => snapshot.running && node.status === 'idle' && node.capabilities.includes('selection') && (node.capabilities.includes('pacing') || uiState.requestFrequency >= 4));
  const mode = el('fetch-source').value;
  let message;
  if (mode === 'local') message = 'This Mac will fetch the dataset. Analysis uses the same working dataset.';
  else if (mode === 'parallel') {
    const participating = snapshot.nodes.filter(node => snapshot.running && node.status === 'idle' && node.capabilities.includes('videos') && node.capabilities.includes('pacing'));
    message = participating.length ? `Parallel fetching: this Mac + ${participating.map(node => node.name).join(', ')} share video details. Pacing is divided across participating Macs.` : 'Parallel fetching needs a ready node running the latest source. Sync, restart and re-pair its node app.';
  }
  else if (mode === 'remote') message = ready.length ? `Connected-node fetching: ${ready.map(node => node.name).join(', ')} ready.` : 'Connected-node fetching requires a ready node. Connect or resume a node in Workspace → Nodes.';
  else if (el('selection-kind').value === 'position' && Number(el('position-end').value) - Number(el('position-start').value) + 1 > 500)
    message = 'Automatic fetching: this Mac will fetch. Number ranges above 500 valid videos exceed the node limit.';
  else if (ready.length && snapshot.tasks.length < 30)
    message = `Automatic fetching: ${ready.map(node => node.name).join(', ')} ready. A node will fetch and this Mac will analyse the same dataset.`;
  else message = 'Automatic fetching: this Mac will fetch because no compatible node is available. An available node will be used on a later fetch.';
  el('fetch-node-status').textContent = message;
}

export function syncNodeControls() {
  const busy = uiState.actionBusy;
  el('start-node-service').disabled = busy || Boolean(snapshot?.running);
  el('stop-node-service').disabled = busy || !snapshot?.running;
  el('new-node-pairing').disabled = busy || !snapshot?.running;
  el('copy-node-pairing').disabled = busy || !snapshot?.pairing;
  el('node-service-port').disabled = busy || Boolean(snapshot?.running);
}

function render(data) {
  const selected = new Set([...document.querySelectorAll('[data-node-target]:checked')].map(input => input.value));
  const focused = document.activeElement?.dataset.nodeTarget;
  if (document.querySelector('main').dataset.activePanel === 'nodes') preservePageHeight();
  snapshot = data;
  el('node-service-status').textContent = data.running
    ? data.addresses?.length === 0 ? 'Thunderbolt address unavailable. Reconnect the cable; if its IP changed, stop and start node connections.'
      : `Thunderbolt node connection service is running on port ${data.port}.`
    : 'Connections are stopped.';
  el('node-connection-info').hidden = !data.running;
  const connections = data.addresses || data.urls.map(url => ({url, label: url.includes('127.0.0.1') ? 'This Mac' : 'Other Macs'}));
  const addresses = connections.map(({url, label}) => `<div><span class="muted">${escapeHTML(label)}</span> <code>${escapeHTML(url)}</code> <button type="button" data-copy-node-url="${escapeHTML(url)}">Copy address</button></div>`).join('');
  if (el('node-service-addresses').innerHTML !== addresses) el('node-service-addresses').innerHTML = addresses;
  renderFetchHint();
  el('node-pair-code').value = data.pairing?.code || '';
  el('node-pairing-expiry').textContent = data.pairing ? `Code expires ${new Date(data.pairing.expires_at).toLocaleTimeString()}. It pairs one Mac; create another code for the next Mac.` : 'Create a new pairing code to connect another Mac.';
  el('nodes-list').innerHTML = data.nodes.length ? table(['Target','Mac','Status','Last seen','Progress','Message','Controls'], data.nodes.map(node => [
    '', node.name, node.status, new Date(node.last_seen).toLocaleTimeString(), `${node.progress}%`, node.message,
    `<div class="node-row-actions"><button data-node-id="${node.id}" data-node-action="${node.enabled && node.ready ? 'pause' : 'resume'}">${node.enabled && node.ready ? 'Pause' : 'Resume'}</button><button data-node-id="${node.id}" data-node-action="remove">Remove</button></div>`
  ]), true) : '<p class="empty-state">No nodes paired.</p>';
  // The table helper only allows HTML in its final column; target controls are inserted separately.
  data.nodes.forEach((node, index) => {
    const cell = el('nodes-list').querySelectorAll('tbody tr')[index]?.firstElementChild;
    if (cell) cell.innerHTML = `<input type="checkbox" class="node-target" data-node-target="${node.id}" value="${node.id}" aria-label="Target ${escapeHTML(node.name)}" ${selected.has(node.id) ? 'checked' : ''}>`;
  });
  if (focused) document.querySelector(`[data-node-target="${focused}"]`)?.focus({preventScroll:true});
  el('node-tasks-list').innerHTML = data.tasks.length ? table(['Task','State','Work units','Valid / requested','Invalid','Progress','Controls'], data.tasks.map(task => [
    task.label, task.state, `${task.done}/${task.units}`, `${task.included}/${task.requested}`, task.invalid, `${task.progress}%`,
    `<div class="node-row-actions"><button data-task-id="${task.id}" data-task-action="view">View results</button>${['queued','running'].includes(task.state) ? `<button data-task-id="${task.id}" data-task-action="cancel">Cancel</button>` : ''}</div>`
  ]), true) : '<p class="empty-state">No tasks queued.</p>';
  if (shownTask && !data.tasks.some(task => task.id === shownTask)) {
    shownTask = null;
    el('nodes-result').innerHTML = '<p class="empty-state">This task was cleared from memory.</p>';
  }
  syncNodeControls();
}

export async function refreshNodes() {
  try {
    render(await getJSON('/api/nodes'));
    el('nodes-feedback').hidden = true;
  } catch (error) {
    el('nodes-feedback').textContent = error.message;
    el('nodes-feedback').hidden = false;
  }
}

async function showResult(id) {
  const data = await getJSON(`/api/nodes/result?id=${encodeURIComponent(id)}`);
  shownTask = id;
  preservePageHeight();
  el('nodes-result').innerHTML = `<h3>${escapeHTML(data.task.label)}</h3>
    <p>${escapeHTML(data.task.state)} · ${data.counts.included}/${data.task.requested} valid videos · ${data.task.invalid} invalid videos skipped · ${data.task.shortfall} fewer than requested so far.</p>
    <p class="muted">Collected ${escapeHTML(new Date(data.started_at).toLocaleString())} – ${escapeHTML(new Date(data.collected_at).toLocaleString())}. Nodes: ${escapeHTML(data.nodes.join(', ') || 'Waiting for results')}.</p>
    ${data.task.error ? `<p class="error-message">${escapeHTML(data.task.error)}</p>` : ''}
    ${cohortTables(data)}<p class="muted">These averages describe the received videos and their current accumulated metrics. Partial results are retained if a task fails or is canceled. The creator working dataset is kept separately. Reopen View results to see the latest completed work units.</p>`;
}

export function setupNodes() {
  ['fetch-source', 'selection-kind', 'position-start', 'position-end'].forEach(id => el(id).addEventListener('change', renderFetchHint));
  const mutate = async (path, data) => { await postJSON(path, data); await refreshNodes(); };
  bindAction('start-node-service', () => mutate('/api/nodes/service', {action:'start', port:el('node-service-port').value}), syncNodeControls);
  bindAction('stop-node-service', () => mutate('/api/nodes/service', {action:'stop'}), syncNodeControls);
  bindAction('new-node-pairing', () => mutate('/api/nodes/pairing', {}), syncNodeControls);
  bindAction('copy-node-pairing', async () => {
    if (!snapshot?.pairing) throw Error('Create a new pairing code first.');
    await navigator.clipboard.writeText(snapshot.pairing.code);
  }, syncNodeControls, {showProgress:false, disableAll:false});
  bindAction('queue-node-task', () => mutate('/api/nodes/tasks', {
    kind:el('node-task-kind').value, videos:el('node-task-videos').value, uid:el('node-task-uid').value,
    count:el('node-task-count').value, start:el('node-task-start').value,
    targets:[...document.querySelectorAll('[data-node-target]:checked')].map(input => input.value)
  }), syncNodeControls);
  bindAction('clear-node-tasks', () => mutate('/api/nodes/tasks/action', {action:'clear'}), syncNodeControls);
  el('node-task-kind').addEventListener('change', () => {
    preservePageHeight();
    const creator = el('node-task-kind').value === 'creator';
    el('node-task-videos-source').hidden = creator;
    el('node-task-creator-source').hidden = !creator;
    el('node-creator-scope').hidden = !creator;
  });
  el('panel-nodes').addEventListener('click', event => {
    const address = event.target.closest('button[data-copy-node-url]');
    if (address) {
      performAction(address, () => navigator.clipboard.writeText(address.dataset.copyNodeUrl), {showProgress:false, disableAll:false}).finally(syncNodeControls);
      return;
    }
    const button = event.target.closest('button[data-node-action], button[data-task-action]');
    if (!button) return;
    performAction(button, async () => {
      if (button.dataset.nodeAction) await mutate('/api/nodes/action', {id:button.dataset.nodeId, action:button.dataset.nodeAction});
      else if (button.dataset.taskAction === 'view') await showResult(button.dataset.taskId);
      else await mutate('/api/nodes/tasks/action', {id:button.dataset.taskId, action:button.dataset.taskAction});
    }).finally(syncNodeControls);
  });
  setInterval(() => {
    if (['nodes', 'videos', 'tasks'].includes(document.querySelector('main').dataset.activePanel) && !uiState.actionBusy) refreshNodes();
  }, 3000);
  refreshNodes();
}
