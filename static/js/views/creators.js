import { postJSON } from "../api.js";
import { uiState } from "../state.js";
import { escapeHTML, performAction, renderDetailRows } from "../ui.js";

export async function selectUP(uid, refresh) {
  await postJSON("/api/selected-up", { uid });
  await refresh();
}

export function renderUPDetail(detail) {
  const selected = detail.selected || {};
  const profile = detail.profile || {};
  const relation = detail.relation || {};
  const official = profile.official || {};
  const upStat = profile.upstat || {};
  renderDetailRows("up-detail-result", [
    ["Name", profile.name || selected.name],
    ["UID", profile.mid || selected.uid],
    ["Signature", profile.sign || "None"],
    ["Official title", official.title],
    ["Official description", official.desc],
    ["Followers", relation.follower],
    ["Following", relation.following],
    ["Released videos", detail.video_total],
    ["Total video views", upStat.archive && upStat.archive.view],
    ["Total likes", upStat.likes]
  ]);
}

export function renderSavedUPs(refresh) {
  const query = document.getElementById("up-search").value.trim().toLowerCase();
  const filtered = uiState.savedUPs.filter((up) => {
    const name = String(up.name || "").toLowerCase();
    const uid = String(up.uid || "").toLowerCase();
    return !query || name.includes(query) || uid.includes(query);
  });
  document.getElementById("ups").innerHTML = filtered.map((up) => `
    <div class="up ${uiState.selectedUP && uiState.selectedUP.uid === up.uid ? "active" : ""}">
      <strong>${escapeHTML(up.name)}</strong>
      <span class="muted">UID ${escapeHTML(up.uid)}</span>
      <button type="button" data-uid="${escapeHTML(up.uid)}">Select</button>
    </div>
  `).join("") || `<p class="muted">No saved UPs match this search.</p>`;
  document.querySelectorAll("button[data-uid]").forEach((button) => {
    button.addEventListener("click", () => performAction(button, () => selectUP(button.dataset.uid, refresh)));
  });
}
