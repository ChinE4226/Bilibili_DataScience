const openPanel = require('./workspace.cjs');
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
    // Keyboard selection, dismissal, and restored native values stay synchronized.
    await page.locator('#selection-kind-trigger').focus();
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('End');
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#selection-kind').inputValue(), 'metric');
    assert.equal(await page.locator('#selection-metric').isVisible(), true);
    await page.locator('#selection-kind-trigger').click();
    await page.keyboard.press('Home');
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#selection-kind').inputValue(), 'metric', 'Escape must cancel the pending choice');
    await page.locator('#selection-kind-trigger').click();
    await page.keyboard.press('Home');
    await page.keyboard.press('Enter');
    assert.equal(await page.locator('#selection-position').isVisible(), true);
    let fetchGate = null;
    await page.route('**/api/video-action', async route => {
      const response = await route.fetch();
      if (fetchGate) await fetchGate;
      const data = await response.json();
      data.dataset.collection = { requested: 24, examined: 26, skipped_invalid: 2, shortfall: 0 };
      data.dataset.filter_counts = { fetched: 24, included: 24, excluded: 0, view_range: 0 };
      await route.fulfill({ response, json: data });
    });
    assert.equal(await page.locator('#open-library').isVisible(), true, 'Creator is available before any Back history');
    await page.locator('#fetch-dataset').click();
    await page.locator('#dataset-status').filter({ hasText: 'Fetched 24' }).waitFor();
    assert.match(await page.locator('#dataset-status').innerText(), /24 valid videos · 26 checked · 2 invalid skipped · 24 requested/);
    assert.match(await page.locator('#dataset-filter-status').innerText(), /24 fetched · 24 included · 0 excluded/);
    await openPanel(page, 'analysis');
    assert.equal(await page.locator('.selection-card').isVisible(), false);
    assert.equal(await page.locator('#analysis-field-trigger').isDisabled(), true);
    await page.locator('#run-analysis').click();
    await page.locator('#analysis-result svg').first().waitFor();
    assert.equal(await page.locator('#analysis-result svg').count(), 2);
    assert.equal(actions.at(-1).reuse_only, true);
    const previous = actions.length;
    await page.locator('#analysis-field-trigger').click();
    await page.locator('#analysis-field-options').getByRole('option', { name: 'Likes', exact: true }).click();
    assert.match(await page.locator('#analysis-result').innerText(), /Likes distribution/);
    assert.equal(await page.locator('#analysis-metric-title').innerText(), 'Likes overview');
    assert.equal(await page.locator('#analysis-result .analysis-table').first().locator('tbody tr td').nth(1).innerText(), '23');
    assert.equal(actions.length, previous, 'Changing chart metric must stay local');
    await openPanel(page, 'videos');
    assert.equal(await page.locator('.selection-card').isVisible(), true);
    await page.locator('#dataset-filters > summary').click();
    await page.locator('#local-min-views').fill('200');
    await openPanel(page, 'analysis');
    await page.locator('#run-analysis').click();
    await page.waitForFunction(() => !document.querySelector('#run-analysis').disabled);
    assert.equal(actions.at(-1).local_filter.minimum_views, '200');
    // Navigation preserves the dataset controls and the last workspace view.
    const requestCount = actions.length;
    await page.locator('[data-section="explore"]').click();
    assert.equal(await page.locator('#panel-creators').isVisible(), true);
    assert.equal(await page.locator('.selection-card').isVisible(), false);
    await openPanel(page, 'single-video');
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
      await page.locator('#analysis-field-trigger').click();
      const menuBox = await page.locator('#analysis-field-options').boundingBox();
      assert.ok(menuBox.x >= 0 && menuBox.x + menuBox.width <= width, 'Select menu must fit the viewport');
      const panelBox = await page.locator('.panel.active').boundingBox();
      const triggerBox = await page.locator('#analysis-field-trigger').boundingBox();
      await page.mouse.click(panelBox.x + 2, triggerBox.y + 10);
      assert.equal(await page.locator('#analysis-field-options').isVisible(), false);
      assert.equal(await page.locator('#panel-analysis').isVisible(), true, 'Closing select menu must not trigger Back');
      await page.locator('#open-library').scrollIntoViewIfNeeded();
      const backBox = await page.locator('#menu-back').boundingBox();
      const creatorBox = await page.locator('#open-library').boundingBox();
      assert.ok(Math.abs(backBox.y - creatorBox.y) < 1, 'Creator and Back must share a row');
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
    for (const panel of ['division', 'plot', 'saved-plots']) {
      await openPanel(page, panel);
      assert.equal(await page.locator('.selection-card').isVisible(), false);
      assert.equal(await page.locator('#fetch-dataset').isVisible(), false);
    }
    await openPanel(page, 'videos');
    await page.locator('#fetch-dataset').click();
    await page.waitForFunction(() => !document.querySelector('#fetch-dataset').disabled);
    assert.equal(await page.locator('#panel-videos').isVisible(), true);
    // Finishing a fetch must respect a page chosen while it was running.
    let releaseFetch;
    fetchGate = new Promise(resolve => { releaseFetch = resolve; });
    await page.locator('#fetch-dataset').click();
    await openPanel(page, 'plot');
    assert.equal(await page.locator('.selection-card').isVisible(), false);
    releaseFetch();
    await page.waitForFunction(() => !document.querySelector('#fetch-dataset').disabled);
    assert.equal(await page.locator('#panel-plot').isVisible(), true, 'Fetch completion must not navigate away');
    fetchGate = null;
    await openPanel(page, 'analysis');
    // Random samples and weekly averages share Sampling without changing the creator dataset.
    const beforeWeekly = actions.length;
    await openPanel(page, 'sampling');
    assert.equal(await page.locator('[data-panel="weekly"]').count(), 0);
    assert.equal(await page.locator('#sampling-random').isVisible(), true);
    await page.locator('#sample-keyword').fill('camera');
    await page.locator('#sample-size').fill('5');
    await page.locator('#sample-pool-size').fill('30');
    await page.locator('#sample-minimum').fill('2k');
    await page.locator('#sample-maximum').fill('2400');
    await page.locator('#sample-seed').fill('42');
    await page.locator('#fetch-random-sample').click();
    await page.locator('#sample-result h3').filter({ hasText: 'Random sample' }).waitFor();
    await page.waitForFunction(() => !document.querySelector('#fetch-random-sample').disabled);
    assert.match(await page.locator('#sample-result').innerText(), /5\s+Eligible candidates\s+5/);
    assert.equal(await page.locator('#sample-result .analysis-table').first().locator('tbody tr').first().locator('td').nth(3).innerText(), '2,200');
    const sampledResult = await page.locator('#sample-result').innerHTML();
    await page.locator('#sample-keyword').fill('');
    await page.locator('#fetch-random-sample').click();
    await page.locator('#page-feedback').filter({ hasText: 'Enter a search keyword' }).waitFor();
    assert.equal(await page.locator('#sample-result').innerHTML(), sampledResult, 'Failed random collection retains the prior sample');
    await page.locator('#sample-keyword').fill('camera');
    await page.locator('#sample-size').fill('10');
    await page.locator('#fetch-random-sample').click();
    await page.locator('#sample-result').filter({ hasText: '5 fewer videos than requested' }).waitFor();
    await page.waitForFunction(() => !document.querySelector('#fetch-random-sample').disabled);
    for (const width of [1360, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Sampling overflow at ${width}px`);
    }
    await page.locator('#sample-mode-random').focus();
    await page.keyboard.press('ArrowRight');
    assert.equal(await page.locator('#sampling-weekly').isVisible(), true);
    assert.equal(await page.locator('#sampling-random').isVisible(), false);
    await page.locator('#sample-mode-weekly').click();
    assert.equal(await page.locator('#open-library').isVisible(), false);
    assert.equal(await page.locator('.selection-card').isVisible(), false);
    await page.locator('#fetch-weekly').click();
    await page.locator('#weekly-result h3').filter({ hasText: 'Weekly issue 393' }).waitFor();
    await page.waitForFunction(() => !document.querySelector('#fetch-weekly').disabled);
    assert.equal(await page.locator('#weekly-result .analysis-table').first().locator('tbody tr').first().locator('td').nth(3).innerText(), '1,250');
    assert.match(await page.locator('#weekly-result').innerText(), /Mean per video gives each eligible video equal weight/);
    const weeklyResult = await page.locator('#weekly-result').innerHTML();
    await page.locator('#weekly-source').fill('https://example.com/');
    await page.locator('#fetch-weekly').click();
    await page.locator('#page-feedback').filter({ hasText: 'Enter a Bilibili weekly page URL' }).waitFor();
    assert.equal(await page.locator('#weekly-result').innerHTML(), weeklyResult, 'Failed collection retains the previous report');
    assert.equal(actions.length, beforeWeekly, 'Weekly analysis must not refresh the creator dataset');
    await page.locator('#sample-mode-random').click();
    assert.match(await page.locator('#sample-result').innerText(), /5 fewer videos than requested/);
    await page.locator('#sample-mode-weekly').click();
    for (const width of [1360, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Weekly overflow at ${width}px`);
    }
    await openPanel(page, 'analysis');
    if (process.env.SCREENSHOT_PATH) {
      await page.setViewportSize({ width: 1360, height: 1000 });
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
