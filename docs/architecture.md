# Project Architecture

The project is a local browser application backed by reusable Python modules.
The browser uses native JavaScript modules; no
JavaScript build step or additional web framework is required.

## Directory Map

```text
Bilibili_DataScience/
    bilibili_ds/             Shared Python application code
        config.py           Project paths and defaults
        state.py            Process-wide request rate
        storage.py          JSON persistence helpers
        accounts.py         Credentials and account cache operations
        client.py           Network configuration, pacing, cleanup
        videos.py           Video detail requests and response handling
        selection.py        Sorting, parsing, and filters
        analysis.py         Statistics and ratios
        weekly.py           Weekly cohort averages and engagement eligibility
        sampling.py         Filter validation and random draws from eligible candidates
        plotting.py         Headless PNG rendering
        web/                Local HTTP interface
            __main__.py     Supervisor or worker startup
            server.py       HTTP server lifecycle
            routes.py       Endpoint dispatch and HTTP responses
            http.py         JSON request parsing
            assets.py       Template rendering and public asset lookup
            accounts.py     Browser account workflows
            creators.py     Browser creator selection and storage adapter
            videos.py       Browser fetching and selection
            weekly.py       Weekly source validation and collection
            sampling.py     Bounded search collection and refreshed detail metrics
            actions.py      Browser analysis, ratios, and plotting
            serializers.py Browser-facing fields and result formats
            plots.py       Browser plot rendering and listings
            progress.py    Progress updates
            state.py       Transient browser state
            reload.py      Development supervisor
    templates/
        dashboard.html      Dashboard markup
    static/
        css/dashboard.css   Existing responsive styles
        js/
            app.js          Initialization, navigation, action bindings
            api.js          JSON HTTP requests
            constants.js    Metric names and labels
            state.js        Browser-only state
            ui.js           Common formatting and action feedback
            selection.js    Selection form values
            progress.js     Operation progress polling
            batch.js        Sequential task execution and queue feedback
            dev_reload.js  Source-change refresh and form restoration
            views/          Accounts, creators, videos, and plots
        vendor/             ECharts 5.6.0 and selected Lucide 1.8.0 modules
    tests/
        unit/               Calculations, serialization, asset validation
        integration/        Storage, mocked APIs, entry points, HTTP, reload
    scripts/
        preview_dashboard.py  Sample-data dashboard, no Bilibili requests
    docs/
        architecture.md     This guide
    requirements.txt        Direct Python dependencies
    web_server.py           Compatibility web launcher
    web_reload.py           Compatibility supervisor imports
    start-web.command       macOS web launcher
    objects/creators.json         Existing saved Creator identities
    .runtime/               Existing private caches and generated plots
```

## Dependency Direction

```text
Browser modules -> HTTP routes -> Web workflows -> Shared Python modules
Shared Python modules -> Bilibili API / local storage
```

Shared modules do not import the web interface. New code should import its owning
module directly, not the compatibility launchers.

Web-specific creator selection rules and result formats live in `web/`.

## State and Files

- `config.py` is the source of truth for paths, all anchored to the checkout, not
  the current working directory.
- `state.py` owns the shared process request rate.
- `web/state.py` owns browser creator selection, progress, and QR login state.
- `web/dataset.py` retains one RAM-only dataset keyed by Creator, account ID, and fetch
  selection. Explicit refresh replaces it only on success. A nonblocking lock
  rejects overlapping video operations. `reuse_only` requests never fetch silently.
  Local view filters run on a copy and do not mutate the retained collection.
  Collection metadata tracks requested, examined, skipped and shortfall counts.
  `web/videos.py` pages forward from the requested publication position until it
  collects End − Start + 1 unique videos with six valid metrics or runs out of
  available videos. It retains only valid rows. Date/metric ranges retain their
  boundaries. Request pacing applies to replacement requests too; summary errors
  and recognized server rejection codes abort the refresh.
- `distributions.py` contains pure quantile, histogram, IQR, quality, and engagement
  calculations. `static/js/views/analysis.js` renders tables and inline SVG charts
  without PNG generation or disk writes.
- `web/plots.py` keeps at most 20 unsaved plot snapshots in memory, keyed by
  opaque IDs. Plot generation never writes PNGs. `POST /api/plots/save` exports
  the referenced snapshot on demand and returns the existing file on retries.
  A lock protects the snapshot cache and serializes matplotlib exports.
- `static/js/state.js` owns browser display state. It contains no credentials.
- Account credentials, cookies, QR images, and plots keep their existing paths
  under `.runtime/`. Creator identities are stored in `objects/creators.json`
  under the `creators` collection key; the terminology rename preserves existing entries.
- `/static/` serves only `.js` and `.css` files confined to the static directory.
  Traversal paths and symlinks outside that directory are rejected. Private
  runtime files are not exposed as a general static directory.

The application is a local, single-user tool. Process-wide request settings and
progress are not isolated by browser session; this is not a multi-user service.

## Entry Points and Reload

Double-click `start-web.command` on macOS to start the dashboard in a foreground
Terminal window. Press Control+C in that window to stop the server and watcher.
The server runs independently of ChatGPT. Closing the Terminal window and
confirming termination also stops both processes.

`python -m bilibili_ds.web` and `python web_server.py` start the same dashboard.

The web entry point starts the supervisor before importing application modules,
so a syntax error in application code does not kill the watcher. It watches
`bilibili_ds/`, `templates/`, `static/`, and the root compatibility scripts.
Each worker uses a fresh bytecode-cache namespace and disables cache writes.

