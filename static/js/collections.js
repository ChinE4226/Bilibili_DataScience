import { getJSON } from './api.js';
import { uiState } from './state.js';
import { escapeHTML, performAction, preservePageHeight } from './ui.js';

const el = id => document.getElementById(id);
let entries = new Map();

export function collectionPayload() {
  const cohort = Boolean(uiState.collectionId);
  return { collection_id: uiState.collectionId || null, local_filter: {
    minimum_views: el(cohort ? 'analysis-min-views' : 'local-min-views').value,
    maximum_views: el(cohort ? 'analysis-max-views' : 'local-max-views').value
  } };
}

function renderChoices() {
  const options = `<option value="">Creator dataset</option>` + [...entries.values()].map(meta =>
    `<option value="${escapeHTML(meta.collection_id)}">${escapeHTML(meta.source_label)} · ${meta.count} videos · ${escapeHTML(new Date(meta.collected_at).toLocaleTimeString())}</option>`).join('');
  const missing = uiState.collectionId && !entries.has(uiState.collectionId);
  el('analysis-collection').innerHTML = options + (missing ? `<option value="${escapeHTML(uiState.collectionId)}">Collection expired · collect again</option>` : '');
  el('analysis-collection').value = uiState.collectionId || '';
  el('analysis-collection').dispatchEvent(new Event('optionschange'));
}

export function registerCollection(meta) {
  if (!meta?.collection_id) return;
  entries.set(meta.collection_id, meta);
  while (entries.size > 4) entries.delete(entries.keys().next().value);
  renderChoices();
  renderAnalysisContext();
}

export async function refreshCollections() {
  const data = await getJSON('/api/collections');
  entries = new Map(data.collections.slice().reverse().map(meta => [meta.collection_id, meta]));
  if (data.creator_dataset) {
    const previous = uiState.creatorDataset;
    recordDataset({ ...data.creator_dataset, ...(previous?.collected_at === data.creator_dataset.collected_at && previous.filter_counts ? {filter_counts: previous.filter_counts} : {}) });
  } else if (uiState.creatorDataset) {
    uiState.creatorDataset = null;
    el('dataset-status').textContent = 'Fetch the selected creator and range to load a dataset.';
    el('dataset-count-flow').hidden = true;
    el('dataset-filter-status').hidden = true;
    el('videos-result').innerHTML = '<p class="empty-state">No dataset loaded for this creator and account.</p>';
    if (!uiState.collectionId) document.dispatchEvent(new Event('analysis-source-changed'));
  }
  renderChoices();
  renderAnalysisContext();
}

function countsLine(meta) {
  const c = meta.collection || {}, f = meta.filter_counts;
  const parts = [];
  if (c.requested != null) parts.push(`${c.requested} requested`);
  if (c.examined != null) parts.push(`${c.examined} ${meta.source_kind === 'random' ? 'candidate entries' : 'checked'}`);
  if (c.eligible != null) parts.push(`${c.eligible} eligible`);
  parts.push(`${meta.count} ${meta.source_kind === 'random' ? 'sampled' : 'valid'}`);
  parts.push(`${f?.included ?? meta.count} after local filters`);
  return parts.join(' → ');
}

function exclusionsLine(meta) {
  const c = meta.collection || {};
  const parts = [`${c.skipped_invalid || 0} invalid`, `${c.skipped_duplicates || 0} duplicates`];
  if (c.collection_filtered != null) parts.push(`${c.collection_filtered} outside collection filters`);
  if (meta.filter_counts) parts.push(`${meta.filter_counts.excluded} excluded by local view filters`);
  if (c.shortfall) parts.push(`${c.shortfall} short of requested count`);
  return parts.join(' · ');
}

