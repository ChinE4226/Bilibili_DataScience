# Bilibili Data Science

A local Python web application for exploring Bilibili creators and videos.

## Getting Started

The existing environment was tested with Python 3.14. From the project directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Start the dashboard:

```sh
python -m bilibili_ds.web
```

Open the address printed by the server, normally
[http://127.0.0.1:8000](http://127.0.0.1:8000). If that port is busy, the server tries
the next available port. The server is intended for local, single-user use.

On macOS, double-click `start-web.command` to open the website.
The command `python web_server.py` also starts the same web application.

### Start and Stop on macOS

1. Double-click `start-web.command`. Terminal opens and starts the website.
2. Keep that Terminal window open. The server runs independently of ChatGPT.
3. To stop, click the Terminal window and press **Control+C**. This stops both
   the server and its automatic-reload watcher; no process IDs or commands are needed.

Closing that Terminal window and confirming termination also shuts down the
server and watcher. Closing only the browser tab does not stop the server.

## Project Structure

```text
bilibili_ds/          Shared Python logic, paths, and settings
    web/             HTTP routes, web workflows, and development reload
templates/           Dashboard HTML
static/
    css/             Responsive styles
    js/              Browser modules and feature views
    vendor/          Pinned local chart library and selected Lucide icons
tests/
    unit/            Calculations, validation, and serialization
    integration/     Storage, requests, launchers, HTTP, and reload
scripts/             Local development tools and sample-data preview
docs/                Architecture and maintenance guide
objects/             Saved Creator identities
.runtime/            Private account caches, QR images, and generated plots
requirements.txt     Python dependencies used by this checkout
web_server.py        Small compatibility web launcher
web_reload.py        Compatibility supervisor imports
```

See [the architecture guide](docs/architecture.md) for individual module
responsibilities, dependency direction, state ownership, and extension points.
The website imports shared Python modules directly. No frontend build step is required.

## Features

- QR sign-in, cached account selection, guest mode, and sign-out.
- Saved Creator selection and account or creator profile details.
- Temporary lookup of one video by its Bilibili URL or BV ID.
- Video selection by published-time position, date range, or metric range.
- Distribution summaries: valid/missing counts, mean, median, quartiles, P90, min/max,
  and IQR, with inline histograms, box plots, and explained outlier flags.
- Pooled and median per-video engagement ratios, duplicate-ID checks, and low-view flags.
- One reusable in-memory dataset with explicit fetching and local view-count filters.
- Per-video and aggregate ratios, including ratios involving follower counts.
- Interactive charts with crosshair details, zoom/pan, time ranges, line/bar views,
  a range slider, and zero-based, comma-separated Y-axis ticks.
- Manual PNG saving, current-view downloads, saved-plot browsing, and fetching progress.

Aggregate division uses matched rows with a known nonnegative numerator and a
positive denominator. Excluded rows are counted. Followers are repeated for each
eligible video; follower counts are fetched separately when that ratio is requested.
Single-video lookup results stay only in the current page and are replaced by
the next lookup; no cover image is displayed.

Generating a plot does not save a file. **Save PNG** saves the full data range to
Saved Plots; the download icon exports the current chart view to your browser's
download location. Unsaved data is temporary: the server retains the latest 20
plot snapshots in memory, and restarting or source-reloading clears them.
Range presets are relative to the newest selected video's publication date.
These are current metrics grouped by publication time, not historical snapshots
of a video's changing metrics. The Y-axis always begins at zero and rescales to
the visible range using round tick intervals; ratios retain decimal precision.

## Dashboard Navigation

- **Explore** groups the Creators library, creator profiles, and single-video lookup.
- **Workspace** groups Dataset, Statistics, Ratios, Charts, and Saved charts.
  Collection and local filters share one panel above the dataset tools.
- **Settings** contains account, sign-in, and request controls.

The dashboard opens on Workspace. Fetching displays dataset rows and collapses
collection controls. Switching tools keeps your controls and results; returning
to a section restores its last view. Saved charts remain available without a fetch.

## Working with a Dataset

Choose a Creator and selection, then click **Fetch / Refresh**. Listing, analysis,
division, and plotting reuse that collection in RAM. Changing the Creator, account,
or fetch selection requires another explicit fetch. The status shows the collection
interval: values are observed sequentially, not at one simultaneous instant.
A failed refresh keeps the previous dataset; summary-page failures are reported.
Individual unavailable video details remain missing rather than becoming zeros.

Local minimum/maximum view filters are inclusive and run without network requests.
They only narrow the fetched selection; clear both to include every fetched row.
In Analysis, changing the distribution metric redraws the chart locally.

Quartiles and P90 interpolate at `(n - 1) * percentile`. Outliers are values outside
`Q1 - 1.5 * IQR` and `Q3 + 1.5 * IQR`, flagged only with at least four valid values.
Duplicates remain included and are reported. Missing, invalid, and negative counts
are excluded per metric; zero remains valid. Engagement ratios exclude zero views
and missing pairs. The fewer-than-100-views flag is descriptive and does not remove rows.
Pooled engagement weights videos by views; median engagement describes the typical
per-video ratio. Neither measures unique-user conversion or current growth.

Dataset reuse and analysis create no data, image, or cache files. A successful fetch
replaces the previous dataset; stopping or source-reloading the server clears it.
The dashboard shares one dataset across local browser tabs.

## Development Reload

Automatic reload is enabled by default. Saving Python files under `bilibili_ds/`,
HTML under `templates/`, or CSS/JavaScript under `static/` restarts
the worker and refreshes open pages. Root compatibility scripts are watched too.
The watcher survives application syntax errors and retries after the next save.
Changes to the watcher itself take effect after restarting the launcher.

The browser preserves the active tab and form values. Fetched results,
in-progress requests, QR login attempts, and other in-memory state reset.
Updating `objects/creators.json` refreshes the Creator list without a server restart.
Caches, plots, and virtual environments do not trigger restarts.
This refreshes edited source files, not Bilibili data; fetch data again explicitly
to get updated counts.

Disable automatic reload or choose another port with:

```sh
python -m bilibili_ds.web --no-reload --port 8010
```

The dashboard groups related tools under Explore, Workspace, and Settings.
Every page uses the same centered workspace. The current creator button opens a
searchable dropdown for quick switching. Select a creator to close it, or dismiss
it with Escape or a click outside. Add / manage creators opens the Creators tab
under Explore. The dropdown is hidden on Creators, Settings, Single Video, and Saved Charts.

Click unused page space or the Back button to return to the previously visited
menu view. While the dropdown is open, an outside click only closes it. Controls,
results, charts, and selected text do not trigger blank-space navigation. Navigation
history is kept in memory and resets on reload; existing form values and results
stay available when switching views. Wide tables scroll within their own areas; charts resize to the viewport.

## Tests and Preview

Run the offline regression suite:

```sh
.venv/bin/python -m unittest discover -s tests -t . -v
```

Tests use temporary files and mocked Bilibili responses. HTTP and reload tests
open temporary localhost ports. They do not sign in or contact Bilibili.

With Playwright and Chrome installed, run `node tests/browser/plots.cjs` for
offline chart interaction, manual-save, PNG-download, and responsive-layout checks.
Run the analysis browser checks with `node tests/browser/analysis.cjs`. They verify
local chart changes, filter payloads, and desktop/mobile layout using sample data.

Set `PLAYWRIGHT_MODULE` to a Playwright package path when it is not in Node's
normal lookup path. Screenshots are written to a temporary directory.

Preview the dashboard using sample data only:

```sh
.venv/bin/python scripts/preview_dashboard.py
```

The preview defaults to [http://127.0.0.1:8012](http://127.0.0.1:8012);
`--port` selects a different port. Account-changing actions are disabled.

## Saved Data

Application data uses these locations and formats:

- `objects/creators.json`: permanent Creator identities only.
- `.runtime/accounts/`: cached account credentials.
- `.runtime/active_account.json`: active account selection.
- `.runtime/bilibili_credential.json`: legacy credential cache.
- `.runtime/bilibili_cookie.txt`: optional local cookie input.
- `.runtime/bilibili_qrcode.png`: current sign-in QR image.
- `.runtime/plots/`: explicitly saved PNG plots.

A Creator file has this format:

```json
{
  "creators": [
    {
      "name": "Example",
      "space": "https://space.bilibili.com/123456",
      "uid": "123456"
    }
  ]
}
```

`selected_uid` is kept in memory, not saved in this file. Credentials, cookies,
QR images, and fetched profile details do not belong in the Creator list.
Generated runtime files are ignored by Git. Do not commit credentials.

## Useful Endpoints

- `/`: dashboard.
- `/static/`: public CSS and JavaScript only.
- `/api/health`: selected Creator, account summary, and request rate.
- `/api/creators`: saved Creator list.
- `/api/progress`: current operation progress.
- `/api/plots`: saved PNG plot list.
- `POST /api/video-lookup`: temporary video lookup using a `video` URL or BV ID.
- `POST /api/video-action`: listing, analysis, division, or plotting.
- `POST /api/plots/save`: explicitly save a generated plot using its `plot_id`.
- `/plots/<file>.png`: generated plot images.

## API Source and License

Bilibili access uses [bilibili-api-python](https://github.com/Nemo2011/bilibili-api).
Interactive plots use locally bundled [Apache ECharts 5.6.0](https://echarts.apache.org/handbook/en/concepts/axis/).
Selected Lucide 1.8.0 icons are bundled locally. Upstream licenses and notices
are in `docs/licenses/`; there is no runtime CDN dependency.

GPL-3.0 license. See [LICENSE](LICENSE).

Copyright (c) 2026 ChinE4226

All rights reserved.
