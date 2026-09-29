# Project Architecture

The project has two interfaces over shared Python modules: an interactive terminal
and a local browser dashboard. The browser uses native JavaScript modules; no
JavaScript build step or additional web framework is required.

## Directory Map

```text
Bilibili_DataScience/
    bilibili_ds/             Shared Python application code
        __main__.py         Terminal module entry point
        config.py           Project paths and defaults
        state.py            Request rate and terminal session state
        storage.py          JSON files and terminal UP selection
        accounts.py         Credentials and account cache operations
        client.py           Network configuration, pacing, cleanup
        videos.py           Bilibili video and creator requests
        selection.py        Sorting, parsing, and filters
        analysis.py         Statistics and ratios
        plotting.py         Headless PNG rendering
        cli/                Terminal interface
            menu.py         Navigation and command dispatch
            prompts.py      Interactive input
            accounts.py     Terminal account workflows
            creators.py     Terminal creator workflows
            actions.py      Fetch, analysis, division, plot workflows
            output.py       Terminal formatting
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
    tests/
        unit/               Calculations, serialization, asset validation
        integration/        Storage, mocked APIs, entry points, HTTP, reload
    scripts/
        preview_dashboard.py  Sample-data dashboard, no Bilibili requests
    docs/
        architecture.md     This guide
    requirements.txt        Direct Python dependencies
    main/main.py            Compatibility terminal launcher
    web_server.py           Compatibility web launcher
    web_reload.py           Compatibility supervisor imports
    start-macos.command     macOS terminal launcher
    start-web.command       macOS web launcher
    objects/ups.json         Existing saved UP identities
    .runtime/               Existing private caches and generated plots
```

## Dependency Direction

```text
Terminal interface -> Shared Python modules -> Bilibili API / local storage
Browser modules -> HTTP routes -> Web workflows -> Shared Python modules
```

Shared modules do not import either interface. The web backend does not load
`main/main.py` or import terminal menus. New code should import its owning module
directly, not the compatibility launchers.

Web-specific selection rules and result formats remain in `web/` to preserve
existing behavior. For example, terminal and browser creator normalization have
different historical rules; this reorganization does not silently unify them.

## State and Files

- `config.py` is the source of truth for paths, all anchored to the checkout, not
  the current working directory.
- `state.py` owns the shared process request rate and terminal session selection.
- `web/state.py` owns browser creator selection, progress, and QR login state.
- `static/js/state.js` owns browser display state. It contains no credentials.
- Account credentials, cookies, QR images, and plots keep their existing paths
  under `.runtime/`. The reorganization does not migrate or rewrite user data.
- `/static/` serves only `.js` and `.css` files confined to the static directory.
  Traversal paths and symlinks outside that directory are rejected. Private
  runtime files are not exposed as a general static directory.

Both interfaces are local, single-user tools. Process-wide request settings and
progress are not isolated by browser session; this is not a multi-user service.

## Entry Points and Reload

`python -m bilibili_ds` opens the terminal menu. `python -m bilibili_ds.web` starts
the dashboard. Existing direct scripts and macOS launchers still work.

The web entry point starts the supervisor before importing application modules,
so a syntax error in application code does not kill the watcher. It watches
`bilibili_ds/`, `main/`, `templates/`, `static/`, and the root compatibility scripts.
Each worker uses a fresh bytecode-cache namespace and disables cache writes.

The HTML template receives the worker token in a meta tag. `dev_reload.js` polls
the server and refreshes the browser after a worker change, retaining the active
tab and form values. Changes to the saved UP list refresh that list without a
server restart. In-flight requests and transient results reset on source reload.
Changes to the supervisor itself require restarting the launcher.

## Extending the Project

Put reusable evaluation calculations in a new shared module, with unit tests.
Add browser-specific response handling in `web/` and presentation in
`static/js/views/`. Keep network calls and credentials on the Python side. Avoid
introducing imports from shared calculations back into the terminal or web layers.
