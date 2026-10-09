import { getJSON, postJSON } from './api.js';
import { bindAction, escapeHTML, fillOptions, performAction, table } from './ui.js';
import { uiState } from './state.js';
import { metricFields, divisionFields } from './constants.js';
import { refreshCollections } from './collections.js';

const el = id => document.getElementById(id);
const labels = {fetch:'Fetch',snapshot:'Save snapshot',analysis:'Analyze',plot:'Plot',division:'Calculate ratio'};
let enabled = false, busy = false, queue = [], available = [], onResult;
let creatorChoicesInitialized = false;
const option = (value,label) => `<option value="${escapeHTML(value)}">${escapeHTML(label)}</option>`;

function setOptions(id, options, fallback) {
  const select=el(id), previous=select.value;
  select.innerHTML=options;
  select.value=[...select.options].some(item=>item.value===previous)?previous:fallback;
  select.dispatchEvent(new Event('optionschange'));
}

function syncBuilder() {
  el('mission-fetch-settings').hidden=el('mission-source').value!=='fetch';
  el('mission-manual-creator').hidden=el('mission-creator').value!=='manual';
  for(const kind of ['position','published','metric']) el(`mission-range-${kind}`).hidden=el('mission-selection-kind').value!==kind;
  el('mission-plot-settings').hidden=!el('mission-plot').checked;
  el('mission-ratio-settings').hidden=!el('mission-division').checked&&!(el('mission-plot').checked&&el('mission-plot-mode').value==='quotient');
  const meta=available.find(row=>row.collection_id===el('mission-source').value);
  const sample=['weekly','random'].includes(meta?.source_kind);
  for(const id of ['mission-numerator','mission-denominator']) {
    const select=el(id), follower=[...select.options].find(item=>item.value==='followers');
    if(follower) follower.disabled=sample;
    if(sample&&select.value==='followers') select.value=id.endsWith('denominator')?'views':'likes';
    select.dispatchEvent(new Event('optionschange'));
  }
  el('batch-context').textContent=meta?`Copy all ${meta.count} loaded videos into this mission's own RAM dataset. No new fetch.`
    :'New fetches become separate datasets. Saving is optional. Position ranges allow up to 500 videos; each mission retains at most 2,500.';
}

export function updateBatchSummary() {
  setOptions('mission-creator',uiState.savedCreators.map(row=>option(row.uid,`${row.name} · UID ${row.uid}`)).join('')+option('manual','Enter a creator UID'),uiState.selectedCreator?.uid||'manual');
  if (!creatorChoicesInitialized && uiState.savedCreators.length) {
    el('mission-creator').value = uiState.selectedCreator?.uid || uiState.savedCreators[0].uid;
    el('mission-creator').dispatchEvent(new Event('optionschange'));
    creatorChoicesInitialized = true;
  }
  syncBuilder();
}

export function configureBatch(version) {
  enabled=version>=1;
  el('add-mission').disabled=!enabled;
  if(!enabled) el('batch-status').textContent='Restart the main app to enable the mission queue.';
}

function configPayload() {
  const value=id=>el(`mission-${id}`).value, kind=value('selection-kind');
  const selection=kind==='position'?{kind,start:value('start'),end:value('end')}
    :kind==='published'?{kind,start_time:value('start-time'),end_time:value('end-time')}
      :{kind,metric:value('selection-metric'),minimum:value('minimum'),maximum:value('maximum')};
  const source=value('source');
  return {name:value('name'),source:source==='fetch'?'fetch':'loaded',source_collection_id:source,
    creator_uid:value('creator')==='manual'?value('uid'):value('creator'),selection,fetch_source:value('fetch-source'),
    local_filter:{minimum_views:value('min-views'),maximum_views:value('max-views')},
    steps:['snapshot','analysis','plot','division'].filter(step=>el(`mission-${step}`).checked),
    field:value('field'),plot_mode:value('plot-mode'),plot_axis:value('plot-axis'),numerator:value('numerator'),denominator:value('denominator'),mode:value('mode')};
}

function scope(config) {
  if(config.source==='loaded') return 'Copy loaded rows · no fetching';
  const s=config.selection;
  return s.kind==='position'?`Positions ${s.start}–${s.end} · ${config.fetch_source}`
    :s.kind==='published'?`Published ${s.start_time}–${s.end_time} · ${config.fetch_source}`
      :`${s.metric} ${s.minimum??'any'}–${s.maximum??'any'} · ${config.fetch_source}`;
}

