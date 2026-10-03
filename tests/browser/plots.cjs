/* Offline browser regression: PLAYWRIGHT_MODULE can point to an installed package. */
const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const { once } = require("node:events");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const root = path.resolve(__dirname, "../..");
const output = fs.mkdtempSync(path.join(os.tmpdir(), "bilibili-plots-"));
const server = spawn(path.join(root, ".venv/bin/python"), ["-u", "scripts/preview_dashboard.py", "--port", "0"], { cwd: root });
let log = "";
server.stdout.on("data", (chunk) => { log += chunk; });
server.stderr.on("data", (chunk) => { log += chunk; });
const finished = once(server, "exit");

(async () => {
  let browser;
  let page;
  try {
    const deadline = Date.now() + 15000;
    while (!log.match(/http:\/\/127\.0\.0\.1:\d+/)) {
      if (Date.now() > deadline || server.exitCode !== null) throw new Error(log);
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    const url = log.match(/http:\/\/127\.0\.0\.1:\d+/)[0];
    browser = await chromium.launch({ headless: true, channel: process.env.BROWSER_CHANNEL || "chrome" });
    page = await browser.newPage({ viewport: { width: 1360, height: 1000 }, acceptDownloads: true });
    const errors = [];
    let saveRequests = 0;
    let lastSave = null;
    let fetchRequests = 0;
    page.on("pageerror", (error) => { errors.push(error.message); console.error(error.message); });
    page.on("requestfailed", (request) => { errors.push(request.url()); console.error(request.url(), request.failure()); });
    page.on("request", (request) => { if (request.url().endsWith("/api/plots/save")) { saveRequests += 1; lastSave = request.postDataJSON(); }
      if (request.url().endsWith("/api/video-action")) fetchRequests++; });
    await page.route('**/api/creators', async route => {
      const response = await route.fetch();
      const data = await response.json();
      data.creators.push(...Array.from({ length: 80 }, (_, i) => ({ uid: String(700000 + i), name: `Extra creator ${i + 1}` })));
      await route.fulfill({ response, json: data });
    });
    await page.goto(url);
    await page.locator("#status").filter({ hasText: "Layout preview" }).waitFor();

    await page.click('[data-section="explore"]');

    // Filtering a large library preserves page scroll, focus, and row identities.
    for (const width of [1360, 390, 320]) {
      await page.setViewportSize({ width, height: 620 });
      const search = page.locator('#creator-library-search');
      await search.fill('');
      await search.scrollIntoViewIfNeeded();
      await page.evaluate(() => scrollTo(0, document.querySelector('#creator-library-search').getBoundingClientRect().top + scrollY - 160));
      const beforeScroll = await page.evaluate(() => scrollY);
      assert.ok(beforeScroll > 0, 'Exercise filtering while the page is scrolled');
      const beforeHeight = await page.locator('#creators').evaluate(element => element.offsetHeight);
      const row = await page.locator('button[data-uid="987654"]').elementHandle();
      await search.pressSequentially('no matching creator', { delay: 10 });
      assert.equal(await page.evaluate(() => scrollY), beforeScroll, `Filtering must not jump the page at ${width}px`);
      assert.equal(await page.locator('#creators').evaluate(element => element.offsetHeight), beforeHeight);
      assert.equal(await page.locator('#creators .creator:visible').count(), 0);
      assert.equal(await search.evaluate(element => element === document.activeElement), true);
      assert.equal(await row.evaluate(element => element.isConnected), true, 'Search must not replace creator rows');
      assert.equal(await page.locator('#creator-search-count').innerText(), '0 of 82 creators match this search.');
      await search.fill('987');
      assert.equal(await page.locator('#creators .creator:visible').count(), 1);
      assert.equal(await page.evaluate(() => scrollY), beforeScroll);
      await search.fill('');
      const add = await page.locator('#add-creator-form > summary').boundingBox();
      const list = await page.locator('#creators').boundingBox();
      assert.ok(add.y < list.y, 'Add creator must be above the library');
      assert.ok(list.height <= 360, 'Library height must stay bounded');
    }
    await page.setViewportSize({ width: 1360, height: 1000 });

    // Selecting a creator must not refresh other sections or shift the layout.
    let selectionRequests = 0;
    let unrelatedRequests = 0;
    let failSelection = false;
    page.on("request", (request) => {
      if (/\/api\/(health|creators|plots|accounts)$/.test(request.url())) unrelatedRequests++;
    });
    await page.route("**/api/selected-creator", async (route) => {
      selectionRequests++;
      const uid = route.request().postDataJSON().uid;
      await new Promise((resolve) => setTimeout(resolve, 250));
      await route.fulfill({ status: failSelection ? 400 : 200, contentType: "application/json",
        body: JSON.stringify(failSelection ? { error: "Selection failed for testing." } : {
          selected_creator: { uid, name: uid === "123456" ? "Sample uploader" : "Another uploader with a longer name" }
        }) });
    });
    await page.locator("#creators").evaluate((element) => { element.style.maxHeight = "90px"; });
    for (const width of [1360, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      const button = page.locator('button[data-uid="987654"]');
      await button.scrollIntoViewIfNeeded();
      const scrollBefore = await page.locator("#creators").evaluate((element) => element.scrollTop);
      const before = await page.locator("#panel-creators").boundingBox();
      const handle = await button.elementHandle();
      await button.click();
      assert.equal(await page.locator("#page-feedback").isHidden(), true);
      assert.deepEqual(await page.locator("#panel-creators").boundingBox(), before);
      await page.waitForFunction(() => document.querySelector('button[data-uid="987654"]').getAttribute("aria-pressed") === "true");
      assert.equal(await handle.evaluate((element) => element.isConnected && element === document.activeElement), true);
      assert.deepEqual(await page.locator("#panel-creators").boundingBox(), before);
      const count = selectionRequests;
      assert.equal(await page.locator("#creators").evaluate((element) => element.scrollTop), scrollBefore);
      await button.click();
      assert.equal(selectionRequests, count, "Repeated selection should be a no-op");
      await page.click('button[data-uid="123456"]');
      await page.waitForFunction(() => document.querySelector('button[data-uid="123456"]').getAttribute("aria-pressed") === "true");
    }
    assert.equal(unrelatedRequests, 0, "Selecting a Creator must not refresh other dashboard sections");
    await page.locator("#creators").evaluate((element) => { element.style.maxHeight = ""; });
    failSelection = true;
    await page.click('button[data-uid="987654"]');
    await page.locator("#page-feedback").filter({ hasText: "Selection failed for testing." }).waitFor();
    assert.equal(await page.locator('button[data-uid="123456"]').getAttribute("aria-pressed"), "true");
    assert.equal(await page.locator('button[data-uid="987654"]').isEnabled(), true);
    await page.setViewportSize({ width: 1360, height: 1000 });
    await page.click('[data-section="workspace"]');
    await page.click('[data-panel="plot"]');
    await page.click("#run-plot");
    await page.locator("#plot-chart canvas").waitFor();
    await page.waitForFunction(() => !document.getElementById("save-plot").disabled);
    assert.equal(saveRequests, 0);
    assert.equal(await page.locator("#plot-save-status").textContent(), "Not saved");

    async function chartState() {
      return page.evaluate(async () => {
        const echarts = await import("/static/vendor/echarts-5.6.0.esm.min.js");
        const chart = echarts.getInstanceByDom(document.getElementById("plot-chart"));
        const option = chart.getOption();
        const relative = echarts.getInstanceByDom(document.getElementById('plot-relative-chart'))?.getOption();
        return { min: option.yAxis[0].min, max: option.yAxis[0].max, interval: option.yAxis[0].interval,
          gridTop: option.grid[0].top,
          relative: relative ? { data: relative.series[0].data, start: relative.dataZoom[0].start, end: relative.dataZoom[0].end, axis: relative.xAxis[0].type } : null,
          start: option.dataZoom[0].start, end: option.dataZoom[0].end,
          series: option.series.map(series => ({ id: series.id, type: series.type, data: series.data })),
          axis: option.xAxis[0].type, labels: option.xAxis[0].data, style: option.series[0].type, data: option.series[0].data, width: chart.getWidth() };
      });
    }
    assert.equal((await chartState()).min, 0);
    assert.equal((await chartState()).interval, 20000);
    await page.locator("#plot-workspace").screenshot({ path: path.join(output, "initial.png") });
    await page.click("#plot-zoom-in");
    assert.ok((await chartState()).start > 0);
    await page.click('[data-plot-range="30"]');
    assert.ok((await chartState()).start > 80);
    await page.click("#plot-reset");
    assert.equal((await chartState()).start, 0);
    assert.equal((await chartState()).end, 100);
    const beforeMAFetches = fetchRequests;
    await page.click('#plot-zoom-in');
    const beforeMAZoom = (await chartState()).start;
    for (const period of [5, 10, 20]) await page.click(`[data-ma-period="${period}"]`);
    let maState = await chartState();
    assert.equal(maState.start, beforeMAZoom, 'MA toggles must preserve zoom');
    assert.equal(fetchRequests, beforeMAFetches, 'MAs use already loaded values');
    assert.equal(maState.series.length, 4);
    assert.equal(maState.gridTop, 36, "MA labels must not reduce the chart area");
    for (const period of [5, 10, 20]) {
      const ma = maState.series.find(series => series.id === `ma-${period}`);
      assert.equal(ma.data[period - 2][1], null, 'No partial-window averages');
      const expected = maState.data.slice(0, period).reduce((sum, point) => sum + point[1], 0) / period;
      assert.ok(Math.abs(ma.data[period - 1][1] - expected) < 1e-8);
    }
    await page.click('[data-ma-period="20"]');
    assert.equal((await chartState()).series.length, 3, 'Disabling an MA must remove its series');
    await page.click('#plot-reset');
    await page.locator("#plot-style-trigger").click();
    await page.locator("#plot-style-options").getByRole("option", { name: "Bars", exact: true }).click();
    assert.equal((await chartState()).style, "bar");
    assert.deepEqual((await chartState()).series.slice(1).map(series => series.type), ["line", "line"]);
    await page.locator("#plot-style-trigger").click();
    await page.locator("#plot-style-options").getByRole("option", { name: "Line", exact: true }).click();

    const beforeExtraFetches = fetchRequests;
    const mainSize = await page.locator('#plot-chart').boundingBox();
    for (const id of ['ema10', 'ema20', 'median5', 'median10', 'relative20']) await page.click(`[data-indicator="${id}"]`);
    const withExtras = await chartState();
    assert.equal(fetchRequests, beforeExtraFetches);
    assert.equal((await page.locator('#plot-chart').boundingBox()).height, mainSize.height, 'Extra panel must preserve main chart height');
    assert.equal(withExtras.series.length, 7);
    assert.equal(withExtras.series.find(series => series.id === 'ema10').data[8][1], null);
    const seed10 = withExtras.data.slice(0, 10).reduce((total, point) => total + point[1], 0) / 10;
    assert.equal(withExtras.series.find(series => series.id === 'ema10').data[9][1], seed10);
    const sorted5 = withExtras.data.slice(0, 5).map(point => point[1]).sort((a, b) => a - b);
    assert.equal(withExtras.series.find(series => series.id === 'median5').data[4][1], sorted5[2]);
    assert.equal(withExtras.relative.data[19][1], null);
    const baseline20 = withExtras.data.slice(0, 20).reduce((total, point) => total + point[1], 0) / 20;
    assert.equal(withExtras.relative.data[20][1], withExtras.data[20][1] / baseline20);
    await page.click('#plot-zoom-in');
    let linked = await chartState();
    assert.equal(linked.relative.start, linked.start);
    assert.equal(linked.relative.end, linked.end);
    await page.evaluate(async () => {
      const lib = await import('/static/vendor/echarts-5.6.0.esm.min.js');
      lib.getInstanceByDom(document.getElementById('plot-relative-chart')).dispatchAction({ type: 'dataZoom', start: 40, end: 80 });
    });
    linked = await chartState();
    assert.equal(linked.start, 40);
    assert.equal(linked.end, 80);
    await page.click('#plot-reset');
    const fetched = fetchRequests;
    await page.locator('#plot-axis-trigger').click();
    await page.locator('#plot-axis-options').getByRole('option', { name: 'Video number (equal spacing)', exact: true }).click();
    assert.equal((await chartState()).axis, 'category');
    assert.equal((await chartState()).relative.axis, 'category');
    assert.equal((await chartState()).series[1].data[3], null);
    assert.equal(typeof (await chartState()).series[1].data[4], 'number');
    assert.deepEqual((await chartState()).labels, Array.from({ length: 64 }, (_, i) => i + 1));
    assert.equal(fetchRequests, fetched, 'Changing the axis must reuse loaded data');
    assert.equal(await page.locator('[data-plot-range="30"]').isDisabled(), true);
    const spacing = await page.evaluate(async () => {
      const lib = await import('/static/vendor/echarts-5.6.0.esm.min.js');
      const chart = lib.getInstanceByDom(document.getElementById('plot-chart'));
      return [0, 1, 2, 3].map(x => chart.convertToPixel({ xAxisIndex: 0 }, x));
    });
    assert.ok(Math.abs((spacing[1] - spacing[0]) - (spacing[3] - spacing[2])) < 0.1, 'Videos must be equally spaced');
    await page.locator('#plot-axis-trigger').click();
    await page.locator('#plot-axis-options').getByRole('option', { name: 'Published time', exact: true }).click();
    assert.equal((await chartState()).axis, 'time');
    assert.equal(await page.locator('[data-plot-range="30"]').isEnabled(), true);
    const canvas = page.locator("#plot-chart canvas").first();
    await canvas.scrollIntoViewIfNeeded();
    const box = await canvas.boundingBox();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.screenshot({ path: path.join(output, "hover.png") });
    assert.equal((await chartState()).data.length, 64);
    await page.waitForFunction(() => !document.querySelector("#plot-inspection strong").textContent.startsWith("Video 64:"));
    await page.mouse.wheel(0, -250);
    await page.waitForFunction(async () => {
      const lib = await import("/static/vendor/echarts-5.6.0.esm.min.js");
      const zoom = lib.getInstanceByDom(document.getElementById("plot-chart")).getOption().dataZoom[0];
      return zoom.end - zoom.start < 100;
    });
    const beforePan = (await chartState()).start;
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 70, box.y + box.height / 2, { steps: 12 });
    await page.mouse.up();
    assert.notEqual((await chartState()).start, beforePan);
    assert.equal((await chartState()).min, 0);
    await page.click("#plot-reset");

    for (const width of [1360, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.waitForFunction(() => {
        const host = document.getElementById("plot-chart");
        return Math.abs(host.querySelector("canvas").getBoundingClientRect().width - host.clientWidth) < 2;
      });
      const chartBox = await page.locator('#plot-chart').boundingBox();
      const legendBox = await page.locator('#plot-legend').boundingBox();
      assert.ok(legendBox.y >= chartBox.y + chartBox.height, 'Legend must stay outside the chart');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `Overflow at ${width}`);
      const pixels = await canvas.evaluate((element) => {
        const bytes = element.getContext("2d").getImageData(0, 0, element.width, element.height).data;
        let colored = 0;
        for (let i = 0; i < bytes.length; i += 4) if (bytes[i + 3] && bytes[i] < 120 && bytes[i + 2] > bytes[i] * 1.3) colored++;
        return colored;
      });
      assert.ok(pixels > 100, `Blank chart at ${width}`);
      await page.locator("#plot-workspace").screenshot({ path: path.join(output, `${width}-plot.png`) });
    }
    await page.locator('#plot-axis-trigger').click();
    await page.locator('#plot-axis-options').getByRole('option', { name: 'Video number (equal spacing)', exact: true }).click();
    const downloadEvent = page.waitForEvent("download");
    await page.click("#download-plot");
    const download = await downloadEvent;
    const downloadPath = path.join(output, "view.png");
    await download.saveAs(downloadPath);
    assert.equal(fs.readFileSync(downloadPath).subarray(1, 4).toString(), "PNG");
    assert.equal(saveRequests, 0);
    await page.click("#save-plot");
    await page.locator("#plot-save-status a").waitFor();
    await page.waitForFunction(() => document.getElementById("page-feedback").hidden);
    assert.equal(saveRequests, 1);
    assert.equal(lastSave.axis_mode, "number");
    assert.deepEqual(lastSave.ma_periods, [5, 10]);
    assert.deepEqual(lastSave.indicators, ["ema10", "ema20", "median5", "median10", "relative20"]);
    assert.equal(await page.locator("#save-plot").isDisabled(), true);
    await page.click('[data-ma-period="20"]');
    assert.equal(await page.locator('#save-plot').isEnabled(), true, 'Changing overlays should enable saving the new chart');
    await page.click('[data-panel="saved-plots"]');
    await page.locator(".saved-plot img").waitFor();
    await page.click('[data-section="workspace"]');
    await page.click('[data-panel="plot"]');

    const cases = [[0], [10000], [0.001, 0.002], [null, 0, 10], [], [1e8, 2e8]];
    for (const values of cases) {
      await page.evaluate(async (values) => {
        const view = await import("/static/js/views/plots.js");
        view.renderPlot({ y_label: "Test", points: values.map((value, index) => ({ value, title: `<img onerror=alert(1)> ${index}`, label: `2026-09-${String(index + 1).padStart(2, "0")} 12:00:00` })) });
        view.syncPlotControls();
      }, values);
      assert.equal(await page.locator("#plot-inspection img").count(), 0);
      if (values.length) {
        const state = await chartState();
        assert.equal(state.min, 0);
        assert.equal(state.data.length, values.filter((value) => value !== null).length);
        assert.ok(state.max > Math.max(...values.filter((value) => value !== null)));
        assert.match(await page.locator('#plot-ma-status').innerText(), /MA5 needs 5 videos/);
        assert.ok(state.series[1].data.every(value => value === null), 'Short selections must not invent averages');
      } else {
        assert.equal(await page.locator("#plot-chart canvas").count(), 0);
        assert.equal(await page.locator("#download-plot").isDisabled(), true);
      }
    }
    assert.deepEqual(await page.evaluate(async () => {
      const view = await import("/static/js/views/plots.js");
      return [view.formatAxisNumber(10000), view.formatAxisNumber(1000000), view.formatAxisNumber(0.001)];
    }), ["10,000", "1,000,000", "0.001"]);
    assert.deepEqual(await page.evaluate(async () => {
      const { movingAverage } = await import('/static/js/views/plots.js');
      return [movingAverage([1, 2, 3, 4, 5, 6], 5), movingAverage([100, 0, 0, 0, 0, 0], 5), movingAverage([], 10)];
    }), [[null, null, null, null, 3, 4], [null, null, null, null, 20, 0], []]);
    // A large value before the zoomed interval must still contribute to the visible MA.
    await page.evaluate(async () => {
      const view = await import('/static/js/views/plots.js');
      const lib = await import('/static/vendor/echarts-5.6.0.esm.min.js');
      view.renderPlot({ y_label: 'Test', points: [1000, 0, 0, 0, 0, 0].map((value, i) => ({ value, title: String(i), label: `2026-09-0${i + 1} 12:00:00` })) });
      lib.getInstanceByDom(document.getElementById('plot-chart')).dispatchAction({ type: 'dataZoom', start: 80, end: 100 });
    });
    assert.ok((await chartState()).max > 200, 'Zoom scale must include the visible moving average');
    assert.deepEqual(await page.evaluate(async () => {
      const { exponentialAverage, rollingMedian, relativePerformance } = await import('/static/js/indicators.js');
      return [exponentialAverage([1, 2, 3, 10, 0], 3), rollingMedian([1, 100, 2, 3, 4, 5], 5),
        rollingMedian([1, 2, 3, 4], 4), relativePerformance([...Array(20).fill(10), 30]).at(-1),
        relativePerformance([...Array(20).fill(0), 30]).at(-1)];
    }), [[null, null, 2, 6, 3], [null, null, null, null, 3, 4], [null, null, null, 2.5], 3, null]);
    for (const id of ['ema10', 'ema20', 'median5', 'median10', 'relative20']) await page.click(`[data-indicator="${id}"]`);
    assert.equal((await chartState()).series.length, 4, 'Disabled extra overlays must be removed');
    assert.equal(await page.locator('#plot-relative-panel').isHidden(), true);
    assert.deepEqual(errors, []);
    console.log(`Browser plot checks passed. Screenshots: ${output}`);
  } catch (error) {
    if (page) await page.screenshot({ path: path.join(output, "failure.png") }).catch(() => {});
    console.error(`Browser failure artifacts: ${output}\n${log}`);
    throw error;
  } finally {
    if (browser) await browser.close();
    server.kill("SIGINT");
    await finished;
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
