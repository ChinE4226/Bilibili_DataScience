import { table, preservePageHeight } from './ui.js';

// Keep the collected rows intact; only format the current page for the DOM.
export function renderPaginatedTable(target, headers, items, row, { lazy = false, label = 'Videos' } = {}) {
  const element = typeof target === 'string' ? document.getElementById(target) : target;
  const pageSize = 50;
  let page = 0;
  const pages = Math.max(1, Math.ceil(items.length / pageSize));
  const render = () => {
    const start = page * pageSize;
    element.innerHTML = `<div class="analysis-table">${table(headers, items.slice(start, start + pageSize).map(row))}</div>`;
    if (pages === 1) return;
    const controls = document.createElement('nav');
    controls.className = 'table-pagination';
    controls.setAttribute('aria-label', `${label} pages`);
    const status = document.createElement('span');
    status.setAttribute('role', 'status');
    status.textContent = `${start + 1}–${Math.min(start + pageSize, items.length)} of ${items.length.toLocaleString()} · Page ${page + 1} of ${pages}`;
    controls.append(status);
    for (const [text, step] of [['Previous', -1], ['Next', 1]]) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = text;
      button.disabled = step < 0 ? page === 0 : page === pages - 1;
      button.addEventListener('click', () => {
        preservePageHeight();
        page += step;
        render();
        // Page replacement must preserve keyboard navigation, including at boundaries.
        const buttons = [...element.querySelectorAll('.table-pagination button')];
        (buttons.find(item => item.textContent === text && !item.disabled) || buttons.find(item => !item.disabled))?.focus({ preventScroll: true });
      });
      controls.append(button);
    }
    element.append(controls);
  };
  const details = lazy ? element.closest('details') : null;
  if (details && !details.open) {
    element.replaceChildren();
    const onToggle = () => {
      if (!details.open) return;
      details.removeEventListener('toggle', onToggle);
      render();
    };
    details.addEventListener('toggle', onToggle);
  } else render();
}
