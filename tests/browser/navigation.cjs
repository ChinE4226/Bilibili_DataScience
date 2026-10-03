/* Offline regression for scroll position when a shorter page replaces a taller one. */
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '../..');
const server = spawn(path.join(root, '.venv/bin/python'), ['-B', '-u', 'scripts/preview_dashboard.py', '--port', '0'], { cwd: root });
const finished = once(server, 'exit');
let log = '';
server.stdout.on('data', chunk => { log += chunk; });
server.stderr.on('data', chunk => { log += chunk; });

(async () => {
  let browser;
  try {
    const deadline = Date.now() + 15000;
    while (!log.match(/http:\/\/127\.0\.0\.1:\d+/)) {
      if (Date.now() > deadline || server.exitCode !== null) throw new Error(log);
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    browser = await chromium.launch({ headless: true, channel: process.env.BROWSER_CHANNEL || 'chrome' });
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const paint = () => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    for (const width of [1360, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.goto(log.match(/http:\/\/127\.0\.0\.1:\d+/)[0]);
      await page.locator('#status').filter({ hasText: 'Layout preview' }).waitFor();
      await page.locator('[data-panel="sampling"]').click();
      await page.locator('#sample-keyword').fill('camera');
      await page.locator('#sample-size').fill('5');
      await page.locator('#sample-pool-size').fill('20');
      await page.locator('#fetch-random-sample').click();
      await page.locator('#sample-result h3').first().waitFor();
      await page.waitForFunction(() => !document.querySelector('#fetch-random-sample').disabled);
      await page.locator('[data-panel="division"]').evaluate(button => scrollTo(0, button.getBoundingClientRect().top + scrollY - 140));
      await paint();
      const before = await page.evaluate(() => scrollY);
      assert.ok(before > 50, `Exercise a scrolled page at ${width}px`);
      await page.locator('[data-panel="division"]').click();
      await paint();
      assert.equal(await page.evaluate(() => scrollY), before, `Shorter Workspace page must preserve scroll at ${width}px`);
      assert.equal(await page.locator('#panel-division').isVisible(), true);
      await page.locator('#menu-back').click();
      await paint();
      assert.equal(await page.evaluate(() => scrollY), before, 'Back preserves the viewport');
      assert.equal(await page.locator('#panel-sampling').isVisible(), true);
      await page.locator('#sample-mode-weekly').click();
      await paint();
      assert.equal(await page.evaluate(() => scrollY), before, 'Shorter sampling tab preserves the viewport');
      for (const panel of ['analysis', 'plot', 'saved-plots', 'tasks', 'videos']) {
        await page.locator(`[data-panel="${panel}"]`).click();
        await paint();
        assert.equal(await page.evaluate(() => scrollY), before, `${panel} preserves the viewport at ${width}px`);
      }
      await page.locator('[data-section="explore"]').click();
      await paint();
      assert.equal(await page.evaluate(() => scrollY), before, 'Switching sections preserves the viewport');
      await page.locator('[data-panel="single-video"]').click();
      await paint();
      assert.equal(await page.evaluate(() => scrollY), before, 'Shorter Explore page preserves the viewport');
      await page.locator('[data-section="settings"]').click();
      await paint();
      assert.equal(await page.evaluate(() => scrollY), before, 'Settings preserves the viewport');
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'No horizontal overflow');
      // A user who returns to the top does not retain a tall page of empty space.
      await page.evaluate(() => scrollTo(0, 0));
      await page.locator('[data-section="workspace"]').click();
      await page.locator('[data-panel="division"]').click();
      await paint();
      assert.equal(await page.evaluate(() => scrollY), 0);
      const dimensions = await page.evaluate(() => {
        const documentHeight = document.documentElement.scrollHeight;
        document.querySelector('main').style.removeProperty('min-height');
        return { document: documentHeight, viewport: innerHeight, natural: document.documentElement.scrollHeight };
      });
      assert.ok(dimensions.document <= Math.max(dimensions.viewport, dimensions.natural) + 1,
        `Returning to the top releases spare space at ${width}px: ${JSON.stringify(dimensions)}`);
    }
    assert.deepEqual(errors, []);
    console.log('Navigation scroll checks passed at 1360, 768, 390 and 320px.');
  } finally {
    await browser?.close();
    server.kill();
    await finished;
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
