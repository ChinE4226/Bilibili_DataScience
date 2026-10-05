# Bilibili Data Science

A local Python web application for exploring Bilibili creators and videos.

## Getting Started

Python 3.10 or newer is required; the existing environment was tested with Python
3.14. On macOS, double-click `setup-main.command` once to install the main app's
dependencies, then double-click `start-main.command`. If this checkout already
has a working Python environment, skip setup.

For a terminal-based setup, run these commands from the project directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --no-cache-dir -r requirements.txt
```

Start the dashboard:

```sh
python -B -m bilibili_ds.web --no-reload
```

Open the address printed by the server, normally
[http://127.0.0.1:8000](http://127.0.0.1:8000). If that port is busy, the server tries
the next available port. The server is intended for local, single-user use.

The command `python web_server.py` also starts the same web application, with
development reload enabled.

### Start and Stop on macOS

1. Double-click `start-main.command`. Terminal opens and the dashboard opens in
   Google Chrome. Interface edits update automatically; Python restarts are disabled
   so editing a project file does not reset node work.
2. Keep that Terminal window open. The server runs independently of ChatGPT.
3. To stop, click the Terminal window and press **Control+C**.

Closing that Terminal window and confirming termination also shuts down the
server. Closing only the browser tab does not stop the server.

On a fetching Mac, use `setup-node.command` once and `start-node.command` to open
the node's local web GUI in Google Chrome. Setup installs into a local Python
environment and disables the pip download cache. No ZIP or distribution package
is needed.

New setup environments live in `~/Library/Application Support/BilibiliDataScience/.venv`
on each Mac. Main and development launchers select the same interpreter and runtime.
Account files default to that local application support folder. If it has no cached
sign-in but the main checkout's `.runtime` does, both main launchers reuse that
existing cache without copying credentials. The node always defaults to its local
runtime. `BILIBILI_RUNTIME_DIR` explicitly overrides either choice.
An existing working project environment remains usable;
leave legacy `.venv`, `venv` and `.runtime` folders out of a source-only sync.

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
setup-main.command   One-time macOS main-app environment setup
setup-node.command   One-time macOS fetching-node environment setup
start-main.command   macOS dashboard with live interface updates and stable Python
start-node.command   macOS fetching-node GUI launcher
start-web.command    macOS development launcher with source reload
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
  a range slider, publication-time or equally spaced video-number axes, and zero-based Y-axis ticks.
- Optional MA5/10/20, EMA10/20, and rolling median5/10 overlays with hover values and PNG exports.
- Relative20 compares each video with its previous 20-video mean in a separate panel with linked zoom.
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
Moving averages use full trailing windows of 5, 10, or 20 valid plotted videos,
ordered oldest to newest; these windows count videos, not days. The first N−1
points have no MA value. Overlays use the loaded selection in memory, keep their
values during zooming, and appear in both PNG save and download output.
EMA uses weight `2 / (N + 1)` and starts from the first N-video average. Rolling
medians use the middle value (or middle pair for even windows). Relative20 excludes
the current video from its baseline, needs 21 videos for its first value, and leaves
a gap when the baseline is zero. All indicators count valid plotted videos, not days.
Both chart panels appear in explicit PNG exports; no indicator computation writes files.
Range presets are relative to the newest selected video's publication date.
These are current metrics grouped by publication time, not historical snapshots
of a video's changing metrics. Raw and log-value Y-axes begin at zero; performance-index axes also include negative values when needed. The chart rescales to
the visible range using round tick intervals; ratios retain decimal precision.

Charts offer **Raw values**, **Log scale** (`log10(value + 1)`), and **Performance index**.
The index uses `100 + 25 × log2((value + 1) / (dataset median + 1))`; 100 is typical
within the selected cohort and approximately +25 represents doubling. The baseline
uses all valid chart values, stays fixed during zooming, and changes with a new
selection or metric. Index values are never clipped. Zero is valid; small cohorts
may have unstable baselines. Index trend lines use index values; log-view trend
lines are computed on raw values and then transformed. Relative20 always uses raw values.

**Mark unusual values** highlights potential outliers with amber diamonds.
In chronological order, each log-transformed value is compared with the preceding
20 plotted videos, excluding itself. The modified z-score is
`0.6745 × (ln(value + 1) − prior median) / prior MAD`; absolute scores above 3.5
are flagged. The first 20 observations, zero-MAD windows and undated sequences
have no score. **Analysis → Unusual values** lists flags for the most recently
generated chart, including raw values, indices and scores. It does not change
filters, delete rows or fetch data. Flags do not establish manipulation, and
cumulative metrics remain affected by video age. See the
[NIST method reference](https://www.itl.nist.gov/div898/handbook/eda/section3/eda35h.htm).
Trend controls are collapsed under **Trend indicators**. PNG saves preserve value
mode, markers and line/bar style; downloads capture the current view in memory.
After updating an already running dashboard, reload the browser for these controls.
Restart main to enable the updated Save PNG renderer; a restart clears RAM data and
pairing, while browser refresh preserves them. Download current view works without a restart.

## Dashboard Navigation

- **Explore** groups the Creators library, creator profiles, and single-video lookup.
- **Workspace** has four destinations: Data, Analysis, Tasks, and Nodes.
  Data contains Creator dataset and Sampling (Random sample / Weekly popular).
  Analysis contains Overview, Charts, Ratios & engagement, Unusual values, and Saved charts.
  Collection and local filters appear only on Creator dataset; analysis shows a compact dataset summary.
- **Settings** contains account, sign-in, and request controls.

The dashboard opens on Workspace. Fetching updates dataset rows and collapses
collection controls without changing the active page. Switching tools keeps your controls and results; returning
to a section restores its last view. Saved charts remain available without a fetch.
Collection and filter controls appear only on Dataset; Statistics, Ratios, and Charts
reuse its selection and filters. The creator selector shares the Back button row.

Random samples and weekly reports now have **Use in Analysis**. This opens Overview
on the exact collected rows; Charts, Ratios, Unusual values and processing-only
batch tasks use the same collection without fetching again. The **Analysis collection**
menu switches between the creator dataset and retained sampling collections.
Switching clears the previous source's analysis results. Your creator dataset stays
available, with its own local filters. Sampling collections have separate inclusive
view filters in the Analysis summary; run a tool to apply them.

The summary names the source and collection interval, and separates requested,
checked, valid/sampled and active row counts. For example, **100 requested →
102 checked → 100 valid → 86 after local filters**. Random samples also show the
eligible pool before the draw. Collection scope retains the issue or keyword,
search order, bounds and seed. Follower-based ratios require a creator dataset;
mixed-creator collections support the six video metrics.

The latest four sampling collections (at most 2,500 rows each) stay in server RAM.
Expired collections require an explicit recollection on Sampling; they never
silently refetch. No collection or report files are written. Browser refresh or
reopening a tab restores the latest weekly and random reports from these retained
collections; restarting main clears them.

## Running Several Tasks

Open **Workspace → Tasks**, choose Fetch / Refresh, Ratios, Statistics, and/or
Charts, then click **Run selected tasks**. Selected steps run in that order.
Configure the range and filters on Dataset, the ratio on Ratios, and the chart
on Charts; the Tasks page shows those settings and links to each page.

Fetch runs once, then processing steps reuse the collected dataset. Uncheck Fetch
to process an already loaded dataset. Settings are captured when the batch starts,
and editing controls stay disabled during execution. Navigation remains available,
and completion does not change the current page. Results appear on the usual pages.

Each task shows its progress and completion. A failed task stops the batch and
marks later tasks as skipped, preserving completed results. **Stop after current
task** lets the active operation finish, then skips the remaining steps.
Keep the browser tab open until completion. The queue and results stay in memory;
running a batch does not save charts or create dataset files.

## Random Video Samples

Open **Workspace → Data → Sampling → Random sample**. Enter a search keyword, choose
the candidate order, and set the sample size and candidate limit (up to 500).
Optional filters include a Bilibili category ID, publication dates in Beijing time,
and an inclusive range for any of the six metrics. Metric boundaries support
`k` and `m`, such as `10k`. Publication end dates include the whole day.

**Collect random sample** checks details across the bounded search pool, skips
duplicate IDs and incomplete metrics, applies filters, then draws uniformly
without replacement from all eligible candidates. Invalid entries do not count
toward the requested sample size. If the pool has too few eligible videos, the
report shows the actual count and shortfall; increase the candidate limit or
broaden the filters to collect more.

The report includes the pool scope, seed, collection interval, exclusions,
individual sampled videos, and the same performance and engagement averages
as Weekly popular. Reusing a seed repeats the draw only if the eligible pool
and its order are unchanged. Search results and their ranking define this pool;
it is not a uniform sample of all Bilibili. These are current accumulated metrics.
Requests use the configured pacing and stop if the server rejects collection.
The creator dataset is kept separately. Sample rows and report summaries stay in
server RAM and return after a browser refresh; no dataset or report files are written.

## Fetching Nodes on Other Macs

Pair a Mac once under **Workspace → Nodes**. Then return to **Dataset** and use
the usual **Fetch / Refresh** button. **Fetch on → Automatic** uses an idle
compatible node when ready, or this Mac when nodes are absent, busy, paused,
offline or incompatible. The choice is made again on each refresh. Choose
**Connected node only** to require remote collection, or **This Mac only** for
local collection. **Parallel · this Mac + ready nodes** shares one collection:
the main Mac reads the creator's list pages, then all participating Macs fetch
different video details concurrently. Automatic chooses one Mac per collection;
Parallel explicitly requires at least one ready node with the latest source.
The returned rows fill the usual in-memory working dataset;
Statistics, Ratios, Charts and batch tasks reuse it without another collection.

Set **Collection requests per second → Apply pacing** on Dataset (0.1–4).
Settings shows the same value. Connected nodes honor this rate with their own
local cap; Parallel divides it across the participating Macs. It does not multiply
the selected rate by the number of nodes. Sync, stop and restart older node apps,
then re-pair, to advertise support for pacing and Parallel collections.
Invalid metric rows are replaced until the requested valid count is reached or
the scan limit is reached. A rejection stops collection and preserves the previous
dataset. Only one operation can replace the working dataset at a time.

Transient bottom notices dismiss after four seconds (eight seconds for errors).
Hovering holds a dashboard notice open. Live task progress stays visible while running.

The node GUI includes **Check connection**, which verifies the main listener
without consuming a pairing code. Copy the LAN address including the actual
port from the Nodes page. For chat coordination over iCloud, use
[MAIN_MAC.txt](docs/coordination/MAIN_MAC.txt) and
[NODE_MAC.txt](docs/coordination/NODE_MAC.txt), with one chat writing each file.

Open **Workspace → Nodes** to start the separate connection service, generate
one-use pairing codes, and pause/resume or remove nodes. Normal fetching stays
on Dataset; Tasks uses the same automatic routing. The optional **Advanced
collections** section holds the separate queue for links and separate reports.
Fetching Macs run a lightweight app with a local web GUI for pairing, pacing,
pausing and progress. Video links are split into batches across nodes; creator
collections target a valid video count on an assigned node. Returned results show
performance and engagement averages and remain separate from the working dataset.

Copy or clone the source project on each fetching Mac. Double-click
`setup-node.command` once, then `start-node.command`. The node setup installs
the SDK, HTTP client and their dependencies without Matplotlib; running the node does not import the dashboard
or Matplotlib. Keep each Mac's environment and account files local instead of
copying `.venv`, `venv`, `.runtime`, or personal `objects/creators.json` contents.
See [distributed setup and recovery](docs/distributed.md) for the connection steps,
RAM-only state, supported tasks and trusted-LAN/private-VPN scope.

## Weekly Popular Averages

Open **Workspace → Data → Sampling → Weekly popular** and paste a Bilibili weekly page URL, such as
`https://www.bilibili.com/v/popular/weekly?num=393`, or enter its issue number.
**Fetch / Analyze issue** collects the list's metric data and shows totals, means,
medians, extrema and P90 for views, likes, replies, favorites, coins and shares.
Engagement includes both the average per-video ratio and the pooled ratio
(total interactions / total views). Zero-view videos are excluded from ratios.

