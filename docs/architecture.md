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
Both renderers use zero-based axes with 1/2/5-based tick intervals.
The vendored modules require no frontend build or external CDN access. Preserve
upstream headers and `docs/licenses/` when updating them.

## Extending the Project

Put reusable evaluation calculations in a new shared module, with unit tests.
Add browser-specific response handling in `web/` and presentation in
`static/js/views/`. Keep network calls and credentials on the Python side. Avoid
introducing imports from shared calculations back into the web layer.

## Dashboard Organization

Primary navigation groups Explore (Creators library, creator profile and single video), Workspace
(dataset rows, statistics, custom ratios, charts, saved charts), and Settings.
`app.js` maps each tool to a section and remembers its last active view in memory.
One collection/filter panel stays above the Workspace tools; it is hidden for
saved charts and other sections. A successful fetch displays rows and collapses
collection controls. Navigation itself does not fetch data. Live reload restores
the active tool using the main element's `data-active-panel` attribute.

Quick creator switching uses an anchored dropdown with its own search input.
The Creators panel handles browsing and adding saved identities. Both lists use
`views/creators.js`, and selection updates do not reload unrelated sections.
`app.js` keeps a RAM-only menu history. Blank clicks on bare layout surfaces and
an explicit Back button pop that history. An open dropdown takes precedence:
outside clicks dismiss it without navigation. Controls, charts, and results are
excluded. Page changes retain dataset filters and fetched results.
