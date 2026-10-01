import { postJSON } from "../api.js";
import { uiState } from "../state.js";
import { escapeHTML, performAction, renderDetailRows } from "../ui.js";

export function updateSelectedCreator(selected) {
  uiState.selectedCreator = selected;
  const label = document.getElementById("selected");
  label.textContent = selected ? `${selected.name} (UID ${selected.uid})` : "No Creator selected.";
  label.title = label.textContent;
  const libraryButton = document.getElementById("open-library");
  libraryButton.textContent = selected ? `Creator: ${selected.name}` : "Choose creator";
  libraryButton.title = `${label.textContent} — choose creator`;
  renderCreatorOptions();
  document.querySelectorAll("button[data-uid]").forEach((button) => {
    const active = button.dataset.uid === selected?.uid;
    button.closest(".creator").classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

export async function selectCreator(uid) {
  const result = await postJSON("/api/selected-creator", { uid });
  updateSelectedCreator(result.selected_creator);
}

export function renderCreatorDetail(detail) {
  const selected = detail.selected || {};
  const profile = detail.profile || {};
  const relation = detail.relation || {};
  const official = profile.official || {};
  const creatorStat = profile.upstat || {};
  renderDetailRows("creator-detail-result", [
    ["Name", profile.name || selected.name],
    ["UID", profile.mid || selected.uid],
    ["Signature", profile.sign || "None"],
    ["Official title", official.title],
    ["Official description", official.desc],
    ["Followers", relation.follower],
    ["Following", relation.following],
    ["Released videos", detail.video_total],
    ["Total video views", creatorStat.archive && creatorStat.archive.view],
    ["Total likes", creatorStat.likes]
  ]);
}

export function renderSavedCreators() {
  const query = document.getElementById("creator-library-search").value.trim().toLowerCase();
  const filtered = uiState.savedCreators.filter((creator) => {
    const name = String(creator.name || "").toLowerCase();
    const uid = String(creator.uid || "").toLowerCase();
    return !query || name.includes(query) || uid.includes(query);
  });
  document.getElementById("creators").innerHTML = filtered.map((creator) => `
    <div class="creator ${uiState.selectedCreator && uiState.selectedCreator.uid === creator.uid ? "active" : ""}">
      <strong>${escapeHTML(creator.name)}</strong>
      <span class="muted">UID ${escapeHTML(creator.uid)}</span>
      <button type="button" data-uid="${escapeHTML(creator.uid)}">Select</button>
    </div>
  `).join("") || `<p class="muted">No saved Creators match this search.</p>`;
  document.querySelectorAll("button[data-uid]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.uid === uiState.selectedCreator?.uid) return;
      return performAction(button, () => selectCreator(button.dataset.uid), { showProgress: false, disableAll: false });
    });
  });
  updateSelectedCreator(uiState.selectedCreator);
}


export function closeCreatorMenu({ restoreFocus = false } = {}) {
  document.getElementById("creator-menu").hidden = true;
  document.getElementById("open-library").setAttribute("aria-expanded", "false");
  if (restoreFocus) document.getElementById("open-library").focus({ preventScroll: true });
}

export function renderCreatorOptions() {
  const query = document.getElementById("creator-search").value.trim().toLowerCase();
  const options = uiState.savedCreators.filter(creator => `${creator.name || ""} ${creator.uid}`.toLowerCase().includes(query));
  document.getElementById("creator-options").innerHTML = options.map(creator => `
    <button type="button" class="creator-option" data-quick-uid="${escapeHTML(creator.uid)}" aria-pressed="${creator.uid === uiState.selectedCreator?.uid}">
      <strong>${escapeHTML(creator.name)}</strong><span>UID ${escapeHTML(creator.uid)}${creator.uid === uiState.selectedCreator?.uid ? " · Selected" : ""}</span>
    </button>`).join("") || '<p class="muted">No matching creators.</p>';
  document.querySelectorAll("[data-quick-uid]").forEach(button => {
    button.addEventListener("click", () => performAction(button, async () => {
      if (button.dataset.quickUid !== uiState.selectedCreator?.uid) await selectCreator(button.dataset.quickUid);
      closeCreatorMenu({ restoreFocus: true });
      renderCreatorOptions();
    }, { showProgress: false, disableAll: false }));
  });
}