function render(data) {
  queue=data.missions;busy=data.running;available=data.collections;
  if(data.creator_dataset) available=[{...data.creator_dataset,collection_id:'creator'},...available];
  setOptions('mission-source',option('fetch','Fetch a creator dataset')+available.map(meta=>option(meta.collection_id,`${meta.source_label} · ${meta.count} videos in RAM`)).join(''),'fetch');
  el('mission-builder').disabled=busy||!enabled||queue.length>=data.limit;
  el('add-mission').disabled=busy||!enabled||queue.length>=data.limit;
  el('run-batch').disabled=busy||!enabled||!queue.some(row=>row.state!=='completed');
  el('stop-batch').disabled=!busy||data.stop_requested;
  el('batch-status').textContent=data.stop_requested&&busy?'Stopping after the current step…'
    :busy?'Running missions on the server. You can leave this page.'
      :`${queue.filter(row=>row.state==='completed').length} completed · ${queue.filter(row=>row.state==='failed').length} failed · ${queue.filter(row=>!['completed','failed'].includes(row.state)).length} queued / paused`;
  el('mission-list').innerHTML=queue.length?queue.map((row,index)=>{
    const c=row.config, steps=(c.source==='fetch'?['fetch']:[]).concat(c.steps);
    return `<article class="mission-card" data-state="${escapeHTML(row.state)}">
      <div class="page-heading"><div><h3>${index+1}. ${escapeHTML(c.name)}</h3><p class="muted">${escapeHTML(c.creator?`${c.creator.name} · UID ${c.creator.uid}`:row.dataset?.source_label)} · ${escapeHTML(scope(c))}</p></div><span class="mission-state">${escapeHTML(row.state)}</span></div>
      <ol class="mission-step-list">${steps.map(step=>`<li class="${row.completed_steps.includes(step)?'done':''}">${escapeHTML(labels[step])}${row.completed_steps.includes(step)?' ✓':''}</li>`).join('')}</ol>
      <p class="muted" role="status">${escapeHTML(row.message)}${row.dataset?` · ${row.dataset.count} videos retained in RAM`:''}</p>
      <div class="actions"><button data-mission="${row.id}" data-mission-action="result" ${row.dataset?'':'disabled'}>View data & results</button>
        <button data-mission="${row.id}" data-mission-action="duplicate" ${busy?'disabled':''}>Duplicate settings</button>
        <button data-mission="${row.id}" data-mission-action="up" ${busy||index===0?'disabled':''} aria-label="Move ${escapeHTML(c.name)} up">↑</button>
        <button data-mission="${row.id}" data-mission-action="down" ${busy||index===queue.length-1?'disabled':''} aria-label="Move ${escapeHTML(c.name)} down">↓</button>
        <button data-mission="${row.id}" data-mission-action="remove" ${busy?'disabled':''}>Remove</button></div></article>`;
  }).join(''):'<p class="empty-state">Add a mission for A, then another for B or C. Each keeps its own dataset.</p>';
  syncBuilder();
}

export async function refreshBatch() {if(enabled) render(await getJSON('/api/missions'));}

