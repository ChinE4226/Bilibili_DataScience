import { metricFields } from "../constants.js";
import { postJSON } from "../api.js";
import { escapeHTML, formatValue, table } from "../ui.js";
import { startProgressPolling, stopProgressPolling } from "../progress.js";

export function renderSingleVideo(video) {
  const result = document.getElementById("single-video-result");
  const dimensions = video.width && video.height ? `${video.width} x ${video.height}` : "Unknown";
  const videoLink = video.url
    ? `<a href="${escapeHTML(video.url)}" target="_blank" rel="noreferrer">Open on Bilibili</a>`
    : "";
  const detailList = (rows, className) => `<dl class="${className}">${rows.map(([label, value]) =>
    `<div><dt>${escapeHTML(label)}</dt><dd>${escapeHTML(formatValue(value))}</dd></div>`
  ).join("")}</dl>`;
  const stats = detailList(metricFields.map(([key, label]) => [label, video[key]]), "single-video-stats");
  const details = detailList([
      ["Uploader UID", video.owner_mid],
      ["Published", video.published_time],
      ["Duration", video.duration],
      ["Category", video.category],
      ["BVID", video.bvid],
      ["AID", video.aid],
      ["Pages", video.page_count],
      ["Dimensions", dimensions]
    ], "single-video-metadata");
  const description = video.description
    ? `<div class="single-video-group"><h3>Description</h3><div class="single-video-description">${escapeHTML(video.description)}</div></div>`
    : "";
  result.innerHTML = `<article class="single-video-result">
    <div class="single-video-heading"><div><h3>${escapeHTML(formatValue(video.title))}</h3>
      <p class="muted">${escapeHTML(formatValue(video.owner_name))}</p></div>${videoLink}</div>
    <div class="single-video-group"><h3>Statistics</h3>${stats}</div>
    <div class="single-video-group"><h3>Video Details</h3>${details}</div>
    ${description}
  </article>`;
}

export function renderVideos(target, videos) {
  document.getElementById(target).innerHTML = table(
    ["Title", "Published", "Views", "Likes", "Replies", "Favorites", "Coins", "Shares", "BVID"],
    videos.map((item) => [item.title, item.published_time, item.views, item.likes, item.replies, item.favorites, item.coins, item.shares, item.bvid])
  );
}

export async function lookupSingleVideo() {
  const input = document.getElementById("single-video-input");
  const result = document.getElementById("single-video-result");
  startProgressPolling("Fetching video", "single-video-progress");
  result.innerHTML = "";
  try {
    const data = await postJSON("/api/video-lookup", { video: input.value });
    renderSingleVideo(data.video);
  } catch (error) {
    result.innerHTML = `<p class="error-message">${escapeHTML(error.message)}</p>`;
  } finally {
    await stopProgressPolling();
  }
}
