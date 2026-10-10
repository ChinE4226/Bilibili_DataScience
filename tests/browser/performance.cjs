/* Offline pagination and tracking invalidation; no Bilibili requests. */
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
    const errors = [], calls = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => calls.push(new URL(request.url()).pathname));
    await page.route('**/api/health', async route => {
      const response = await route.fetch();
      await route.fulfill({ response, json: { ...await response.json(), tracking_version: 3 } });
    });
    let revision = 'fixture:1', failRevision = false, views = 100;
    const bvid = 'BV1xx411c7mD';
    const time = '2026-10-08T02:00:00Z';
    await page.route('**/api/tracking**', async route => {
      const endpoint = new URL(route.request().url()).pathname;
      if (endpoint === '/api/tracking/revision' && failRevision) {
        await route.fulfill({ status: 503, json: { error: 'Temporary local failure' } });
        return;
      }
      const video = { bvid, title: 'Tracked video', views, collected_at: time };
      const fixtures = {
        '/api/tracking/revision': { revision },
        '/api/tracking': { revision, path: '/preview/tracking.sqlite3', counts: { trackers: 1, creator_watches: 0, observations: 1 },
          trackers: [{ ...video, id: 1, status: 'active', interval_seconds: 600, next_check_at: time }],
          videos: [video], creator_watches: [], releases: [] },
        '/api/tracking/history': { errors: [] },
        '/api/tracking/analysis': { bvid, metric: 'views', points: [{ id: 1, value: views, collected_at: time, video_age_hours: 1 }],
          summary: { observations: 1, missing_observations: 0, counter_decreases: 0, baseline_value: views, latest_value: views, net_change: 0, elapsed_hours: 0 } }
      };
      assert.ok(fixtures[endpoint], `Unexpected tracking request ${endpoint}`);
      await route.fulfill({ json: fixtures[endpoint] });
    });
    await page.goto(log.match(/http:\/\/127\.0\.0\.1:\d+/)[0]);
    await page.locator('#status').filter({ hasText: 'Layout preview' }).waitFor();

    // A real sampled collection retains every row for analysis, with a bounded DOM.
    await openPanel(page, 'sampling');
    await page.locator('#sample-keyword').fill('camera');
    await page.locator('#sample-size').fill('123');
    await page.locator('#sample-pool-size').fill('150');
    await page.locator('#sample-seed').fill('fixed');
    await page.locator('#fetch-random-sample').click();
    await page.locator('#sample-result [data-cohort-videos]').waitFor({ state: 'attached' });
    await page.waitForFunction(() => !document.querySelector('#fetch-random-sample').disabled);
    const videos = page.locator('#sample-result [data-cohort-videos]');
    assert.equal(await videos.locator('tbody tr').count(), 0, 'Collapsed lists must not render rows');
    await page.locator('#sample-result summary').filter({ hasText: 'Included videos (123)' }).click();
    await videos.locator('tbody tr').first().waitFor();
    assert.equal(await videos.locator('tbody tr').count(), 50);
    const firstTitle = await videos.locator('tbody tr').first().innerText();
    const dataRequests = () => calls.filter(call => ['/api/video-action', '/api/random-sample', '/api/weekly-analysis'].includes(call)).length;
    const beforePaging = dataRequests();
    await videos.getByRole('button', { name: 'Next', exact: true }).click();
    assert.equal(await videos.locator('tbody tr').count(), 50);
    assert.notEqual(await videos.locator('tbody tr').first().innerText(), firstTitle);
    await videos.getByRole('button', { name: 'Next', exact: true }).click();
    assert.equal(await videos.locator('tbody tr').count(), 23);
    assert.equal(await videos.getByRole('button', { name: 'Next', exact: true }).isDisabled(), true);
    assert.equal(await videos.getByRole('button', { name: 'Previous', exact: true }).evaluate(button => button === document.activeElement), true);
    assert.equal(dataRequests(), beforePaging, 'Paging must not fetch collection data');
    for (const width of [1360, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Pagination overflow at ${width}px`);
    }
    await page.locator('#sample-result [data-use-collection]').click();
    await page.waitForFunction(() => !document.querySelector('#run-analysis').disabled);
    assert.match(await page.locator('#analysis-dataset-status').innerText(), /123 after local filters/);

    // Dataset rendering also handles exact boundaries, empty results and HTML titles.
    await openPanel(page, 'videos');
    await page.evaluate(async () => {
      const { renderVideos } = await import('/static/js/views/videos.js');
      window.paginationFixture = Array.from({ length: 123 }, (_, i) => ({ title: i ? `Video ${i + 1}` : '<img src=x onerror=alert(1)>', bvid: `video-${i}`, views: i }));
      renderVideos('videos-result', window.paginationFixture);
    });
    assert.equal(await page.locator('#videos-result tbody tr').count(), 50);
    assert.equal(await page.locator('#videos-result img').count(), 0);
    await page.locator('#videos-result').getByRole('button', { name: 'Next', exact: true }).click();
    assert.match(await page.locator('#videos-result tbody tr').first().innerText(), /Video 51/);
    await page.evaluate(async () => {
      const { renderVideos } = await import('/static/js/views/videos.js');
      renderVideos('videos-result', window.paginationFixture.slice(0, 50));
    });
    assert.equal(await page.locator('#videos-result .table-pagination').count(), 0);
    await page.evaluate(async () => (await import('/static/js/views/videos.js')).renderVideos('videos-result', []));
    assert.match(await page.locator('#videos-result').innerText(), /No results/);

    // Idle polls preserve DOM and focus, and skip all history requests.
    await page.locator('[data-group="tracking"]').click();
    await page.locator('#tracking-trackers [data-history-bvid]').click();
    await page.locator('#tracking-chart svg').waitFor();
    await page.waitForFunction(() => !document.querySelector('#tracking-refresh').disabled);
    await page.locator('#tracking-trackers [data-check-tracker]').focus();
    await page.evaluate(() => { window.trackerTable = document.querySelector('#tracking-trackers table'); });
    const count = endpoint => calls.filter(call => call === endpoint).length;
    const analysisBefore = count('/api/tracking/analysis'), overviewBefore = count('/api/tracking');
    const poll = () => page.evaluate(async () => (await import('/static/js/views/tracking.js')).refreshTracking({ force: false }));
    await poll(); await poll();
    assert.equal(count('/api/tracking/analysis'), analysisBefore);
    assert.equal(count('/api/tracking'), overviewBefore);
    assert.equal(await page.evaluate(() => window.trackerTable === document.querySelector('#tracking-trackers table')), true);
    assert.equal(await page.locator('#tracking-trackers [data-check-tracker]').evaluate(button => button === document.activeElement), true);
    revision = 'fixture:2'; views = 160;
    await poll();
    assert.equal(count('/api/tracking/analysis'), analysisBefore + 1);
    assert.match(await page.locator('#tracking-analysis-summary').innerText(), /160/);
    assert.equal(await page.locator('#tracking-trackers [data-check-tracker]').evaluate(button => button === document.activeElement), true);
    failRevision = true;
    assert.match(await page.evaluate(async () => {
      try { await (await import('/static/js/views/tracking.js')).refreshTracking({ force: false }); }
      catch (error) { return error.message; }
    }), /Temporary local failure/);
    failRevision = false;
    await poll();
    assert.equal(count('/api/tracking/analysis'), analysisBefore + 1, 'Failed status checks retain the last good revision');
    await page.locator('#tracking-refresh').click();
    await page.waitForFunction(() => !document.querySelector('#tracking-refresh').disabled);
    assert.equal(count('/api/tracking/analysis'), analysisBefore + 2, 'Manual refresh must reload history');
    assert.deepEqual(errors, []);
    console.log('Pagination, full-cohort analysis, responsive layout and tracking invalidation checks passed.');
  } finally {
    await browser?.close();
    server.kill();
    await finished;
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
