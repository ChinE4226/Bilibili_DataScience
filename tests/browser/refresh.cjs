/* Refresh and reopen collected data through local routes, without browser storage or Bilibili. */
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const openPanel = require('./workspace.cjs');
const root = path.resolve(__dirname, '../..');
const server = spawn(path.join(root, '.venv/bin/python'), ['-B', '-u', 'scripts/preview_dashboard.py', '--port', '0'], { cwd: root });
const finished = once(server, 'exit');
let log = '';
server.stdout.on('data', data => log += data);
server.stderr.on('data', data => log += data);

(async () => {
  let browser;
  try {
    const deadline = Date.now() + 15000;
    while (!log.match(/http:\/\/127\.0\.0\.1:\d+/)) {
      if (Date.now() > deadline || server.exitCode !== null) throw Error(log);
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    const base = log.match(/http:\/\/127\.0\.0\.1:\d+/)[0];
    browser = await chromium.launch({ headless: true, channel: process.env.BROWSER_CHANNEL || 'chrome' });
    const context = await browser.newContext();
    const page = await context.newPage();
    const errors = [], posts = [];
    context.on('page', tab => tab.on('pageerror', error => errors.push(error.message)));
    page.on('pageerror', error => errors.push(error.message));
    context.on('request', request => { if (request.method() === 'POST') posts.push(request.postDataJSON()); });
    const ready = tab => tab.waitForFunction(() => document.documentElement.dataset.dashboardReady === 'true');
    const settled = () => page.waitForFunction(() => !document.documentElement.dataset.actionBusy);
    await page.goto(base);
    await ready(page);
    await page.locator('#position-start').fill('3');
    await page.locator('#position-end').fill('100');
    await page.locator('#fetch-dataset').click();
    await settled();
    const before = await (await page.request.get(base + '/api/collections')).json();
    await openPanel(page, 'sampling');
    await page.locator('#sample-mode-weekly').click();
    await page.locator('#weekly-source').fill('393');
    await page.locator('#fetch-weekly').click();
    await settled();
    const weeklyId = await page.locator('#weekly-result [data-use-collection]').getAttribute('data-use-collection');
    await page.locator('#sample-mode-random').click();
    await page.locator('#sample-keyword').fill('camera');
    await page.locator('#sample-size').fill('3');
    await page.locator('#sample-pool-size').fill('6');
    await page.locator('#sample-seed').fill('fixed');
    await page.locator('#fetch-random-sample').click();
    await settled();
    const randomId = await page.locator('#sample-result [data-use-collection]').getAttribute('data-use-collection');
    const assertRestored = async tab => {
      assert.equal(await tab.locator('#videos-result tbody tr').count(), 24);
      assert.equal(await tab.locator('#position-start').inputValue(), '3');
      assert.equal(await tab.locator('#position-end').inputValue(), '100');
      assert.equal(await tab.locator('#weekly-result [data-use-collection]').getAttribute('data-use-collection'), weeklyId);
      assert.equal(await tab.locator('#sample-result [data-use-collection]').getAttribute('data-use-collection'), randomId);
      assert.match(await tab.locator('#sample-result').textContent(), /Seed: fixed/);
      assert.match(await tab.locator('#dataset-status').textContent(), /Reused 24 valid videos/);
      assert.equal(await tab.evaluate(() => localStorage.length + sessionStorage.length), 0, 'No data or controls saved in browser storage by manual refresh');
    };
    const collectedPosts = posts.length;
    await page.reload();
    await ready(page);
    await assertRestored(page);
    assert.equal(posts.length, collectedPosts, 'Refresh uses GET RAM snapshot only');
    assert.deepEqual(await (await page.request.get(base + '/api/collections')).json().then(data => data.creator_dataset), before.creator_dataset);
    await openPanel(page, 'sampling');
    await page.locator('#sample-result [data-use-collection]').click();
    await settled();
    assert.equal(posts.at(-1).collection_id, randomId);
    assert.equal(posts.at(-1).refresh, undefined);
    assert.match(await page.locator('#analysis-dataset-status').textContent(), /3 sampled/);
    await page.close();
    const reopened = await context.newPage();
    const beforeReopen = posts.length;
    await reopened.goto(base);
    await ready(reopened);
    await assertRestored(reopened);
    assert.equal(posts.length, beforeReopen, 'Reopening a tab reuses server memory');

    // Exercise reconnection while a server-owned operation is still running.
    let running = true, firstSnapshot = true;
    await reopened.route('**/api/workspace-data', async route => {
      const response = await route.fetch(), data = await response.json();
      if (firstSnapshot) { data.running = true; firstSnapshot = false; }
      await route.fulfill({ response, json: data });
    });
    await reopened.route('**/api/progress', route => route.fulfill({ json: { running, message: 'Collecting in server RAM', count: 24 } }));
    await reopened.reload();
    await reopened.waitForFunction(() => document.documentElement.dataset.actionBusy === 'true');
    assert.equal(await reopened.locator('#fetch-dataset').isDisabled(), true);
    running = false;
    await ready(reopened);
    await assertRestored(reopened);
    assert.equal(await reopened.locator('#fetch-dataset').isEnabled(), true);
    assert.equal(posts.length, beforeReopen, 'Reconnection does not start another collection');
    assert.deepEqual(errors, []);
    console.log('Refresh/reopen restored creator rows, selection and sampling reports from RAM; running-task reconnection and no-refetch/storage checks passed.');
  } finally {
    await browser?.close();
    server.kill('SIGINT');
    await finished;
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