async function showResult(id) {
  const row=await getJSON(`/api/missions/result?id=${id}`),result=row.results;
  el('mission-result').hidden=false;
  el('mission-result-title').textContent=`${row.config.name} · retained results`;
  const action=(name,label)=>`<button data-mission="${id}" data-mission-view="${name}">${label}</button>`;
  el('mission-result-content').innerHTML=`<p class="muted">${escapeHTML(row.dataset.source_label)} · ${row.dataset.count} whole-collection rows · collected ${escapeHTML(new Date(row.dataset.collected_at).toLocaleString())}</p>
    <div class="actions">${action('analysis','Use dataset in Analysis')}${result.analysis?action('analysis-result','Open saved analysis'):''}${result.plot?action('plot','Open saved plot'):''}${result.division?action('division','Open saved ratios'):''}</div>
    ${result.snapshot?`<p role="status">Snapshot saved · collection #${result.snapshot.batch.id} · ${result.snapshot.batch.video_count} videos.</p>`:'<p class="muted">No snapshot saved by this mission.</p>'}
    ${result.analysis?`<h3>Analysis</h3>${table(['Metric','Count','Mean','Median','Min','Max'],result.analysis.summaries.map(r=>[r.label,r.count,r.mean,r.median,r.min,r.max]))}`:''}
    ${result.division?`<h3>Ratio</h3>${result.division.mode==='aggregate'?table(['Numerator','Denominator','Pooled ratio','Included','Excluded'],[[result.division.numerator_total,result.division.denominator_total,result.division.ratio,result.division.eligible_count,result.division.excluded_count]]):table(['Video','Numerator','Denominator','Ratio'],result.division.rows.map(r=>[r.title,r.numerator,r.denominator,r.ratio]))}`:''}
    ${result.plot?`<p>${escapeHTML(result.plot.plot_label)} · ${result.plot.points.length} plotted videos. Open saved plot to inspect the chart.</p>`:''}
    <details><summary>Whole dataset (${row.dataset.count} videos)</summary><div class="analysis-table">${table(['Title','BVID','Views','Likes','Coins'],(row.videos||[]).map(v=>[v.title,v.bvid,v.views,v.likes,v.coins]))}</div></details>`;
}

function duplicate(row) {
  const config = row.config;
  el('mission-name').value=`${config.name} · copy`;
  for(const [key,id] of [['field','field'],['plot_mode','plot-mode'],['plot_axis','plot-axis'],['numerator','numerator'],['denominator','denominator'],['mode','mode'],['fetch_source','fetch-source']]) if(config[key]!=null) el(`mission-${id}`).value=config[key];
  el('mission-source').value=config.source==='fetch'?'fetch':row.collection_id;
  if(config.creator){el('mission-creator').value=uiState.savedCreators.some(c=>c.uid===config.creator.uid)?config.creator.uid:'manual';el('mission-uid').value=config.creator.uid;}
  if(config.selection){const s=config.selection;el('mission-selection-kind').value=s.kind;for(const [key,id] of Object.entries({start:'start',end:'end',start_time:'start-time',end_time:'end-time',metric:'selection-metric',minimum:'minimum',maximum:'maximum'}))el(`mission-${id}`).value=s[key]??'';}
  el('mission-min-views').value=config.local_filter.minimum_views??'';el('mission-max-views').value=config.local_filter.maximum_views??'';
  for(const step of ['snapshot','analysis','plot','division'])el(`mission-${step}`).checked=config.steps.includes(step);
  el('mission-builder').querySelectorAll('select').forEach(select=>select.dispatchEvent(new Event('optionschange')));
  el('mission-builder-panel').open=true;
  syncBuilder();el('mission-name').focus();
}

export function setupBatch({viewResult, onSettled}) {
  onResult=viewResult;
  const stackedLayout=matchMedia('(max-width: 900px)');
  const syncBuilderPanel=()=>{el('mission-builder-panel').open=!stackedLayout.matches;};
  stackedLayout.addEventListener('change',syncBuilderPanel);
  syncBuilderPanel();
  for(const id of ['mission-field','mission-selection-metric'])fillOptions(id,metricFields);
  for(const id of ['mission-numerator','mission-denominator'])fillOptions(id,divisionFields);
  el('mission-field').value='views';el('mission-selection-metric').value='views';el('mission-numerator').value='likes';el('mission-denominator').value='views';
  el('mission-builder').addEventListener('change',syncBuilder);
  bindAction('add-mission',async()=>{render(await postJSON('/api/missions/add',configPayload()));el('mission-name').value='';await refreshCollections();},refreshBatch);
  bindAction('run-batch',async()=>render(await postJSON('/api/missions/run',{})),refreshBatch);
  bindAction('stop-batch',async()=>render(await postJSON('/api/missions/stop',{})),refreshBatch);
  bindAction('refresh-missions',refreshBatch);
  el('mission-result-close').addEventListener('click',()=>{el('mission-result').hidden=true;});
  el('panel-tasks').addEventListener('click',event=>{
    const button=event.target.closest('button[data-mission]');if(!button||button.disabled)return;
    const id=button.dataset.mission, command=button.dataset.missionAction;
    if(command==='duplicate'){duplicate(queue.find(row=>row.id===id));return;}
    performAction(button,async()=>{
      if(button.dataset.missionView)await onResult(await getJSON(`/api/missions/result?id=${id}`),button.dataset.missionView);
      else if(command==='result')await showResult(id);
      else{render(await postJSON('/api/missions/action',{id,action:command}));if(command==='remove'){el('mission-result').hidden=true;el('mission-result-content').innerHTML='';}await refreshCollections();}
    }).finally(() => { onSettled?.(); return refreshBatch(); });
  });
  setInterval(()=>{if(enabled&&!document.hidden&&(busy||document.querySelector('main').dataset.activePanel==='tasks')&&!uiState.actionBusy)
    refreshBatch().catch(error=>{el('batch-status').textContent=error.message;});},1200);
  updateBatchSummary();
}
