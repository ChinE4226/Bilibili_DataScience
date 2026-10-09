/* Offline multi-object mission queue using real server routes and disposable SQLite. */
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const openPanel = require('./workspace.cjs');
const root = path.resolve(__dirname, '../..');
const server = spawn(path.join(root, '.venv/bin/python'), ['-B', '-u', 'scripts/preview_dashboard.py', '--port', '0'], { cwd: root });
let log = '';
server.stdout.on('data', chunk => log += chunk);
server.stderr.on('data', chunk => log += chunk);
const finished = once(server, 'exit');

(async () => {
  let browser;
  try {
    const deadline = Date.now() + 15000;
    while (!log.match(/http:\/\/127\.0\.0\.1:\d+/)) {
      if (Date.now() > deadline || server.exitCode !== null) throw Error(log);
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    browser = await chromium.launch({ headless: true, channel: process.env.BROWSER_CHANNEL || 'chrome' });
    const page = await browser.newPage({ viewport: { width: 1360, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const settled = () => page.waitForFunction(() => !document.documentElement.dataset.actionBusy);
    const choose = async (id, name) => {
      await page.locator(`#${id}-trigger`).click();
      await page.locator(`#${id}-options`).getByRole('option', { name }).click();
    };
    await page.goto(log.match(/http:\/\/127\.0\.0\.1:\d+/)[0]);
    await page.locator('#status').filter({ hasText: 'Layout preview' }).waitFor();
    await page.locator('#fetch-dataset').click(); await settled();
    const original = await page.locator('#dataset-status').innerText();
    await openPanel(page, 'tasks');
    await choose('mission-creator', /Sample uploader/);
    await page.locator('#mission-name').fill('A');
    await page.locator('#mission-end').fill('2');
    await page.locator('#mission-snapshot').check();
    await page.locator('#add-mission').click(); await settled();
    await choose('mission-creator', /Another uploader/);
    await page.locator('#mission-name').fill('B');
    await page.locator('#mission-end').fill('3');
    await page.locator('#mission-snapshot').uncheck();
    await page.locator('#mission-analysis').uncheck();
    await page.locator('#mission-plot').check();
    await page.locator('#add-mission').click(); await settled();
    await choose('mission-creator', 'Enter a creator UID');
    await page.locator('#mission-uid').fill('111111');
    await page.locator('#mission-name').fill('C');
    await page.locator('#mission-end').fill('1');
    await page.locator('#mission-plot').uncheck();
    await page.locator('#mission-division').check();
    await page.locator('#add-mission').click(); await settled();
    await page.locator('#run-batch').click(); await settled();
    await openPanel(page, 'analysis');
    await page.reload();
    await page.locator('html[data-dashboard-ready="true"]').waitFor();
    await openPanel(page, 'tasks');
    await page.locator('#batch-status').filter({ hasText: '3 completed' }).waitFor();
    const queue = await (await page.request.get('/api/missions')).json();
    assert.deepEqual(queue.missions.map(row => row.config.creator.uid), ['123456', '987654', '111111']);
    assert.deepEqual(queue.missions.map(row => row.dataset.count), [2, 3, 1]);
    assert.deepEqual(queue.missions.map(row => row.completed_steps), [['fetch','snapshot','analysis'], ['fetch','plot'], ['fetch','division']]);
    const [a, b, c] = await Promise.all(queue.missions.map(async row => (await page.request.get(`/api/missions/result?id=${row.id}`)).json()));
    assert.equal(a.videos[0].views, 123456);
    assert.equal(a.results.snapshot.batch.video_count, 2);
    assert.equal(b.results.snapshot, undefined);
    assert.equal(c.results.snapshot, undefined);
    assert.equal(b.results.plot.points.length, 3);
    assert.equal(b.results.plot.selected_creator.uid, '987654');
    assert.ok(Math.abs(c.results.division.ratio - 10 / 111111) < 1e-10);
    await page.locator('.mission-card').filter({ has: page.getByRole('heading', { name: '1. A', exact: true }) }).getByText('View data & results', { exact: true }).click(); await settled();
    assert.match(await page.locator('#mission-result-content').innerText(), /Snapshot saved.*2 videos/);
    await page.getByRole('button', { name: 'Open saved analysis', exact: true }).click(); await settled();
    assert.equal(await page.locator('#analysis-result svg').count(), 2);
    assert.equal(await page.locator('#analysis-field-trigger').isEnabled(), true);
    await openPanel(page, 'videos');
    assert.equal(await page.locator('#dataset-status').innerText(), original);
    await openPanel(page, 'tasks');
    await page.locator('#mission-result-close').click();
    // Loaded inputs are copied before processing; no fetch step is inserted.
    await choose('mission-source', /A · .*2 videos in RAM/);
    await page.locator('#mission-name').fill('A ratios');
    await page.locator('#mission-analysis').uncheck();
    await page.locator('#mission-division').check();
    await page.locator('#add-mission').click(); await settled();
    await page.locator('#run-batch').click(); await settled();
    await page.locator('#batch-status').filter({ hasText: '4 completed' }).waitFor();
    const loaded = (await (await page.request.get('/api/missions')).json()).missions.at(-1);
    assert.deepEqual(loaded.completed_steps, ['division']);
    assert.equal(loaded.dataset.count, 2);
    assert.notEqual(loaded.collection_id, a.collection_id);
    if (process.env.SCREENSHOT_PATH) await page.screenshot({ path: process.env.SCREENSHOT_PATH });
    for (const width of [1360, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Tasks overflow at ${width}px`);
    }
    assert.deepEqual(errors, []);
    console.log('Mission browser checks passed: targets, steps, optional snapshots, independent RAM, reload, saved results, loaded inputs and layout.');
  } finally {
    await browser?.close(); server.kill(); await finished;
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
