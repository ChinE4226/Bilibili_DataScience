const openPanel = require('./workspace.cjs');
/* Main and node GUIs use real HTTP connections; fetching uses offline fixtures. */
const assert = require('node:assert/strict');
const {spawn} = require('node:child_process');
const {once} = require('node:events');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '../..');
const server = spawn(path.join(root,'.venv/bin/python'), ['-B','-u','tests/fixtures/node_system.py'], {cwd:root});
const finished = once(server,'exit');
let log='';server.stdout.on('data', data=>log+=data);server.stderr.on('data',data=>log+=data);

(async()=>{let browser;try {
  const deadline=Date.now()+15000;
  while (!log.match(/\{"main":.*\}\n/)) {if(Date.now()>deadline||server.exitCode!==null)throw Error(log);await new Promise(resolve=>setTimeout(resolve,100));}
  const urls=JSON.parse(log.match(/\{"main":.*\}/)[0]);
  browser=await chromium.launch({headless:true,channel:process.env.BROWSER_CHANNEL||'chrome'});
  const main=await browser.newPage({viewport:{width:1360,height:1000}});
  const nodes=[await browser.newPage(),await browser.newPage()];
  const errors=[];[main,...nodes].forEach(page=>page.on('pageerror',error=>errors.push(error.message)));
  await main.goto(urls.main);await main.locator('#status').filter({hasText:'Layout preview'}).waitFor();
  await openPanel(main, 'nodes');
  await main.locator('#node-service-status').filter({hasText:'running'}).waitFor();
  await main.locator('#stop-node-service').click();
  await main.locator('#node-service-status').filter({hasText:'stopped'}).waitFor();
  await main.locator('#node-service-port').fill(urls.listener.split(':').at(-1));
  await main.locator('#start-node-service').click();
  await main.locator('#node-service-status').filter({hasText:'running'}).waitFor();
  assert.equal(await main.locator('#open-library').isVisible(),false);
  assert.equal(await main.locator('.selection-card').isVisible(),false);
  assert.equal(await main.locator('#node-advanced-collections').evaluate(details => details.open),false,
    'Connection page keeps separate collection controls collapsed');
  for(let i=0;i<2;i++) {
    if(i) {const previous=await main.locator('#node-pair-code').inputValue();await main.locator('#new-node-pairing').click();await main.waitForFunction(value=>document.querySelector('#node-pair-code').value!==value,previous);}
    const code=await main.locator('#node-pair-code').inputValue();assert.ok(code.length>20);
    await nodes[i].goto(urls.nodes[i]);await nodes[i].locator('#connection-status').filter({hasText:'disconnected'}).waitFor();
    await nodes[i].locator('#node-name').fill(i ? 'Mac B' : 'Mac A & Desk');
    await nodes[i].locator('#node-url').fill(urls.listener);await nodes[i].locator('#node-code').fill(code);
    const activityPosition = await nodes[i].locator('#activity-progress').boundingBox();
    await nodes[i].locator('#check-connection').click();
    await nodes[i].locator('#feedback').filter({hasText:'reachable'}).waitFor();
    assert.deepEqual(await nodes[i].locator('#activity-progress').boundingBox(), activityPosition,
      'Node connection feedback must not move the activity section');
    assert.equal(await main.locator('#node-pair-code').inputValue(),code,'Health checks do not consume pairing codes');
    await nodes[i].locator('#feedback').waitFor({ state: 'hidden', timeout: 6000 });
    await nodes[i].locator('details > summary').click();
    await nodes[i].locator('#node-cookie').fill('SESSDATA=private-local-fixture');await nodes[i].locator('#connect').click();
    await nodes[i].locator('#connection-status').filter({hasText:/^connected$/}).waitFor();
    assert.equal(await nodes[i].locator('#node-cookie').inputValue(),'');assert.equal(await nodes[i].locator('#node-code').inputValue(),'');
    assert.equal(await nodes[i].locator('#node-url').isDisabled(),true);
  }
  await main.locator('#nodes-list tbody tr').nth(1).waitFor();
  const a=main.locator('#nodes-list tbody tr').filter({hasText:'Mac A & Desk'});
  const b=main.locator('#nodes-list tbody tr').filter({hasText:'Mac B'});
  await a.getByRole('button',{name:'Pause',exact:true}).click();
  await nodes[0].locator('#connection-status').filter({hasText:'paused by main'}).waitFor();
  await nodes[1].locator('#pause').click();
  await nodes[1].waitForFunction(()=>!document.querySelector('#resume').disabled);
  const ids=Array.from({length:41},(_,i)=>'BV'+String(i).padStart(10,'0'));
  await main.locator('#node-advanced-collections > summary').click();
  await main.locator('#node-task-videos').fill(ids.join('\n')+'\n'+ids[0]);
  await main.locator('#queue-node-task').click();
  const task=main.locator('#node-tasks-list tbody tr').filter({hasText:'Fetch 41 video(s)'});
  await task.waitFor();assert.equal(await task.locator('td').nth(1).innerText(),'queued');
  await a.getByRole('button',{name:'Resume',exact:true}).click();await nodes[1].locator('#resume').click();
  await task.locator('td').nth(1).filter({hasText:'completed'}).waitFor({timeout:15000});
  assert.equal(await task.locator('td').nth(3).innerText(),'40/41');
  await task.getByRole('button',{name:'View results'}).click();
  await main.locator('#nodes-result h3').first().waitFor();
  assert.match(await main.locator('#nodes-result').innerText(),/40\/41 valid videos/);
  assert.match(await main.locator('#nodes-result').innerText(),/Mac A & Desk, Mac B/);
  assert.equal(await main.locator('#nodes-result .analysis-table').first().locator('tbody tr').first().locator('td').nth(3).innerText(),'2,042.5');
  // Node target checkboxes survive polling; only the selected node gets this task.
  await b.locator('[data-node-target]').check();
  await main.locator('#node-task-videos').fill(ids[1]);await main.locator('#queue-node-task').click();
  const targeted=main.locator('#node-tasks-list tbody tr').filter({hasText:'Fetch 1 video(s)'});
  await targeted.locator('td').nth(1).filter({hasText:'completed'}).waitFor({timeout:15000});
  assert.equal(await b.locator('[data-node-target]').isChecked(),true);
  await targeted.getByRole('button',{name:'View results'}).click();
  await main.locator('#nodes-result h3').filter({hasText:'Fetch 1 video(s)'}).waitFor();
  assert.match(await main.locator('#nodes-result').innerText(),/Nodes: Mac B/);
  await main.locator('#node-task-kind').selectOption('creator',{force:true});
  assert.equal(await main.locator('#node-task-creator-source').isVisible(),true);
  await main.locator('#node-task-uid').fill('42');await main.locator('#node-task-count').fill('2');
  await main.locator('#queue-node-task').click();
  const creator=main.locator('#node-tasks-list tbody tr').filter({hasText:'Creator 42'});
  await creator.locator('td').nth(1).filter({hasText:'completed'}).waitFor({timeout:15000});
  assert.equal(await creator.locator('td').nth(3).innerText(),'2/2');
  await openPanel(main, 'videos');
  await main.locator('#position-end').fill('5');
  assert.equal(await main.locator('#fetch-source').inputValue(),'auto');
  await main.locator('#fetch-dataset').click();
  await main.locator('#dataset-status').filter({hasText:'Fetched 5 valid videos'}).waitFor();
  assert.match(await main.locator('#dataset-status').innerText(),/fetched on Mac/);
  assert.match(await main.locator('#dataset-status').innerText(),/2 invalid skipped/);
  assert.equal(await main.locator('#panel-videos').isVisible(),true,'Fetching stays on the normal Dataset page');
  assert.equal(await main.locator('#videos-result tbody tr').count(),5);
  // Keep the same Dataset button and mode as node availability changes.
  await openPanel(main, 'nodes');
  await a.getByRole('button',{name:'Pause',exact:true}).click();
  await b.getByRole('button',{name:'Pause',exact:true}).click();
  await openPanel(main, 'videos');
  await main.locator('#fetch-dataset').click();
  await main.locator('#dataset-status').filter({hasText:'fetched on This Mac'}).waitFor();
  assert.equal(await main.locator('#panel-videos').isVisible(),true);
  assert.equal(await main.locator('#videos-result tbody tr').count(),5);
  await openPanel(main, 'nodes');
  await b.getByRole('button',{name:'Resume',exact:true}).click();
  await openPanel(main, 'videos');
  await main.locator('#fetch-dataset').click();
  await main.locator('#dataset-status').filter({hasText:'fetched on Mac B'}).waitFor();
  assert.equal(await main.locator('#fetch-source').inputValue(),'auto');
  await openPanel(main, 'analysis');
  await main.locator('#run-analysis').click();
  await main.waitForFunction(()=>document.querySelector('#dataset-status').textContent.includes('Reused 5 valid videos'));
  assert.ok(await main.locator('#analysis-result svg').count()>0);
  await openPanel(main, 'nodes');
  await main.locator('#new-node-pairing').click();
  await main.waitForFunction(() => !document.querySelector('#copy-node-pairing').disabled);
  await main.evaluate(() => {
    Object.defineProperty(navigator, 'clipboard', {configurable:true, value:{
      writeText: () => new Promise((resolve, reject) => {
        window.copyResolve = resolve;
        window.copyReject = reject;
      })
    }});
  });
  const paint = () => main.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const position = selector => main.evaluate(selector => ({
    top: document.querySelector(selector).getBoundingClientRect().top,
    scroll: scrollY, height: document.documentElement.scrollHeight
  }), selector);
  const stableCopy = async (selector, fail=false) => {
    const button = main.locator(selector).first();
    await button.scrollIntoViewIfNeeded();
    await paint();
    const before = await position(selector);
    await button.click();
    await main.waitForFunction(() => typeof window.copyResolve === 'function');
    await paint();
    assert.deepEqual(await position(selector), before, 'Copy must not move content while pending');
    await main.evaluate(fail => {
      if (fail) window.copyReject(new Error('Clipboard unavailable for testing.'));
      else window.copyResolve();
      delete window.copyResolve;
      delete window.copyReject;
    }, fail);
    await main.waitForFunction(() => !document.querySelector('#copy-node-pairing').disabled);
    if (fail) await main.locator('#page-feedback').filter({hasText:'Clipboard unavailable for testing.'}).waitFor();
    await paint();
    assert.deepEqual(await position(selector), before, 'Copy success and errors must not move content');
    await main.evaluate(async () => {
      const {refreshNodes} = await import('/static/js/views/nodes.js');
      await refreshNodes();
    });
    assert.equal(await button.evaluate(element => document.activeElement === element), true,
      'Copy retains keyboard focus through node status updates');
  };
  for(const width of [1360,768,390,320]) {
    await main.setViewportSize({width,height:1000});await nodes[0].setViewportSize({width,height:1000});
    await stableCopy('#copy-node-pairing');
    await stableCopy('[data-copy-node-url]', width === 320);
    assert.ok(await main.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Main overflow at ${width}`);
    assert.ok(await nodes[0].evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`Node overflow at ${width}`);
  }
  await main.setViewportSize({width:1360,height:1000});
  await b.getByRole('button',{name:'Remove',exact:true}).click();
  await nodes[1].locator('#connection-status').filter({hasText:'pairing required'}).waitFor();
  await main.locator('#clear-node-tasks').click();await main.locator('#node-tasks-list').filter({hasText:'No tasks queued'}).waitFor();
  if(process.env.NODE_SCREENSHOT_DIRECTORY) {
    await main.evaluate(()=>scrollTo(0,0));await main.screenshot({path:path.join(process.env.NODE_SCREENSHOT_DIRECTORY,'main.png')});
    await nodes[0].evaluate(()=>scrollTo(0,0));await nodes[0].screenshot({path:path.join(process.env.NODE_SCREENSHOT_DIRECTORY,'worker.png')});
  }
  assert.deepEqual(errors,[]);console.log('Node browser checks passed: preflight, pairing, normal Dataset remote fetching and local analysis, targeting, pause/resume, revocation, stable clipboard feedback/focus, and responsive GUIs.');
}finally{await browser?.close();server.kill();await finished;}})().catch(error=>{console.error(error);process.exitCode=1;});