Videos with incomplete list metrics get a detail request; invalid or unavailable
videos are skipped, and repeated IDs count once. The page reports included and
excluded counts and lets you inspect individual videos. It keeps the creator
dataset separately and does not apply its local filters to the weekly cohort.
Navigation retains the report in memory; only the fetch button recollects it.
Metrics describe accumulated performance observed during collection, rather than
performance earned during the issue's week or averages across all Bilibili videos.
No weekly dataset or report files are created.

## Working with a Dataset

Choose a Creator and selection, then click **Fetch / Refresh**. Listing, analysis,
division, and plotting reuse that collection in RAM. Changing the Creator, account,
or fetch selection requires another explicit fetch. The status shows the collection
interval: values are observed sequentially, not at one simultaneous instant.
A failed refresh keeps the previous dataset; summary-page failures are reported.
Refreshing or reopening the webpage restores its video table and fetch selection
from server RAM without collecting again. The latest retained weekly and random
reports also return. If collection is still running, the page reconnects to its
progress and shows the completed dataset. No fetched rows are saved in browser
storage or dataset files. Charts and analysis can be rerun on the restored data.
Collection skips videos without all six valid, nonnegative whole-number metrics
(views, likes, replies, favorites, coins, shares); zero remains valid.
For a number range, Start is the original publication position and End − Start + 1
is the target number of valid videos. Collection continues to older videos until
that target is met: requesting 1–100 with two invalid videos checks 102 and keeps 100.
Repeated video IDs do not count twice. If available videos run out, the status
reports the shortfall, alongside checked, skipped, and requested counts.
Date and metric selections skip invalid videos without extending their boundaries.
Server rejections stop collection and preserve the previous dataset.
Zero denominators can still prevent ratio plots even when all metrics are present.

