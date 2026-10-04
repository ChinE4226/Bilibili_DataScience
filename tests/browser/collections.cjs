/* Shared cohort analysis through real local routes; no Bilibili or disk exports. */
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
    const errors = [], actions = [], collections = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      if (request.method() !== 'POST') return;
      if (request.url().endsWith('/api/video-action')) actions.push(request.postDataJSON());
      if (/\/api\/(random-sample|weekly-analysis)$/.test(request.url())) collections.push(request.url());
    });
    const settled = async () => page.waitForFunction(() => !document.querySelector('#run-analysis').disabled && !document.querySelector('#fetch-dataset').disabled);
    const choose = async (id, label) => {
      await page.locator(`#${id}-trigger`).click();
      await page.locator(`#${id}-options`).getByRole('option', { name: label, exact: true }).click();
    };
    await page.goto(log.match(/http:\/\/127\.0\.0\.1:\d+/)[0]);
    await page.locator('#status').filter({ hasText: 'Layout preview' }).waitFor();
    await page.locator('#fetch-dataset').click();
    await settled();
    const creatorStatus = await page.locator('#dataset-status').innerText();
    assert.match(await page.locator('#dataset-count-flow').innerText(), /24 valid → 24 after local filters/);
    await openPanel(page, 'sampling');
    await page.locator('#sample-mode-weekly').click();
    await page.locator('#weekly-source').fill('393');
    await page.locator('#fetch-weekly').click();
    await page.locator('#weekly-result [data-use-collection]').waitFor();
    await settled();
    assert.equal(await page.locator('#dataset-status').innerText(), creatorStatus);
    await page.locator('#weekly-result [data-use-collection]').click();
    await settled();
    assert.equal(await page.locator('#panel-analysis').isVisible(), true);
    assert.match(await page.locator('#analysis-dataset-status').innerText(), /Weekly popular.*24 requested → 24 checked → 24 valid → 24 after local filters/);
    assert.match(await page.locator('#analysis-result').innerText(), /1,250/);
    const weeklyId = await page.locator('#analysis-collection').inputValue();
    assert.ok(weeklyId);
    assert.equal(actions.at(-1).collection_id, weeklyId);
    assert.equal(actions.at(-1).refresh, undefined);
    await page.locator('#analysis-min-views').fill('1000');
    await page.locator('#run-analysis').click();
    await settled();
    assert.match(await page.locator('#analysis-dataset-status').innerText(), /24 valid → 15 after local filters/);
    assert.match(await page.locator('#analysis-filter-status').innerText(), /9 excluded by local view filters/);
    assert.equal(await page.locator('#dataset-status').innerText(), creatorStatus);
    await openPanel(page, 'plot');
    await page.locator('#run-plot').click();
    await settled();
    assert.equal(await page.locator('#plot-workspace').isVisible(), true);
    assert.match(await page.locator('#plot-context').innerText(), /Weekly popular/);
    assert.match(await page.locator('#plot-data-label').innerText(), /15 videos/);
    assert.equal(await page.locator('#save-plot').isEnabled(), true);
    await openPanel(page, 'division');
    await page.locator('#run-division').click();
    await settled();
    assert.equal(await page.locator('#division-result tbody tr').count(), 15);
    await page.locator('#division-denominator-trigger').click();
    assert.equal(await page.locator('#division-denominator-options').getByRole('option', { name: 'Followers', exact: true }).getAttribute('aria-disabled'), 'true');
    await page.keyboard.press('Escape');
    await openPanel(page, 'tasks');
    assert.equal(await page.locator('#batch-fetch').isChecked(), false);
    assert.equal(await page.locator('#batch-fetch').isDisabled(), true);
    assert.match(await page.locator('#batch-context').innerText(), /Weekly popular/);
    await openPanel(page, 'analysis');
    await choose('analysis-collection', 'Creator dataset');
    assert.equal(await page.locator('#plot-workspace').isHidden(), true);
    assert.match(await page.locator('#analysis-result').innerText(), /Run Analyze Dataset/);
    assert.equal(await page.locator('#batch-fetch').isEnabled(), true);
    assert.equal(await page.locator('#local-min-views').inputValue(), '');
    await page.locator('#run-analysis').click();
    await settled();
    assert.equal(actions.at(-1).collection_id, null);
    await openPanel(page, 'sampling');
    await page.locator('#sample-mode-random').click();
    await page.locator('#sample-keyword').fill('camera');
    await page.locator('#sample-size').fill('3');
    await page.locator('#sample-pool-size').fill('6');
    await page.locator('#sample-seed').fill('fixed');
    await page.locator('#fetch-random-sample').click();
    await settled();
    await page.locator('#sample-result [data-use-collection]').click();
    await settled();
    assert.match(await page.locator('#analysis-dataset-status').innerText(), /3 requested → 6 candidate entries → 6 eligible → 3 sampled → 3 after local filters/);
    await page.locator('#analysis-provenance > summary').click();
    assert.match(await page.locator('#analysis-scope-status').innerText(), /seed fixed.*bounded search pool/);
    assert.equal(await page.locator('#analysis-min-views').inputValue(), '', 'Do not inherit weekly or creator filters');
    await page.locator('#analysis-collection-trigger').click();
    assert.equal(await page.locator('#analysis-collection-options').getByRole('option').count(), 3, 'Newly collected sources appear in the project menu');
    await page.keyboard.press('Escape');
    assert.equal(collections.length, 2, 'Analysis never recollects either source');
    assert.ok(actions.filter(action => action.collection_id).every(action => !action.refresh));
    for (const width of [1360, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `Collection controls overflow at ${width}`);
    }
    await page.setViewportSize({ width: 1360, height: 1000 });
    await choose('analysis-collection', 'Creator dataset');
    await openPanel(page, 'plot');
    await page.locator('#run-plot').click();
    await settled();
    assert.equal(await page.locator('#plot-workspace').isVisible(), true);
    await page.route('**/api/video-action', async route => {
      if (!route.request().postDataJSON().refresh) return route.continue();
      const response = await route.fetch(), data = await response.json();
      data.dataset.collected_at = '2026-10-04T01:00:00Z';
      await route.fulfill({ response, json: data });
    });
    await openPanel(page, 'videos');
    await page.locator('#fetch-dataset').click();
    await settled();
    assert.equal(await page.locator('#plot-workspace').isHidden(), true, 'A new creator collection clears the old chart');
    assert.match(await page.locator('#analysis-result').innerText(), /Run Analyze Dataset/);
    assert.deepEqual(errors, []);
    console.log('Shared collection analysis, filters, menus, provenance and mobile widths passed.');
  } finally {
    await browser?.close();
    server.kill('SIGINT');
    await finished;
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
