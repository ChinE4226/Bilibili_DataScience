import { getJSON, postJSON } from '../api.js';
import { bindAction, escapeHTML, performAction, table } from '../ui.js';
import { selectionPayload } from '../selection.js';
import { startProgressPolling, stopProgressPolling } from '../progress.js';
import { configureSnapshotChoices, setupSnapshotChoices, markSnapshotSaved, syncSnapshotChoices } from '../snapshot-choice.js';

let collectionEnabled = false;
let loading = false;
let collectionEntries = new Map();
let creatorMetadata = null;
const dateFormat = new Intl.DateTimeFormat('en-GB', {timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});
const date = value => value ? dateFormat.format(new Date(value)) : null;
const videoCount = count => `${count} ${count === 1 ? 'video' : 'videos'}`;
const feedback = message => { document.getElementById('snapshot-feedback').textContent = message; };

export function configureSnapshots(version) {
  configureSnapshotChoices(version);
  collectionEnabled = version >= 1;
  document.getElementById('snapshot-refresh').disabled = !collectionEnabled;
  document.getElementById('snapshot-backup').disabled = !collectionEnabled;
  updateSnapshotControls();
}

function updateSnapshotControls() {
  const mode = document.getElementById('snapshot-mode').value;
  const identity = document.getElementById('snapshot-collection').value;
  const meta = identity === 'creator' ? creatorMetadata : collectionEntries.get(identity);
  const button = document.getElementById('snapshot-save-collection');
  document.getElementById('snapshot-configure-creator').hidden = mode !== 'fresh' || identity !== 'creator';
  button.textContent = mode === 'loaded' ? 'Save data as a snapshot' : 'Fetch new data & save as a snapshot';
  button.disabled = !collectionEnabled || (mode === 'loaded' && !meta?.count);
  const help = document.getElementById('snapshot-source-help');
  if (!collectionEnabled) help.textContent = 'Restart the main app to enable whole-collection snapshots.';
  else if (mode === 'loaded') help.textContent = meta
    ? `Save ${videoCount(meta.count)} as fetched at ${date(meta.collected_at)} Beijing time. No network requests; other RAM collections remain temporary. Local analysis filters are not applied.`
    : 'No collection is loaded. Fetch a creator dataset or sample first, or choose Fetch new data.';
  else help.textContent = identity === 'creator'
    ? 'Fetch the creator dataset using the current Data collection controls and save only that new result. Your loaded RAM dataset is preserved.'
    : meta?.source_kind === 'creator' ? 'Fetch this mission creator again using its original collection range and fetching source. Save only the new result; retained mission data stays unchanged.'
      : 'Collect this sample again using its original scope and seed, and save only the new result. Your loaded RAM collections are preserved.';
}

async function showBatch(identity) {
  const data = await getJSON(`/api/snapshots/batch?id=${identity}`);
  document.getElementById('snapshot-batch-detail').hidden = false;
  document.getElementById('snapshot-batch-title').textContent = data.batch.label;
  document.getElementById('snapshot-batch-summary').textContent =
    `${data.videos.length} of ${data.batch.video_count} videos shown · ${data.batch.capture_mode === 'loaded' ? 'Saved fetched data' : 'Fetched new data'} · collected ${date(data.batch.collected_at)} · saved ${date(data.batch.saved_at)} Beijing time`;
  document.getElementById('snapshot-batch-rows').innerHTML = table(
    ['Title', 'BVID', 'Views', 'Likes', 'Coins', 'Favorites', 'Replies', 'Shares', 'Danmaku'],
    data.videos.map(row => [row.title, row.bvid, row.views, row.likes, row.coins, row.favorites, row.replies, row.shares, row.danmaku])
  );
  const link = document.getElementById('snapshot-batch-export');
  link.href = `/api/snapshots/export?id=${identity}`;
  link.download = `collection-snapshot-${identity}.csv`;
}

export async function refreshSnapshots() {
  if (!collectionEnabled || loading) return;
  loading = true;
  try {
    const data = await getJSON('/api/snapshots');
    syncSnapshotChoices(data.batches || []);

    const collections = await getJSON('/api/collections');
    creatorMetadata = collections.creator_dataset;
    collectionEntries = new Map(collections.collections.map(meta => [meta.collection_id, meta]));
    const select = document.getElementById('snapshot-collection');
    const previous = select.value;
    select.innerHTML = `<option value="creator">Creator dataset${creatorMetadata ? ` · ${videoCount(creatorMetadata.count)}` : ' · not loaded'}</option>` +
      collections.collections.map(meta => `<option value="${escapeHTML(meta.collection_id)}">${escapeHTML(meta.source_label)} · ${videoCount(meta.count)}</option>`).join('');
    select.value = previous === 'creator' || collectionEntries.has(previous) ? previous : 'creator';
    select.dispatchEvent(new Event('optionschange'));
    updateSnapshotControls();
    document.getElementById('snapshot-batches').innerHTML = table(
      ['Collection', 'Videos', 'Mode', 'Collected · Beijing', 'Saved · Beijing', 'Action'],
      (data.batches || []).map(batch => [batch.label, batch.video_count, batch.capture_mode === 'loaded' ? 'Fetched data' : 'New fetch',
        date(batch.collected_at), date(batch.saved_at), `<button type="button" data-snapshot-batch="${batch.id}">View collection</button>`]), true
    );

    document.getElementById('snapshot-database-path').textContent = data.path;
  } finally { loading = false; }
}

export function setupSnapshots() {
  setupSnapshotChoices();
  document.getElementById('snapshot-mode').addEventListener('change', updateSnapshotControls);
  document.getElementById('snapshot-collection').addEventListener('change', updateSnapshotControls);
  bindAction('snapshot-save-collection', async () => {
    const mode = document.getElementById('snapshot-mode').value;
    const payload = { mode, collection_id: document.getElementById('snapshot-collection').value };
    const meta = payload.collection_id === 'creator' ? creatorMetadata : collectionEntries.get(payload.collection_id);
    if (mode === 'loaded') payload.expected_collected_at = meta?.collected_at;
    if (mode === 'fresh' && payload.collection_id === 'creator') {
      payload.selection = selectionPayload();
      payload.fetch_source = document.getElementById('fetch-source').value;
    }
    if (mode === 'fresh') startProgressPolling('Fetching a new collection for a snapshot', 'snapshot-collection-progress');
    try {
      const data = await postJSON('/api/snapshots/collection', payload);
      if (mode === 'loaded') markSnapshotSaved(meta, data.batch);
      await showBatch(data.batch.id);
      await refreshSnapshots();
      feedback(`Saved the whole collection: ${videoCount(data.batch.video_count)} from ${data.batch.label}. Other RAM data was not saved.`);
    } finally {
      if (mode === 'fresh') await stopProgressPolling();
    }
  }, updateSnapshotControls);
  bindAction('snapshot-refresh', refreshSnapshots);
  bindAction('snapshot-backup', async () => {
    const data = await postJSON('/api/snapshots/backup', {});
    feedback(`Database backup saved: ${data.path}`);
  });
  document.getElementById('panel-snapshots').addEventListener('click', event => {
    const button = event.target.closest('button[data-snapshot-batch]');
    if (button && !button.disabled) performAction(button, () => showBatch(Number(button.dataset.snapshotBatch)), {disableAll:false});
  });
  setInterval(() => {
    if (document.querySelector('main').dataset.activePanel === 'snapshots' && !document.hidden && document.documentElement.dataset.actionBusy !== 'true')
      refreshSnapshots().catch(error => feedback(error.message));
  }, 5000);
}