Local minimum/maximum view filters are inclusive and run without network requests.
They only narrow the fetched selection; clear both to include every fetched row.
In Statistics, **Chart metric** updates the selected metric's summary, histogram,
box plot, and unusual values locally. Run **Analyze Dataset** first to enable it.
The all-metrics comparison remains available in a separate expandable table.

Quartiles and P90 interpolate at `(n - 1) * percentile`. Outliers are values outside
`Q1 - 1.5 * IQR` and `Q3 + 1.5 * IQR`, flagged only with at least four valid values.
Duplicates remain included and are reported. Missing, invalid, and negative counts
are excluded per metric; zero remains valid. Engagement ratios exclude zero views
and missing pairs. The fewer-than-100-views flag is descriptive and does not remove rows.
Pooled engagement weights videos by views; median engagement describes the typical
per-video ratio. Neither measures unique-user conversion or current growth.

Dataset reuse and analysis create no data, image, or cache files. A successful fetch
replaces the previous dataset; stopping or restarting Python clears it.
The dashboard shares one dataset across local browser tabs.

## Development Reload

Both main and development modes update the browser automatically when source changes:
CSS updates in place. HTML and JavaScript refresh the page after the current browser
task and collection finish. The active page, sampling tab, analysis source, form
values and scroll position are restored. Passwords and pairing codes are excluded.
The independent browser watcher can recover after fixing a syntax error in `app.js`.
Interface updates keep the Python process, RAM datasets/cohorts and node connections.
Browser-rendered analysis results need running again on the retained data.

