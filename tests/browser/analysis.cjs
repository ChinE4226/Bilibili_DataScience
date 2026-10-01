/* Offline UI checks; browser profile is removed when Chromium closes. */
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
    const errors = [], actions = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      if (request.url().endsWith('/api/video-action')) actions.push(request.postDataJSON());
    });
    await page.goto(log.match(/http:\/\/127\.0\.0\.1:\d+/)[0]);
    await page.locator('#status').filter({ hasText: 'Layout preview' }).waitFor();
    assert.equal(await page.locator('.main-nav button').count(), 3);
    assert.equal(await page.locator('#panel-videos').isVisible(), true);
    await page.locator('#fetch-dataset').click();
    await page.locator('#dataset-status').filter({ hasText: 'Fetched 24' }).waitFor();
    await page.locator('[data-panel="analysis"]').click();
    await page.locator('#run-analysis').click();
    await page.locator('#analysis-result svg').first().waitFor();
    assert.equal(await page.locator('#analysis-result svg').count(), 2);
    assert.equal(actions.at(-1).reuse_only, true);
    const previous = actions.length;
    await page.locator('#analysis-field').selectOption('likes');
    assert.match(await page.locator('#analysis-result').innerText(), /Likes distribution/);
    assert.equal(actions.length, previous, 'Changing chart metric must stay local');
    await page.locator('#dataset-filters > summary').click();
    await page.locator('#local-min-views').fill('200');
    await page.locator('#run-analysis').click();
    await page.waitForFunction(() => !document.querySelector('#run-analysis').disabled);
    assert.equal(actions.at(-1).local_filter.minimum_views, '200');
    // Navigation preserves the dataset controls and the last workspace view.
    const requestCount = actions.length;
    await page.locator('[data-section="explore"]').click();
    assert.equal(await page.locator('#panel-creators').isVisible(), true);
    assert.equal(await page.locator('.selection-card').isVisible(), false);
    await page.locator('[data-panel="single-video"]').click();
    assert.equal(await page.locator('#single-video-input').isVisible(), true);
    assert.equal(await page.locator('#open-library').isVisible(), false);
    await page.locator('[data-section="settings"]').click();
    assert.equal(await page.locator('#panel-settings').isVisible(), true);
    assert.equal(await page.locator('#open-library').isVisible(), false);
    await page.locator('[data-section="workspace"]').click();
    assert.equal(await page.locator('#panel-analysis').isVisible(), true);
    assert.equal(await page.locator('#local-min-views').inputValue(), '200');
    assert.equal(actions.length, requestCount, 'Navigation must not fetch data');
    for (const width of [1360, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Overflow at ${width}px`);
      const before = await page.locator('main').boundingBox();
      assert.ok(Math.abs(before.x + before.width / 2 - width / 2) < 1, 'Workspace must be centered');
      await page.locator('#open-library').click();
      assert.equal(await page.locator('#creator-menu').isVisible(), true);
      assert.deepEqual(await page.locator('main').boundingBox(), before, 'Dropdown must not shift the workspace');
      await page.keyboard.press('Escape');
      assert.equal(await page.locator('#creator-menu').isVisible(), false);
    }
    await page.setViewportSize({ width: 1360, height: 1000 });
    let failSelection = false;
    await page.route('**/api/selected-creator', async route => {
      const uid = route.request().postDataJSON().uid;
      await route.fulfill({ status: failSelection ? 400 : 200, contentType: 'application/json',
        body: JSON.stringify(failSelection ? { error: 'Selection failed.' } : { selected_creator: { uid, name: 'Another creator' } }) });
    });
    await page.locator('#open-library').click();
    await page.locator('#creator-search').fill('987');
    assert.equal(await page.locator('[data-quick-uid]').count(), 1);
    failSelection = true;
    await page.locator('[data-quick-uid="987654"]').click();
    await page.locator('#creator-menu-feedback').filter({ hasText: 'Selection failed.' }).waitFor();
    assert.equal(await page.locator('#creator-menu').isVisible(), true);
    failSelection = false;
    await page.locator('[data-quick-uid="987654"]').click();
    await page.waitForFunction(() => document.querySelector('#creator-menu').hidden);
    assert.match(await page.locator('#open-library').innerText(), /Another creator/);
    // Opening a menu and clicking outside closes it without navigating.
    await page.locator('#open-library').click();
    await page.locator('.panel.active').click({ position: { x: 2, y: 2 } });
    assert.equal(await page.locator('#panel-analysis').isVisible(), true);
    assert.equal(await page.locator('#creator-menu').isVisible(), false);
    await page.locator('.panel.active').click({ position: { x: 2, y: 2 } });
    assert.equal(await page.locator('#panel-settings').isVisible(), true, 'Blank space returns to previous menu view');
    await page.locator('#request-frequency').fill('2');
    assert.equal(await page.locator('#panel-settings').isVisible(), true, 'Controls must not trigger Back');
    await page.locator('#menu-back').click();
    assert.equal(await page.locator('#panel-single-video').isVisible(), true);
    await page.locator('[data-section="workspace"]').click();
    await page.locator('#open-library').click();
    await page.locator('#manage-creators').click();
    assert.equal(await page.locator('#panel-creators').isVisible(), true);
    assert.equal(await page.locator('#new-creator-name').isVisible(), true);
    await page.locator('#menu-back').click();
    assert.equal(await page.locator('#panel-analysis').isVisible(), true);
    assert.equal(await page.locator('#local-min-views').inputValue(), '200');
    if (process.env.SCREENSHOT_PATH) {
      await page.setViewportSize({ width: 1360, height: 1000 });
      await page.locator('#dataset-filters > summary').click();
      await page.evaluate(() => scrollTo(0, 0));
      await page.screenshot({ path: process.env.SCREENSHOT_PATH });
    }
    assert.deepEqual(errors, []);
    console.log('Analysis browser checks passed at 1360, 768, 390 and 320px.');
  } finally {
    await browser?.close();
    server.kill();
    await finished;
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
