// Runs independently of app.js so fixing a broken app module can refresh the page.
export function enableLiveReload() {
  const meta = name => document.querySelector(`meta[name="${name}"]`)?.content || '';
  const token = meta('dev-reload-token');
  if (!token) return;
  const storageKey = 'bilibili-dev-view';
  let uiRevision = meta('ui-revision'), cssRevision = meta('css-revision');
  let creatorsRevision = null;
  const eligible = 'input[id]:not([type=password]):not([type=file]):not([data-transient]), select[id]:not([data-transient])';
  const notice = text => {
    const target = document.getElementById('code-update-status');
    if (target) { target.textContent = text; target.hidden = !text; }
  };

  function saveView() {
    try {
      // Preserve the original view if a syntax error prevented app startup.
      if (!document.documentElement.dataset.dashboardReady && sessionStorage.getItem(storageKey)) return;
      const fields = {};
      document.querySelectorAll(eligible).forEach(control => {
        fields[control.id] = control.type === 'checkbox' ? control.checked : control.value;
      });
      sessionStorage.setItem(storageKey, JSON.stringify({ fields,
        panel: document.querySelector('main')?.dataset.activePanel,
        sampling: document.querySelector('[data-sampling-mode][aria-selected="true"]')?.dataset.samplingMode,
        scroll: scrollY }));
    } catch (_) { /* Source updates work even when tab storage is disabled. */ }
  }

  function restoreView() {
    try {
      const saved = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
      if (!saved) return;
      for (const [id, value] of Object.entries(saved.fields || {})) {
        const control = document.getElementById(id);
        if (!control?.matches(eligible)) continue;
        if (control.tagName === 'SELECT' && ![...control.options].some(option => option.value === value && !option.disabled)) continue;
        if (control.type === 'checkbox') control.checked = value === true;
        else control.value = value;
        control.dispatchEvent(new Event('change', { bubbles: true }));
      }
      document.querySelector(`[data-sampling-mode="${saved.sampling === 'weekly' ? 'weekly' : 'random'}"]`)?.click();
      const button = [...document.querySelectorAll('button[data-panel]')].find(item => item.dataset.panel === saved.panel);
      if (button) button.click();
      requestAnimationFrame(() => requestAnimationFrame(() => {
        if (Number.isFinite(saved.scroll) && saved.scroll > 0) {
          const main = document.querySelector('main');
          if (main) main.style.minHeight = `${Math.max(0, saved.scroll + innerHeight - (main.getBoundingClientRect().top + scrollY))}px`;
          scrollTo(0, Math.max(0, saved.scroll || 0));
        }
      }));
      sessionStorage.removeItem(storageKey);
    } catch (_) { /* Ignore obsolete controls and unavailable browser storage. */ }
  }
  document.addEventListener('dashboard-ready', restoreView, { once: true });
  if (document.documentElement.dataset.dashboardReady) restoreView();

  async function updateStyles(revision) {
    await Promise.all([...document.querySelectorAll('link[rel="stylesheet"]')].map(original => new Promise((resolve, reject) => {
      const replacement = original.cloneNode();
      const url = new URL(original.href);
      url.searchParams.set('source', revision);
      replacement.href = url.href;
      const timeout = setTimeout(() => failed(), 4000);
      const failed = () => { clearTimeout(timeout); replacement.remove(); reject(Error('Stylesheet update pending.')); };
      replacement.onload = () => { clearTimeout(timeout); original.remove(); resolve(); };
      replacement.onerror = failed;
      original.after(replacement);
    })));
    cssRevision = revision;
  }

  async function checkVersion() {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 2500);
    try {
      const response = await fetch('/api/dev-version', { cache: 'no-store', signal: controller.signal });
      if (!response.ok) return;
      const version = await response.json();
      const changed = version.token && version.token !== token || version.ui_revision && uiRevision && version.ui_revision !== uiRevision;
      const busy = document.documentElement.dataset.actionBusy === 'true' || version.busy;
      if (changed) {
        if (busy) { notice('Interface update ready · waiting for the current task to finish.'); return; }
        saveView();
        location.reload();
        return;
      }
      if (!uiRevision) uiRevision = version.ui_revision || '';
      if (version.css_revision && cssRevision && version.css_revision !== cssRevision) await updateStyles(version.css_revision);
      if (!cssRevision) cssRevision = version.css_revision || '';
      notice(!version.backend_auto_reload && version.python_revision && version.python_revision !== version.loaded_python_revision
        ? 'Backend code changed · restart main to apply it, or use start-web.command for automatic Python restarts.' : '');
      if (!busy && creatorsRevision !== null && creatorsRevision !== version.creators_revision) document.dispatchEvent(new Event('creators-source-changed'));
      if (!busy) creatorsRevision = version.creators_revision;
    } catch (_) { /* Retry while source or the Python worker is being repaired. */ }
    finally { clearTimeout(timeout); setTimeout(checkVersion, 1000); }
  }
  checkVersion();
}

enableLiveReload();
