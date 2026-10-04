// Navigate the grouped workspace through the same controls as a user.
const groups = { videos: 'data', sampling: 'data', analysis: 'analysis', plot: 'analysis', division: 'analysis', anomalies: 'analysis', 'saved-plots': 'analysis', tasks: 'tasks', nodes: 'nodes' };
module.exports = async function openPanel(page, name) {
  const group = groups[name];
  if (group) {
    if (!(await page.locator(`[data-group="${group}"]`).isVisible())) await page.locator('[data-section="workspace"]').click();
    const button = page.locator(`[data-panel="${name}"]`);
    if (!(await button.isVisible())) await page.locator(`[data-group="${group}"]`).click();
    if (await button.isVisible()) await button.click();
  } else await page.locator(`[data-panel="${name}"]`).click();
};
