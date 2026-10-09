import { getJSON, postJSON } from '../api.js';
import { bindAction, escapeHTML, performAction, table } from '../ui.js';

let enabled = false, loading = false, selectedBvid = null, analysis = null;
let analysisRequest = 0;
const dateFormat = new Intl.DateTimeFormat('en-GB', {timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'});
const date = value => value ? dateFormat.format(new Date(value)) : null;
const feedback = message => { document.getElementById('tracking-feedback').textContent = message; };
const count = (value, label, plural = `${label}s`) => `${value} ${value === 1 ? label : plural}`;
const cells = values => values.map(value => value == null ? '—' : value);
const minutes = id => {
  const value = Number(document.getElementById(id).value);
  if (!Number.isInteger(value) || value < 1 || value > 10080) throw Error('Use an interval of 1–10080 whole minutes.');
  return value * 60;
};

export function configureTracking(version) {
  enabled = version >= 2;
  for (const id of ['tracking-start', 'tracking-watch-creator', 'tracking-show-history', 'tracking-refresh', 'tracking-backup'])
    document.getElementById(id).disabled = !enabled;
  if (!enabled) feedback('Restart the main app to enable the separate tracking workflow.');
}

function renderChart() {
  const container = document.getElementById('tracking-chart');
  container.hidden = !analysis?.points.length;
  if (container.hidden) return;
  const field = document.getElementById('tracking-chart-mode').value;
  const points = analysis.points;
  const values = points.map(point => point[field]).filter(value => value != null);
  if (!values.length) { container.innerHTML = '<p class="empty-state">Two adjacent valid observations are needed for a rate chart.</p>'; return; }
  const start = Date.parse(points[0].collected_at), end = Date.parse(points.at(-1).collected_at);
  const minimum = Math.min(0, ...values), maximum = Math.max(...values, minimum + 1);
  const x = point => 80 + (Date.parse(point.collected_at) - start) / Math.max(1, end - start) * 750;
  const y = value => 240 - (value - minimum) / (maximum - minimum) * 210;
  let segments = '', connected = false;
  for (const point of points) {
    if (point[field] == null) { connected = false; continue; }
    segments += `${connected ? 'L' : 'M'}${x(point).toFixed(2)},${y(point[field]).toFixed(2)} `;
    connected = true;
  }
  const label = `${analysis.metric} · ${field === 'value' ? 'observed count' : 'change per hour'}`;
  container.innerHTML = `<svg viewBox="0 0 900 310" role="img" aria-label="${escapeHTML(label)} over collection time">
    <title>${escapeHTML(label)} over collection time</title><path d="M80,30 V240 H830" fill="none" stroke="var(--line)"/>
    <path d="${segments}" fill="none" stroke="currentColor" stroke-width="2"/>
    ${points.filter(point => point[field] != null).map(point => `<circle cx="${x(point)}" cy="${y(point[field])}" r="3" fill="currentColor"><title>${escapeHTML(date(point.collected_at))}: ${point[field]}</title></circle>`).join('')}
    <text x="75" y="35" text-anchor="end">${escapeHTML(maximum.toLocaleString(undefined,{maximumFractionDigits:1}))}</text>
    <text x="75" y="245" text-anchor="end">${escapeHTML(minimum.toLocaleString(undefined,{maximumFractionDigits:1}))}</text>
    <text x="80" y="270">${escapeHTML(date(points[0].collected_at))}</text>
    <text x="830" y="270" text-anchor="end">${escapeHTML(date(points.at(-1).collected_at))}</text>
    <text x="450" y="298" text-anchor="middle">Collection time · Beijing · ${escapeHTML(label)}</text></svg>`;
}

async function showHistory(value, { reveal = false } = {}) {
  const request = ++analysisRequest;
  const metric = document.getElementById('tracking-metric').value;
  const bvid = encodeURIComponent(value);
  const [result, history] = await Promise.all([getJSON(`/api/tracking/analysis?bvid=${bvid}&metric=${metric}`), getJSON(`/api/tracking/history?bvid=${bvid}`)]);
  if (request !== analysisRequest) return;
  analysis = result;
  selectedBvid = result.bvid;
  const summary = result.summary;
  document.getElementById('tracking-history-title').textContent = `Tracking analysis · ${result.bvid}`;
  document.getElementById('tracking-history-summary').textContent = `${result.points.length} of ${summary.observations} observations shown · ${metric} · ${summary.missing_observations} unavailable · ${summary.counter_decreases} counter decreases · Beijing time. Dataset snapshots are excluded.`;
  document.getElementById('tracking-analysis-summary').innerHTML = table(
    ['Baseline', 'Latest', 'Net change', 'Elapsed · hours', 'Average change/hour', 'Latest interval change/hour'],
    [cells([summary.baseline_value, summary.latest_value, summary.net_change, summary.elapsed_hours, summary.average_per_hour, summary.latest_per_hour])]);
  document.getElementById('tracking-history').innerHTML = table(
    ['Collected · Beijing', 'Video age · hours', 'Observed count', 'Interval · hours', 'Change', 'Change/hour', 'Growth · %', 'Rate change', 'Note'],
    [...result.points].reverse().map(point => cells([date(point.collected_at), point.video_age_hours, point.value, point.interval_hours, point.delta, point.rate_per_hour, point.growth_percent, point.rate_change_per_hour,
      point.counter_decreased ? 'Counter decreased' : point.value == null ? 'Unavailable' : point.delta == null ? 'No comparison' : 'Observed'])));
  renderChart();
  const link = document.getElementById('tracking-export');
  link.href = `/api/tracking/export?bvid=${encodeURIComponent(result.bvid)}`;
  link.download = `${result.bvid}-observations.csv`;
  link.hidden = false;
  document.getElementById('tracking-errors').hidden = !history.errors.length;
  document.getElementById('tracking-errors-result').innerHTML = table(['Attempted · Beijing', 'Source', 'Reason'], history.errors.map(row => [date(row.attempted_at), row.source, row.message]));
  if (reveal && document.querySelector('main').dataset.activePanel === 'tracking')
    document.getElementById('tracking-history-title').scrollIntoView({behavior:'smooth',block:'start'});
}

export async function refreshTracking() {
  if (!enabled || loading) return;
  loading = true;
  try {
    const data = await getJSON('/api/tracking');
    document.getElementById('tracking-database-path').textContent = data.path;
    document.getElementById('tracking-summary').textContent = `${count(data.counts.trackers, 'video tracker')} · ${count(data.counts.creator_watches, 'creator watch', 'creator watches')} · ${count(data.counts.observations, 'tracking observation')}`;
    document.getElementById('tracking-saved-videos').innerHTML = data.videos.map(row => `<option value="${escapeHTML(row.bvid)}">${escapeHTML(row.title || row.bvid)}</option>`).join('');
    document.getElementById('tracking-creators').innerHTML = table(
      ['Creator', 'UID', 'Status', 'Discovery · min', 'New videos · min', 'Baseline · Beijing', 'Next check · Beijing', 'Last error', 'Actions'],
      data.creator_watches.map(row => [row.label, row.uid, row.status, row.interval_seconds / 60, row.video_interval_seconds / 60, date(row.baseline_at) || 'Awaiting first scan', date(row.next_check_at) || 'Paused', row.last_error || '—',
        `<button data-watch-id="${row.id}" data-watch-status="${row.status === 'active' ? 'paused' : 'active'}">${row.status === 'active' ? 'Pause' : 'Resume'}</button><button data-watch-check="${row.id}">Check releases now</button>`]), true);
    document.getElementById('tracking-releases').innerHTML = table(['Creator', 'Title', 'BVID', 'Detected · Beijing', 'Action'],
      data.releases.map(row => [row.label, row.title, row.bvid, date(row.discovered_at), `<button data-history-bvid="${escapeHTML(row.bvid)}">Analyze</button>`]), true);
    document.getElementById('tracking-trackers').innerHTML = table(
      ['Video', 'BVID', 'Status', 'Interval · min', 'Views', 'Last observation · Beijing', 'Next check · Beijing', 'Last error', 'Actions'],
      data.trackers.map(row => [row.title || 'Awaiting baseline', row.bvid, row.status, row.interval_seconds / 60, row.views, date(row.collected_at) || 'No observation yet', date(row.next_check_at) || 'Paused', row.last_error || '—',
        `<button data-tracker-id="${row.id}" data-tracker-status="${row.status === 'active' ? 'paused' : 'active'}">${row.status === 'active' ? 'Pause' : 'Resume'}</button><button data-check-tracker="${row.id}" data-bvid="${escapeHTML(row.bvid)}">Check now</button><button data-history-bvid="${escapeHTML(row.bvid)}">Analyze</button>`]), true);
    document.getElementById('tracking-videos').innerHTML = table(['Video', 'BVID', 'Creator', 'Views', 'Latest observation · Beijing', 'Action'],
      data.videos.map(row => [row.title, row.bvid, row.creator_name, row.views, date(row.collected_at), `<button data-history-bvid="${escapeHTML(row.bvid)}">Analyze</button>`]), true);
    if (selectedBvid) await showHistory(selectedBvid);
  } finally { loading = false; }
}

export function setupTracking() {
  bindAction('tracking-start', async () => {
    const data = await postJSON('/api/tracking/trackers', {video:document.getElementById('tracking-video').value, interval_seconds:minutes('tracking-interval')});
    feedback(`Monitoring ${data.tracker.bvid}. The first observation is due now; later checks use this schedule.`);
    await showHistory(data.tracker.bvid);
    await refreshTracking();
  });
  bindAction('tracking-watch-creator', async () => {
    const data = await postJSON('/api/tracking/creators', {creator:document.getElementById('tracking-creator').value, interval_seconds:minutes('tracking-release-interval'), video_interval_seconds:minutes('tracking-new-video-interval')});
    feedback(`Watching creator ${data.watch.uid}. First scan establishes a baseline; later new releases start video tracking.`);
    await refreshTracking();
  });
  bindAction('tracking-show-history', () => showHistory(document.getElementById('tracking-video').value, {reveal:true}));
  bindAction('tracking-refresh', refreshTracking);
  bindAction('tracking-backup', async () => { const data = await postJSON('/api/tracking/backup', {}); feedback(`Database backup saved: ${data.path}`); });
  document.getElementById('tracking-metric').addEventListener('change', () => { if (selectedBvid) showHistory(selectedBvid).catch(error => feedback(error.message)); });
  document.getElementById('tracking-chart-mode').addEventListener('change', renderChart);
  document.getElementById('panel-tracking').addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button || button.disabled) return;
    if (button.dataset.historyBvid) performAction(button, async () => { document.getElementById('tracking-video').value = button.dataset.historyBvid; await showHistory(button.dataset.historyBvid, {reveal:true}); });
    else if (button.dataset.trackerStatus) performAction(button, async () => {
      await postJSON('/api/tracking/update', {tracker_id:Number(button.dataset.trackerId), status:button.dataset.trackerStatus});
      await refreshTracking();
      feedback(button.dataset.trackerStatus === 'paused' ? 'Video tracking paused. A running check may finish.' : 'Video tracking resumed. Next check is due now.');
    });
    else if (button.dataset.checkTracker) performAction(button, async () => {
      await postJSON('/api/tracking/check', {tracker_id:Number(button.dataset.checkTracker)});
      await showHistory(button.dataset.bvid); await refreshTracking(); feedback('Tracking observation saved. Loaded datasets were not changed.');
    });
    else if (button.dataset.watchStatus) performAction(button, async () => {
      await postJSON('/api/tracking/creators/update', {watch_id:Number(button.dataset.watchId), status:button.dataset.watchStatus});
      await refreshTracking(); feedback('Creator discovery schedule updated. Video trackers keep their own schedules.');
    });
    else if (button.dataset.watchCheck) performAction(button, async () => {
      const result = await postJSON('/api/tracking/creators/check', {watch_id:Number(button.dataset.watchCheck)});
      await refreshTracking(); feedback(result.baseline ? 'Existing uploads recorded as the release baseline.' : `Detected ${count(result.releases.length, 'new release')}. Video trackers are ready.`);
    });
  });
  setInterval(() => {
    if (document.querySelector('main').dataset.activePanel === 'tracking' && !document.hidden && document.documentElement.dataset.actionBusy !== 'true') refreshTracking().catch(error => feedback(error.message));
  }, 5000);
}