Use `start-web.command` for automatic Python restarts too. Saving Python files under
`bilibili_ds/` or root compatibility scripts restarts the development worker.
This clears its RAM datasets, coordinator state, in-progress requests and QR attempts.
The supervisor survives Python syntax errors and retries after the next save.
With `start-main.command`, Python edits show a restart notice and leave the backend
running. Changes to the supervisor itself require restarting the launcher.
Updating `objects/creators.json` refreshes the Creator list without a server restart.
Caches, plots, and virtual environments do not trigger restarts.
This refreshes edited source files, not Bilibili data; fetch data again explicitly
to get updated counts.

Disable automatic Python restarts or choose another port with:

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
Run `node tests/browser/navigation.cjs` to check that switching pages, Sampling
tabs and Back navigation preserve scroll position on desktop and mobile.
Run the analysis browser checks with `node tests/browser/analysis.cjs`. They verify
local chart changes, filter payloads, and desktop/mobile layout using sample data.
Run `node tests/browser/batch.cjs` for task ordering, dataset reuse, captured settings,
result rendering, failure handling, stopping, and responsive Tasks layout.
Run `node tests/browser/nodes.cjs` for pairing through two node web GUIs,
distributed result collection, targeting, creator tasks, revocation and layout.

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
- `POST /api/weekly-analysis`: collect a weekly issue and calculate cohort averages.
- `POST /api/random-sample`: collect a bounded, filtered keyword-search pool and return a random video sample with averages.
- `/api/nodes`: local-only node service, paired Macs and collection queue.
- `/api/nodes/result?id=...`: local-only received videos and cohort analysis.
- `POST /api/nodes/service`, `/api/nodes/pairing`, `/api/nodes/action`: local node connection controls.
- `POST /api/nodes/tasks`, `/api/nodes/tasks/action`: queue, cancel or clear distributed collections.
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
