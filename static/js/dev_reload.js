export function enableLiveReload(refresh) {
  const token = document.querySelector('meta[name="dev-reload-token"]')?.content || "";
  if (!token) return;
  const storageKey = "bilibili-dev-view";
  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey) || "null");
    sessionStorage.removeItem(storageKey);
    if (saved) {
      for (const [id, value] of Object.entries(saved.fields || {})) {
        const control = document.getElementById(id);
        if (control && control.matches("input:not([type=password]):not([type=file]), select")) {
          control.value = value;
          control.dispatchEvent(new Event("change"));
        }
      }
      const button = [...document.querySelectorAll("button[data-panel]")]
        .find((item) => item.dataset.panel === saved.panel);
      if (button) button.click();
    }
  } catch (_) { /* Reload also works when browser storage is unavailable. */ }
  let upsRevision = null;
  async function checkVersion() {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 2500);
    try {
      const response = await fetch("/api/dev-version", { cache: "no-store", signal: controller.signal });
      if (!response.ok) return;
      const version = await response.json();
      if (version.token && version.token !== token) {
        try {
          const fields = {};
          document.querySelectorAll("input[id]:not([type=password]):not([type=file]), select[id]")
            .forEach((control) => { fields[control.id] = control.value; });
          const panel = document.querySelector('button[data-panel][aria-current="page"]')?.dataset.panel;
          sessionStorage.setItem(storageKey, JSON.stringify({ fields, panel }));
        } catch (_) { /* Keep reloading even if session storage is disabled. */ }
        location.reload();
        return;
      }
      if (upsRevision !== null && upsRevision !== version.ups_revision) await refresh();
      upsRevision = version.ups_revision;
    } catch (_) { /* Retry while the worker is restarting or awaiting a source fix. */ }
    finally {
      clearTimeout(timeout);
      setTimeout(checkVersion, 1000);
    }
  }
  checkVersion();
}