The HTML template receives the worker token in a meta tag. `dev_reload.js` polls
the server and refreshes the browser after a worker change, retaining the active
tab and form values. Changes to the saved Creator list refresh that list without a
server restart. In-flight requests and transient results reset on source reload.
Changes to the supervisor itself require restarting the launcher.

## Interactive Plots

`static/js/views/plots.js` owns the ECharts instance, chart controls, hover details,
visible-range Y-axis scaling, and manual saving. Valid dated points are sorted
chronologically and use a true time axis; undated points use a category axis.
ResizeObserver handles layout and tab changes. Exports from the download icon
capture the current browser chart; Saved Plots contains full-range Python PNGs.
The browser legend sits below the canvas; downloads append it as an in-memory footer.
Saved PNGs reserve a separate figure footer for the legend.
Both renderers use zero-based axes with 1/2/5-based tick intervals. MA5/MA10/MA20
use full trailing windows over valid plotted points, with nulls before the first
complete window. Zooming scales against visible raw and MA values without
recomputing windows. Save requests include `ma_periods`; the server validates and
normalizes these, and caches exports by axis mode, MA windows, and additional
`indicators`. `bilibili_ds/indicators.py` and `static/js/indicators.js` implement the
same pure trailing calculations: seeded EMA, full-window median, and relative
performance against the preceding 20 observations. Zero baselines produce gaps.
Relative20 uses a separate ECharts instance with bidirectional zoom synchronization;
PNG downloads combine both panels in memory and Python exports share their X-axis.
The main plot keeps its height when the relative panel is enabled.
The vendored modules require no frontend build or external CDN access. Preserve
upstream headers and `docs/licenses/` when updating them.

## Extending the Project

Put reusable evaluation calculations in a new shared module, with unit tests.
Add browser-specific response handling in `web/` and presentation in
`static/js/views/`. Keep network calls and credentials on the Python side. Avoid
introducing imports from shared calculations back into the web layer.

## Dashboard Organization

Primary navigation groups Explore (Creators library, creator profile and single video), Workspace
(dataset rows, statistics, custom ratios, charts, sampling, tasks, saved charts), and Settings.
`app.js` maps each tool to a section and remembers its last active view in memory.
Before switching panels or Sampling tabs, `ui.preservePageHeight()` reserves enough
minimum height in the main element to keep the current viewport reachable. Main
content disables scroll anchoring so replacing a panel does not shift the page.
The minimum is recalculated on each switch; content can grow naturally, and
navigating after scrolling to the top releases any spare space.
The collection/filter panel appears only on Dataset; other tools reuse its settings.
A successful fetch updates rows and collapses collection controls without changing
the active page. Navigation itself does not fetch data. Live reload restores
the active tool using the main element's `data-active-panel` attribute.

Quick creator switching uses an anchored dropdown on the Back button row with its own search input.
The Creators panel handles browsing and adding saved identities. Both lists use
`views/creators.js`, and selection updates do not reload unrelated sections.
`app.js` keeps a RAM-only menu history. Blank clicks on bare layout surfaces and
an explicit Back button pop that history. An open dropdown takes precedence:
outside clicks dismiss it without navigation. Controls, charts, and results are
excluded. Page changes retain dataset filters and fetched results.

The Tasks page queues Fetch, Ratios, Statistics and Charts in dependency order.
`app.js` shares task definitions and result renderers between individual actions
and `batch.js`. A batch captures the selection, filters and each task's options
before sending sequential `/api/video-action` requests under one browser action
guard. Only its fetch step sets `refresh`; later steps keep `reuse_only` enabled.
Inputs and configuration buttons are disabled while the queue runs. Navigation
stays available. Failure or a stop request skips subsequent tasks; stopping lets
the current request complete. The queue lives in the browser's memory and requires
the tab to remain open. It does not add an endpoint, persistent queue or disk writes.

Sampling groups Random sample and Weekly popular in local tabs. Random sample
uses `POST /api/random-sample`; `web/sampling.py` searches video-only candidates
with the installed SDK, at most `ceil(pool_size / 20)` search pages and at most
500 candidate entries. Every unique BVID gets paced detail enrichment; duplicate
entries need no repeated detail request. `sampling.py` rejects incomplete metrics,
applies inclusive metric boundaries and Beijing-time publication dates, and uses
a request-local seeded PRNG to sample uniformly without replacement across the
entire eligible pool. A shortfall is reported instead of silently increasing the
candidate limit. Search ranking limits the population represented by the sample.
The report includes candidate, detail, duplicate, invalid, filtered, eligible,
sampled and requested counts, seed and collection times. The shared cohort
renderer shows summaries and engagement ratios. Collection shares `dataset.LOCK`
and never modifies `dataset.CURRENT`; it stops on API rejection. Successful
results remain in the browser when navigating; a failed request retains the old
report. No new dataset, cache or report files are created.

Weekly popular uses `POST /api/weekly-analysis` with an issue number or a validated
Bilibili weekly-page URL. `web/weekly.py` calls the installed library's weekly API;
it never requests an arbitrary user-provided URL. Complete list metrics avoid
per-video requests; incomplete entries use the existing paced detail fetcher.
It shares the video-operation lock but does not modify `dataset.CURRENT`.
`weekly.py` deduplicates the cohort, excludes invalid records, and calculates count
summaries and equal-weight versus pooled engagement ratios. The browser retains
the report when navigating or when a later fetch fails. No report is saved to disk.
