// Keep the native values for API payloads while rendering project-styled menus.
const controls = [];

export function closeSelectMenus(outsideTarget) {
  let closed = false;
  for (const control of controls) {
    if (!control.menu.hidden && (!outsideTarget || !control.wrapper.contains(outsideTarget) && !control.menu.contains(outsideTarget))) {
      control.menu.hidden = true;
      control.trigger.setAttribute('aria-expanded', 'false');
      control.trigger.removeAttribute('aria-activedescendant');
      closed = true;
    }
  }
  return closed;
}

export function setupSelects() {
  document.querySelectorAll('select').forEach(select => {
    const wrapper = document.createElement('span');
    wrapper.className = 'project-select';
    wrapper.dataset.select = select.id;
    const label = select.closest('label');
    const name = select.getAttribute('aria-label') || [...(label?.childNodes || [])]
      .filter(node => node.nodeType === Node.TEXT_NODE).map(node => node.textContent.trim()).join(' ');
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.id = `${select.id}-trigger`;
    trigger.className = 'select-trigger';
    trigger.setAttribute('role', 'combobox');
    trigger.setAttribute('aria-label', name);
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');
    const menu = document.createElement('div');
    menu.id = `${select.id}-options`;
    menu.className = 'select-menu';
    menu.setAttribute('role', 'listbox');
    menu.setAttribute('aria-label', name);
    menu.hidden = true;
    trigger.setAttribute('aria-controls', menu.id);
    select.before(wrapper);
    wrapper.append(select, trigger);
    document.body.append(menu);
    select.hidden = true;
    if (label) label.htmlFor = trigger.id;
    let items = [];
    const rebuild = () => {
      menu.replaceChildren();
      items = [...select.options].map((option, index) => {
        const item = document.createElement('div');
        item.id = `${select.id}-option-${index}`;
        item.className = 'select-option';
        item.setAttribute('role', 'option');
        item.textContent = option.textContent;
        item.setAttribute('aria-disabled', String(option.disabled));
        menu.append(item);
        item.addEventListener('mousedown', event => event.preventDefault());
        item.addEventListener('click', () => choose(index));
        return item;
      });
    };
    rebuild();
    const control = { wrapper, trigger, menu, anchorTop: 0, anchorLeft: 0 };
    let active = select.selectedIndex;
    const sync = () => {
      trigger.textContent = select.selectedOptions[0]?.textContent || 'Select';
      trigger.disabled = select.disabled;
      items.forEach((item, index) => item.setAttribute('aria-selected', String(index === select.selectedIndex)));
    };
    const highlight = index => {
      active = index;
      items.forEach((item, i) => item.classList.toggle('highlighted', i === index));
      trigger.setAttribute('aria-activedescendant', items[index]?.id || '');
      items[index]?.scrollIntoView({ block: 'nearest' });
    };
    const open = () => {
      closeSelectMenus();
      const rect = trigger.getBoundingClientRect();
      control.anchorTop = rect.top;
      control.anchorLeft = rect.left;
      const width = Math.min(Math.max(rect.width, 160), innerWidth - 24);
      menu.style.width = `${width}px`;
      menu.style.left = `${Math.max(12, Math.min(rect.left, innerWidth - width - 12))}px`;
      const below = innerHeight - rect.bottom - 16;
      const above = rect.top - 16;
      const upwards = below < 180 && above > below;
      menu.style.maxHeight = `${Math.min(280, Math.max(40, upwards ? above : below))}px`;
      menu.style.top = upwards ? 'auto' : `${rect.bottom + 6}px`;
      menu.style.bottom = upwards ? `${innerHeight - rect.top + 6}px` : 'auto';
      menu.hidden = false;
      trigger.setAttribute('aria-expanded', 'true');
      highlight(select.selectedIndex);
    };
    const choose = index => {
      if (trigger.disabled || select.options[index]?.disabled) return;
      select.selectedIndex = index;
      closeSelectMenus();
      select.dispatchEvent(new Event('change', { bubbles: true }));
      trigger.focus({ preventScroll: true });
    };
    trigger.addEventListener('click', () => menu.hidden ? open() : closeSelectMenus());
    let search = '', lastTyped = 0;
    trigger.addEventListener('keydown', event => {
      if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
        event.preventDefault();
        if (menu.hidden) { open(); return; }
        const enabled = [...select.options].map((option, i) => option.disabled ? -1 : i).filter(i => i >= 0);
        const position = enabled.indexOf(active);
        highlight(event.key === 'Home' ? enabled[0] : event.key === 'End' ? enabled.at(-1)
          : enabled[Math.max(0, Math.min(enabled.length - 1, position + (event.key === 'ArrowDown' ? 1 : -1)))]);
      } else if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        if (menu.hidden) open(); else choose(active);
      } else if (event.key === 'Escape') {
        event.preventDefault(); closeSelectMenus();
      } else if (event.key === 'Tab') closeSelectMenus();
      else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
        event.preventDefault();
        if (menu.hidden) open();
        search = Date.now() - lastTyped > 700 ? event.key : search + event.key;
        lastTyped = Date.now();
        const index = [...select.options].findIndex(option => !option.disabled && option.textContent.toLowerCase().startsWith(search.toLowerCase()));
        if (index >= 0) highlight(index);
      }
    });
    select.addEventListener('change', sync);
    const optionsChanged = () => { rebuild(); active = select.selectedIndex; sync(); };
    select.addEventListener('optionschange', optionsChanged);
    new MutationObserver(optionsChanged).observe(select, { attributes: true, attributeFilter: ['disabled'], childList: true, subtree: true });
    controls.push(control);
    sync();
  });
  window.addEventListener('resize', () => closeSelectMenus());
  document.addEventListener('scroll', event => {
    if (event.target instanceof Element && event.target.closest('.select-menu')) return;
    // A queued scroll from focusing the trigger can arrive after it opens.
    // Dismiss only when the anchor has actually moved since opening.
    if (controls.some(control => {
      if (control.menu.hidden) return false;
      const rect = control.trigger.getBoundingClientRect();
      return Math.abs(rect.top - control.anchorTop) > 1 || Math.abs(rect.left - control.anchorLeft) > 1;
    })) closeSelectMenus();
  }, true);
}
