"""Local-only layout preview with sample data; never calls Bilibili or writes accounts."""

import argparse
import io
from datetime import datetime, timedelta
from pathlib import Path
import sys
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bilibili_ds.distributions import analyse_dataset
from bilibili_ds.weekly import summarize_weekly_items
from bilibili_ds.sampling import parse_sample_options, sample_candidates
from bilibili_ds.plotting import plt
from bilibili_ds.web.assets import dashboard_html
from bilibili_ds.web.http import read_json_body
from bilibili_ds.web.routes import BilibiliDataScienceHandler
from bilibili_ds.web.serializers import VIDEO_FIELDS, extract_bvid, serialize_video
from bilibili_ds.web.server import DashboardHTTPServer
from bilibili_ds.web.weekly import parse_weekly_source


VIDEO = {
    "title": "A longer sample video title: comparing camera details and everyday recording quality",
    "owner_name": "Sample uploader", "owner_mid": 123456, "published_time": "2026-09-18 12:30:00",
    "duration": "12:45", "category": "Technology", "bvid": "BV1xx411c7mD", "aid": 170001,
    "page_count": 1, "width": 1920, "height": 1080, "views": 1200034,
    "likes": 24001, "replies": 864, "favorites": 9375, "coins": 3072, "shares": 0,
    "url": "https://www.bilibili.com/video/BV1xx411c7mD",
    "description": "Sample description for layout verification.\n" + "LongUnbrokenText" * 15,
}
VIDEOS = [dict(VIDEO, title=f"{index + 1}. {VIDEO['title']}") for index in range(24)]
CREATOR = {"name": "Sample uploader", "uid": "123456"}
POINTS = [{"title": f"Video {i + 1}: sample metric history", "label": (datetime(2026, 3, 1) + timedelta(days=i * 3)).strftime("%Y-%m-%d %H:%M:%S"),
           "value": 18000 + ((i * 7919) % 43000) + i * 300} for i in range(64)]
figure, axis = plt.subplots(figsize=(13, 7))
axis.plot([point["label"] for point in POINTS], [point["value"] for point in POINTS])
axis.set_xlabel("Published time")
axis.set_ylabel("Views")
figure.tight_layout()
buffer = io.BytesIO()
figure.savefig(buffer, format="png")
plt.close(figure)
PNG = buffer.getvalue()


