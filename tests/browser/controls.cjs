/* Offline pacing controls and transient notifications. No Bilibili requests. */
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
    browser = await chromium.launch({ headless: true, channel: process.env.BROWSER_CHANNEL || 'chrome' });
    const page = await browser.newPage({ viewport: { width: 1360, height: 1000 } });
    const errors = [];
    let pacingPosts = 0;
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => { if (request.url().endsWith('/api/request-frequency') && request.method() === 'POST') pacingPosts++; });
    await page.goto(log.match(/http:\/\/127\.0\.0\.1:\d+/)[0]);
    await page.locator('#status').filter({ hasText: 'Layout preview' }).waitFor();
    assert.equal(await page.locator('#dataset-request-frequency').inputValue(), '4');
    await page.locator('#dataset-request-frequency').fill('0.5');
    await page.locator('#set-dataset-frequency').click();
    await page.waitForFunction(() => !document.querySelector('#set-dataset-frequency').disabled);
    assert.equal(await page.locator('#panel-videos').isVisible(), true);
    assert.equal(await page.locator('#request-frequency').inputValue(), '0.5');
    assert.match(await page.locator('#dataset-pacing-status').innerText(), /0.5 requests\/s/);
    await page.locator('[data-section="settings"]').click();
    await page.locator('#request-frequency').fill('0.2');
    await page.locator('#set-frequency').click();
    await page.waitForFunction(() => !document.querySelector('#set-frequency').disabled);
    await openPanel(page, 'videos');
    assert.equal(await page.locator('#dataset-request-frequency').inputValue(), '0.2');
    assert.equal(pacingPosts, 2);
    await page.locator('#dataset-request-frequency').fill('0');
    await page.locator('#set-dataset-frequency').click();
    await page.locator('#page-feedback').filter({ hasText: 'Use pacing' }).waitFor();
    assert.equal(pacingPosts, 2, 'Reject invalid pacing before sending');
    await page.click('#fetch-source-trigger');
    await page.locator('#fetch-source-options').getByRole('option', { name: 'Parallel · this Mac + ready nodes', exact: true }).click();
    assert.equal(await page.locator('#fetch-source').inputValue(), 'parallel');
    assert.match(await page.locator('#fetch-node-status').innerText(), /latest source/);
    const position = await page.locator('#panel-videos').boundingBox();
    await page.clock.install();
    await page.evaluate(async () => {
      const ui = await import('/static/js/ui.js');
      ui.showFeedback(document.getElementById('page-feedback'), 'First error', { error: true });
    });
    await page.clock.fastForward(7000);
    assert.equal(await page.locator('#page-feedback').isVisible(), true);
    await page.evaluate(async () => {
      const ui = await import('/static/js/ui.js');
      ui.showFeedback(document.getElementById('page-feedback'), 'New error', { error: true });
    });
    await page.clock.fastForward(2000);
    assert.match(await page.locator('#page-feedback').innerText(), /New error/);
    await page.clock.fastForward(6001);
    assert.equal(await page.locator('#page-feedback').isHidden(), true, 'Errors dismiss automatically without hiding newer messages');
    assert.deepEqual(await page.locator('#panel-videos').boundingBox(), position, 'Dismissing a notice must not move the page');
    await page.evaluate(async () => {
      const ui = await import('/static/js/ui.js');
      ui.showFeedback(document.getElementById('page-feedback'), 'Copied');
    });
    await page.clock.fastForward(4001);
    assert.equal(await page.locator('#page-feedback').isHidden(), true);
    for (const width of [1360, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `Pacing controls overflow at ${width}`);
    }
    assert.deepEqual(errors, []);
    console.log('Pacing and notification browser checks passed, including mobile widths.');
  } finally {
    await browser?.close();
    server.kill('SIGINT');
    await finished;
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
