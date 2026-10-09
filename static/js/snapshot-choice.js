import { getJSON, postJSON } from './api.js';
import { escapeHTML, performAction } from './ui.js';

let enabled = false;
const collections = new Map();
const saved = new Map();
const keyFor = meta => JSON.stringify([meta.collection_id || 'creator', meta.uid == null ? null : String(meta.uid), new Date(meta.collected_at).getTime()]);

export function renderSnapshotChoice(meta) {
  if (!meta?.count) return '';
  const key = keyFor(meta);
  collections.set(key, meta);
  const batch = saved.get(key);
  const quantity = `${meta.count} ${meta.count === 1 ? 'video' : 'videos'}`;
  return `<div class="snapshot-choice" data-snapshot-key="${escapeHTML(key)}">
    <div><strong>${batch ? 'Snapshot saved' : 'Saving is optional'}</strong>
      <p class="muted" role="status">${batch
        ? `Saved the whole collection (${quantity}). Your loaded data is still available for analysis.`
        : `Loaded in RAM: ${quantity}. You can continue without saving.`}</p>
      <p class="muted">${batch ? '' : 'A snapshot includes the whole fetched collection and its original collection time, before local analysis filters.'}</p></div>
    <div class="actions">${batch
      ? '<button type="button" data-panel="snapshots">Browse saved snapshots</button>'
      : `<button type="button" data-save-snapshot ${enabled ? '' : 'disabled'}>Save data as a snapshot</button>`}
      ${meta.collection_id && !meta.mission_id ? `<button type="button" data-release-collection="${escapeHTML(meta.collection_id)}" data-collected-at="${escapeHTML(meta.collected_at)}" title="Discard unsaved rows and derived results. Saved snapshots remain available.">Release from memory</button>` : ''}</div>
  </div>`;
}

export function forgetSnapshotChoices(identity) {
  for (const [key, meta] of collections) {
    if ((meta.collection_id || 'creator') === identity) {
      collections.delete(key);
      saved.delete(key);
    }
  }
}

function updateChoices() {
  document.querySelectorAll('[data-snapshot-key]').forEach(card => {
    const meta = collections.get(card.dataset.snapshotKey);
    if (meta) card.outerHTML = renderSnapshotChoice(meta);
  });
}

export function configureSnapshotChoices(version) {
  enabled = version >= 1;
  updateChoices();
}

export function markSnapshotSaved(meta, batch) {
  if (!meta) return;
  saved.set(keyFor(meta), batch);
  updateChoices();
}

export function syncSnapshotChoices(batches) {
  for (const batch of batches) {
    if (batch.capture_mode !== 'loaded') continue;
    const scope = JSON.parse(batch.scope_json);
    saved.set(keyFor({collection_id: batch.collection_id, uid: batch.source_kind === 'creator' ? scope.uid : null,
      collected_at: batch.collected_at}), batch);
  }
  updateChoices();
}

export async function refreshSnapshotChoices() {
  if (enabled) syncSnapshotChoices((await getJSON('/api/snapshots')).batches || []);
}

export function setupSnapshotChoices() {
  document.addEventListener('click', event => {
    const button = event.target.closest('button[data-save-snapshot]');
    if (!button || button.disabled) return;
    const meta = collections.get(button.closest('[data-snapshot-key]').dataset.snapshotKey);
    performAction(button, async () => {
      const data = await postJSON('/api/snapshots/collection', {
        mode: 'loaded', collection_id: meta.collection_id || 'creator',
        expected_collected_at: meta.collected_at
      });
      markSnapshotSaved(meta, data.batch);
    }).finally(updateChoices);
  });
}
