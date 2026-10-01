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
    page.on("pageerror", (error) => { errors.push(error.message); console.error(error.message); });
    page.on("requestfailed", (request) => { errors.push(request.url()); console.error(request.url(), request.failure()); });
    page.on("request", (request) => { if (request.url().endsWith("/api/plots/save")) saveRequests += 1; });
    await page.goto(url);
    await page.locator("#status").filter({ hasText: "Layout preview" }).waitFor();

    await page.click('[data-section="explore"]');

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
        return { min: option.yAxis[0].min, max: option.yAxis[0].max, interval: option.yAxis[0].interval,
          start: option.dataZoom[0].start, end: option.dataZoom[0].end,
          style: option.series[0].type, data: option.series[0].data, width: chart.getWidth() };
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
    await page.selectOption("#plot-style", "bar");
    assert.equal((await chartState()).style, "bar");
    await page.selectOption("#plot-style", "line");

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
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, `Overflow at ${width}`);
      const pixels = await canvas.evaluate((element) => {
        const bytes = element.getContext("2d").getImageData(0, 0, element.width, element.height).data;
        let colored = 0;
        for (let i = 0; i < bytes.length; i += 4) if (bytes[i + 3] && bytes[i] < 100 && bytes[i + 1] > bytes[i] * 1.3) colored++;
        return colored;
      });
      assert.ok(pixels > 100, `Blank chart at ${width}`);
      await page.locator("#plot-workspace").screenshot({ path: path.join(output, `${width}-plot.png`) });
    }
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
    assert.equal(await page.locator("#save-plot").isDisabled(), true);
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
      } else {
        assert.equal(await page.locator("#plot-chart canvas").count(), 0);
        assert.equal(await page.locator("#download-plot").isDisabled(), true);
      }
    }
    assert.deepEqual(await page.evaluate(async () => {
      const view = await import("/static/js/views/plots.js");
      return [view.formatAxisNumber(10000), view.formatAxisNumber(1000000), view.formatAxisNumber(0.001)];
    }), ["10,000", "1,000,000", "0.001"]);
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
