import { renderDetailRows } from "../ui.js";

export function renderAccountDetail(detail) {
  renderDetailRows("account-result", [
    ["Name", detail.name || detail.uname],
    ["UID", detail.mid || detail.uid],
    ["Level", detail.level],
    ["Coins", detail.coins],
    ["Following", detail.following],
    ["Followers", detail.follower],
    ["VIP type", detail.vip && detail.vip.type],
    ["VIP status", detail.vip && detail.vip.status],
    ["Signature", detail.sign]
  ]);
}
