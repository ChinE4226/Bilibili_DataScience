/* Offline task sequencing, settings capture, failures, and stop behavior. */
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '../..');
const server = spawn(path.join(root, '.venv/bin/python'), ['-B', '-u', 'scripts/preview_dashboard.py', '--port', '0'], { cwd: root });
let log = '';
server.stdout.on('data', chunk => { log += chunk; });
server.stderr.on('data', chunk => { log += chunk; });
const finished = once(server, 'exit');

(async () => {
  let browser;
  try {
    const deadline = Date.now() + 15000;
    while (!log.match(/http:\/\/127\.0\.0\.1:\d+/)) {
      if (Date.now() > deadline || server.exitCode !== null) throw new Error(log);
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    browser = await chromium.launch({ headless: true, channel: process.env.BROWSER_CHANNEL || 'chrome' });
    const page = await browser.newPage({ viewport: { width: 1360, height: 1000 } });
    async function openTool(name) {
      await page.locator('[data-section="workspace"]').click();
      await page.locator(`[data-panel="${name}"]`).click();
    }
    const errors = [], requests = [];
    let failure = false, saves = 0;
    const gates = new Map();
    function hold(action) {
      let release;
      const promise = new Promise(resolve => { release = resolve; });
      gates.set(action, promise);
      return () => { gates.delete(action); release(); };
    }
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => { if (request.url().endsWith('/api/plots/save')) saves++; });
    await page.route('**/api/video-action', async route => {
      const payload = route.request().postDataJSON();
      requests.push(payload);
      if (gates.has(payload.action)) await gates.get(payload.action);
      if (failure && payload.action === 'division') {
        await route.fulfill({ status: 400, json: { error: 'Ratio failed for testing.' } });
      } else {
        await route.continue();
      }
    });
    await page.goto(log.match(/http:\/\/127\.0\.0\.1:\d+/)[0]);
    await page.locator('#status').filter({ hasText: 'Layout preview' }).waitFor();
    await page.locator('#position-end').fill('100');
    await page.locator('#dataset-filters > summary').click();
    await page.locator('#local-min-views').fill('200');
    await openTool('division');
    await page.locator('#division-mode').selectOption('aggregate', { force: true });
    await page.locator('#division-numerator').selectOption('favorites', { force: true });
    await openTool('plot');
    await page.locator('#plot-field').selectOption('likes', { force: true });
    await page.locator('#plot-axis').selectOption('number', { force: true });
    await page.locator('[data-panel="tasks"]').click();
    assert.equal(await page.locator('.selection-card').isVisible(), false);
    assert.match(await page.locator('#batch-config-fetch').innerText(), /100 valid videos/);
    assert.match(await page.locator('#batch-config-division').innerText(), /Favorites \/ Views.*pooled/);
    assert.match(await page.locator('#batch-config-plot').innerText(), /Likes.*equal spacing/);
    await page.locator('#batch-plot').check();

    const releaseFetch = hold('list'), releaseRatio = hold('division');
    await page.locator('#run-batch').click();
    await page.locator('#batch-state-fetch').filter({ hasText: 'Running' }).waitFor();
    assert.equal(requests.length, 1);
    assert.equal(await page.locator('#position-end').isDisabled(), true);
    assert.equal(await page.locator('#batch-analysis').isDisabled(), true);
    assert.equal(await page.locator('#stop-batch').isEnabled(), true);
    await openTool('analysis');
    assert.equal(await page.locator('#run-analysis').isDisabled(), true, 'Other operations cannot overlap a batch');
    // Simulate changes outside the UI: queued requests still use their captured settings.
    await page.evaluate(() => {
      document.querySelector('#position-end').value = '5';
      document.querySelector('#local-min-views').value = '999';
      document.querySelector('#division-numerator').value = 'coins';
      document.querySelector('#plot-field').value = 'shares';
    });
    await page.locator('[data-panel="tasks"]').click();
    releaseFetch();
    await page.locator('#batch-state-division').filter({ hasText: 'Running' }).waitFor();
    assert.equal(requests.length, 2);
    assert.match(await page.locator('#batch-state-fetch').innerText(), /Completed/);
    assert.equal(await page.locator('#batch-state-analysis').innerText(), 'Queued');
    releaseRatio();
    await page.locator('#batch-status').filter({ hasText: 'Completed all 4 tasks' }).waitFor();
    await page.waitForFunction(() => !document.querySelector('#run-batch').disabled);
    assert.deepEqual(requests.map(request => request.action), ['list', 'division', 'analysis', 'plot']);
    assert.equal(requests.filter(request => request.refresh).length, 1);
    for (const request of requests) {
      assert.equal(request.selection.end, '100');
      assert.equal(request.local_filter.minimum_views, '200');
      assert.equal(request.reuse_only, true);
    }
    assert.equal(requests[1].numerator, 'favorites');
    assert.equal(requests[1].mode, 'aggregate');
    assert.equal(requests[3].field, 'likes');
    assert.equal(saves, 0, 'Running tasks must not save PNGs automatically');
    assert.equal(await page.locator('#panel-tasks').isVisible(), true, 'Completion must preserve the active page');
    assert.equal(await page.locator('#stop-batch').isDisabled(), true);
    assert.equal(await page.locator('#position-end').isEnabled(), true);
    await openTool('analysis');
    assert.equal(await page.locator('#analysis-result svg').count(), 2);
    assert.equal(await page.locator('#analysis-field-trigger').isEnabled(), true);
    await openTool('division');
    assert.match(await page.locator('#division-result').innerText(), /Eligible/);
    await openTool('plot');
    assert.equal(await page.locator('#plot-workspace').isVisible(), true);
    assert.equal(await page.locator('#plot-reset').isEnabled(), true);
    await page.locator('[data-panel="tasks"]').click();
    if (process.env.SCREENSHOT_PATH) await page.screenshot({ path: process.env.SCREENSHOT_PATH });

    // Reuse an existing dataset without an automatic fetch.
    await page.locator('#batch-fetch').uncheck();
    await page.locator('#batch-plot').uncheck();
    requests.length = 0;
    await page.locator('#run-batch').click();
    await page.locator('#batch-status').filter({ hasText: 'Completed all 2 tasks' }).waitFor();
    await page.waitForFunction(() => !document.querySelector('#run-batch').disabled);
    assert.deepEqual(requests.map(request => request.action), ['division', 'analysis']);
    assert.ok(requests.every(request => !request.refresh));

    // A failed step stops remaining tasks, while completed results remain available.
    failure = true;
    await page.locator('#batch-fetch').check();
    await page.locator('#batch-plot').check();
    requests.length = 0;
    await page.locator('#run-batch').click();
    await page.locator('#batch-status').filter({ hasText: 'Stopped at Calculate ratios' }).waitFor();
    await page.waitForFunction(() => !document.querySelector('#run-batch').disabled);
    assert.deepEqual(requests.map(request => request.action), ['list', 'division']);
    assert.match(await page.locator('#batch-state-division').innerText(), /Failed: Ratio failed/);
    assert.equal(await page.locator('#batch-state-analysis').innerText(), 'Skipped after failure');
    assert.equal(await page.locator('#batch-state-plot').innerText(), 'Skipped after failure');
    failure = false;

    // Stopping lets the active request complete and prevents subsequent requests.
    requests.length = 0;
    const releaseStoppedFetch = hold('list');
    await page.locator('#run-batch').click();
    await page.locator('#batch-state-fetch').filter({ hasText: 'Running' }).waitFor();
    await page.locator('#stop-batch').click();
    assert.match(await page.locator('#batch-status').innerText(), /Stopping after/);
    releaseStoppedFetch();
    await page.locator('#batch-status').filter({ hasText: 'Stopped. 1 of 4' }).waitFor();
    await page.waitForFunction(() => !document.querySelector('#run-batch').disabled);
    assert.deepEqual(requests.map(request => request.action), ['list']);
    assert.equal(await page.locator('#batch-state-division').innerText(), 'Skipped by request');
    for (const id of ['fetch', 'division', 'analysis', 'plot']) await page.locator(`#batch-${id}`).uncheck();
    assert.equal(await page.locator('#run-batch').isDisabled(), true);
    for (const width of [1360, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Tasks overflow at ${width}px`);
      const main = await page.locator('main').boundingBox();
      assert.ok(Math.abs(main.x + main.width / 2 - width / 2) < 1, 'Workspace stays centered');
    }
    assert.deepEqual(errors, []);
    console.log('Batch browser checks passed: sequence, reuse, settings capture, results, failure, stop, and responsive layout.');
  } finally {
    await browser?.close();
    server.kill();
    await finished;
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