class PreviewHandler(BilibiliDataScienceHandler):
    saved = False

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self.send_bytes(dashboard_html(), "text/html; charset=utf-8")
            return
        if path.startswith("/static/") or path == "/favicon.ico":
            super().do_GET()
            return
        if path == "/plots/sample.png":
            self.send_bytes(PNG, "image/png")
            return
        fixtures = {
            "/api/health": {"account": "Layout preview (sample data)", "selected_creator": CREATOR, "request_frequency": 4},
            "/api/creators": {"creators": [CREATOR, {"name": "Another uploader with a longer name", "uid": "987654"}]},
            "/api/accounts": {"accounts": [{"name": "Sample account", "uid": "555555", "id": "sample", "source": "qr", "active": True}]},
            "/api/plots": {"plots": [{"url": "/plots/sample.png", "name": "Sample_views_by_published_time.png", "size": len(PNG)}] if self.saved else []},
            "/api/progress": {"message": "Completed.", "running": False, "count": 24},
            "/api/account-detail": {"name": "Sample account", "mid": 555555, "level": 5, "coins": 34, "following": 120, "follower": 17, "sign": "Sample account signature"},
            "/api/creator-detail": {"selected": CREATOR, "profile": {"name": CREATOR["name"], "mid": 123456, "sign": "Long profile text " * 15, "upstat": {"archive": {"view": 123456789}, "likes": 654321}}, "relation": {"follower": 100000, "following": 45}, "video_total": 500},
        }
        if path in fixtures:
            self.send_json(fixtures[path])
        else:
            self.send_error_json(404, "Preview endpoint not available.")

    def do_POST(self):
        path = urlparse(self.path).path
        data = read_json_body(self)
        if path == "/api/video-lookup":
            try:
                extract_bvid(data.get("video"))
            except ValueError as exc:
                self.send_error_json(400, str(exc))
                return
            self.send_json({"video": VIDEO})
        elif path == "/api/random-sample":
            try:
                options = parse_sample_options(data)
                raw = [{"title": f"Sample video {i + 1}", "bvid": f"random-{i}", "pubdate": int(datetime(2026, 9, 1).timestamp()) + i * 3600,
                        "owner": {"mid": i % 4, "name": f"Creator {i % 4 + 1}"},
                        "stat": {field["stat_key"]: (i + 1) * 100 if field["field"] == "views" else i * 2 for field in VIDEO_FIELDS}}
                       for i in range(options["pool_size"])]
                sampled, summary = sample_candidates(raw, options)
            except ValueError as exc:
                self.send_error_json(400, str(exc))
                return
            summary["sampling"].update({"checked": len(raw), "pages": (len(raw) + 19) // 20})
            self.send_json({**summary, "started_at": "2026-10-03T00:00:00Z", "collected_at": "2026-10-03T00:00:01Z",
                "videos": [{**serialize_video(row), "creator": row["owner"]["name"]} for row in sampled]})
        elif path == "/api/weekly-analysis":
            try:
                issue = parse_weekly_source(data.get("source"))
            except ValueError as exc:
                self.send_error_json(400, str(exc))
                return
            raw = [{"title": f"Weekly video {i + 1}", "bvid": f"weekly-{i}", "pubdate": int(datetime(2026, 9, 1).timestamp()) + i * 86400,
                    "owner": {"mid": i % 4, "name": f"Creator {i % 4 + 1}"},
                    "stat": {field["stat_key"]: (i + 1) * 100 if field["field"] == "views" else i * 2 for field in VIDEO_FIELDS}}
                   for i in range(24)]
            _, summary = summarize_weekly_items(raw)
            self.send_json({**summary, "issue": {"number": issue, "name": f"Weekly issue {issue}", "subject": "Sample popular videos",
                "url": f"https://www.bilibili.com/v/popular/weekly?num={issue}"},
                "started_at": "2026-10-03T00:00:00Z", "collected_at": "2026-10-03T00:00:01Z",
                "videos": [{**serialize_video(row), "creator": row["owner"]["name"]} for row in raw]})
        elif path == "/api/video-action":
            self.send_json({
                "videos": VIDEOS, "points": POINTS, "y_label": "Views", "plot_id": "sample", "selected_creator": CREATOR, "selection": "All videos",
                "mode": data.get("mode"), "numerator_total": 24001, "denominator_total": 1200034, "ratio": 0.02,
                "rows": [{"title": item["title"], "published_time": item["published_time"], "numerator": 24001, "denominator": 1200034, "ratio": 0.02} for item in VIDEOS],
                **analyse_dataset([{"title": item["title"], "bvid": f"sample-{i}",
                    "stat": {field["stat_key"]: (i + 1) * 100 if field["field"] == "views" else i * 2 for field in VIDEO_FIELDS}}
                    for i, item in enumerate(VIDEOS)]),
                "dataset": {"count": 24, "selection": "Sample selection", "started_at": "2026-09-30T00:00:00Z", "collected_at": "2026-09-30T00:00:10Z", "reused": not data.get("refresh")},
            })
        elif path == "/api/plots/save" and data.get("plot_id") == "sample":
            type(self).saved = True
            self.send_json({"name": "sample.png", "url": "/plots/sample.png"})
        else:
            self.send_error_json(400, "Sample error: this action is disabled in the layout preview.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8012)
    args = parser.parse_args()
    server = DashboardHTTPServer(("127.0.0.1", args.port), PreviewHandler)
    print(f"Sample layout preview: http://127.0.0.1:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