export function renderAnalysisContext() {
  const cohort = Boolean(uiState.collectionId);
  let meta = uiState.creatorDataset;
  if (cohort) meta = entries.has(uiState.collectionId) ? uiState.analysisDataset || entries.get(uiState.collectionId) : null;
  el('analysis-cohort-filters').hidden = !cohort;
  el('analysis-creator-filters').hidden = cohort;
  el('analysis-source-help').textContent = cohort
    ? 'Uses collected rows only. Local filters do not recollect or replace the creator dataset. Follower ratios are available on creator datasets.'
    : 'Uses the loaded creator dataset and its local filters. Collection controls stay on Data.';
  el('analysis-dataset-status').textContent = meta
    ? `${meta.source_label || 'Creator dataset'} · ${countsLine(meta)} · collected ${new Date(meta.started_at).toLocaleString()} – ${new Date(meta.collected_at).toLocaleString()}.`
    : cohort ? 'This collection is unavailable. Collect it again on Sampling.' : 'Fetch a creator dataset in Data, or use a sampling result in Analysis.';
  el('analysis-filter-status').hidden = !meta;
  el('analysis-filter-status').textContent = meta ? exclusionsLine(meta) : '';
  el('analysis-provenance').hidden = !meta;
  const scope = meta?.scope || {};
  el('analysis-scope-status').textContent = meta?.source_kind === 'random'
    ? `Search pool: ${scope.keyword} · ${scope.order} · candidate limit ${scope.pool_size} · ${scope.eligible} eligible · published ${scope.published_start || 'any start'} through ${scope.published_end || 'any end'} (Beijing time) · ${scope.metric} ${scope.minimum ?? 0}–${scope.maximum ?? 'unlimited'} · category ${scope.category_id || 'all'} · seed ${scope.seed}. This sample describes the bounded search pool, not all Bilibili videos.`
    : meta?.source_kind === 'weekly' ? `Weekly issue ${scope.number}${scope.subject ? ` · ${scope.subject}` : ''}. This selected popular cohort is not an average across Bilibili. Metrics are accumulated counts observed during collection, not growth earned that week.`
      : `${meta?.selection || ''} · collected on ${meta?.collection?.node_name || 'This Mac'}. Metrics are accumulated counts observed during collection.`;
  for (const id of ['division-numerator', 'division-denominator', 'plot-numerator', 'plot-denominator']) {
    const select = el(id), option = [...select.options].find(option => option.value === 'followers');
    if (option) option.disabled = cohort;
    if (cohort && select.value === 'followers') select.value = id.includes('denominator') ? 'views' : 'likes';
    select.dispatchEvent(new Event('optionschange'));
  }
}

export function recordDataset(meta) {
  if (meta.source_kind === 'weekly' || meta.source_kind === 'random') {
    uiState.analysisDataset = meta;
  } else {
    const previous = uiState.creatorDataset;
    uiState.creatorDataset = meta;
    if (!uiState.collectionId && previous && previous.collected_at !== meta.collected_at) {
      document.dispatchEvent(new Event('analysis-source-changed'));
    }
    const c = meta.collection;
    const details = c ? ` · ${c.examined} checked · ${c.skipped_invalid} invalid skipped${c.skipped_duplicates ? ` · ${c.skipped_duplicates} duplicates skipped` : ''}${c.requested != null ? ` · ${c.requested} requested` : ''}${c.shortfall ? ` · ${c.shortfall} short` : ''}` : '';
    el('dataset-status').textContent = `${meta.reused ? 'Reused' : 'Fetched'} ${meta.count} valid videos${details} · fetched on ${c?.node_name || 'This Mac'} · ${meta.source_label || `Creator ${meta.uid || ''}`} · ${meta.selection} · collected ${new Date(meta.started_at).toLocaleString()} – ${new Date(meta.collected_at).toLocaleString()}. In memory only.`;
    el('dataset-count-flow').textContent = countsLine(meta);
    el('dataset-count-flow').hidden = false;
    const f = meta.filter_counts;
    el('dataset-filter-status').hidden = !f;
    if (f) el('dataset-filter-status').textContent = `${f.fetched} fetched · ${f.included} included · ${f.excluded} excluded · ${exclusionsLine(meta)}.`;
  }
  renderAnalysisContext();
}

export function chooseCollection(identity) {
  if ((uiState.collectionId || '') === identity) return;
  preservePageHeight();
  uiState.collectionId = identity || null;
  uiState.analysisDataset = identity ? entries.get(identity) : null;
  el('analysis-min-views').value = '';
  el('analysis-max-views').value = '';
  el('analysis-collection').value = identity;
  el('analysis-collection').dispatchEvent(new Event('optionschange'));
  const fetch = el('batch-fetch');
  fetch.disabled = Boolean(identity);
  if (identity) {
    fetch.checked = false;
    fetch.dispatchEvent(new Event('change', { bubbles: true }));
  }
  renderAnalysisContext();
  document.dispatchEvent(new Event('analysis-source-changed'));
}

export function setupCollections(onUse) {
  el('analysis-collection').addEventListener('change', () => chooseCollection(el('analysis-collection').value));
  document.addEventListener('click', event => {
    const button = event.target.closest('button[data-use-collection]');
    if (!button) return;
    performAction(button, async () => {
      await refreshCollections();
      const id = button.dataset.useCollection;
      if (!entries.has(id)) throw Error('This collection has expired. Collect it again on Sampling.');
      chooseCollection(id);
      await onUse();
    }).finally(() => document.dispatchEvent(new Event('analysis-source-settled')));
  });
}
