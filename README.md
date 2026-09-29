# Bilibili Data Science

A local Python tool for exploring Bilibili creators and videos through a terminal
menu or browser dashboard.

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

Start the terminal interface:

```sh
python -m bilibili_ds
```

On macOS, double-click `start-web.command` for the website or
`start-macos.command` for the terminal. Existing commands
`python web_server.py` and `python main/main.py` still work.

## Project Structure

```text
bilibili_ds/          Shared Python logic, paths, and settings
    cli/             Terminal menus, prompts, and workflows
    web/             HTTP routes, web workflows, and development reload
templates/           Dashboard HTML
static/
    css/             Responsive styles
    js/              Browser modules and feature views
tests/
    unit/            Calculations, validation, and serialization
    integration/     Storage, requests, launchers, HTTP, and reload
scripts/             Local development tools and sample-data preview
docs/                Architecture and maintenance guide
objects/             Saved UP identities
.runtime/            Private account caches, QR images, and generated plots
requirements.txt     Python dependencies used by this checkout
main/main.py         Small compatibility terminal launcher
web_server.py        Small compatibility web launcher
web_reload.py        Compatibility supervisor imports
```

See [the architecture guide](docs/architecture.md) for individual module
responsibilities, dependency direction, state ownership, and extension points.
The website imports shared Python modules directly; it no longer loads the
terminal entry point. No frontend build step is required.

## Features

- QR sign-in, cached account selection, guest mode, and sign-out.
- Saved UP selection and account or creator profile details.
- Temporary lookup of one video by its Bilibili URL or BV ID.
- Video selection by published-time position, date range, or metric range.
- Mean and median of views, likes, replies, favorites, coins, and shares.
- Per-video and aggregate ratios, including ratios involving follower counts.
- Browser charts, PNG plots, saved-plot browsing, and fetching progress.

In aggregate division, followers are multiplied by the selected video count.
Single-video lookup results stay only in the current page and are replaced by
the next lookup; no cover image is displayed.

## Development Reload

Automatic reload is enabled by default. Saving Python files under `bilibili_ds/`
or `main/`, HTML under `templates/`, or CSS/JavaScript under `static/` restarts
the worker and refreshes open pages. Root compatibility scripts are watched too.
The watcher survives application syntax errors and retries after the next save.
Changes to the watcher itself take effect after restarting the launcher.

The browser preserves the active tab and form values. Fetched results,
in-progress requests, QR login attempts, and other in-memory state reset.
Updating `objects/ups.json` refreshes the UP list without a server restart.
Caches, plots, and virtual environments do not trigger restarts.

Disable automatic reload or choose another port with:

```sh
python -m bilibili_ds.web --no-reload --port 8010
```

The dashboard retains its tab-based layout: selection controls follow Videos,
Analysis, Division, and Plot; Single Video, Saved Plots, and Settings use the
full workspace. Wide tables and charts scroll within their own areas.

## Tests and Preview

Run the offline regression suite:

```sh
.venv/bin/python -m unittest discover -s tests -t . -v
```

Tests use temporary files and mocked Bilibili responses. HTTP and reload tests
open temporary localhost ports. They do not sign in or contact Bilibili.

Preview the dashboard using sample data only:

```sh
.venv/bin/python scripts/preview_dashboard.py
```

The preview defaults to [http://127.0.0.1:8012](http://127.0.0.1:8012);
`--port` selects a different port. Account-changing actions are disabled.

## Saved Data

Existing data locations and formats are unchanged:

- `objects/ups.json`: permanent UP identities only.
- `.runtime/accounts/`: cached account credentials.
- `.runtime/active_account.json`: active account selection.
- `.runtime/bilibili_credential.json`: legacy credential cache.
- `.runtime/bilibili_cookie.txt`: optional local cookie input.
- `.runtime/bilibili_qrcode.png`: current sign-in QR image.
- `.runtime/plots/`: generated PNG plots.

A UP file has this format:

```json
{
  "ups": [
    {
      "name": "Example",
      "space": "https://space.bilibili.com/123456",
      "uid": "123456"
    }
  ]
}
```

`selected_uid` is kept in memory, not saved in this file. Credentials, cookies,
QR images, and fetched profile details do not belong in the UP list.
Generated runtime files are ignored by Git. Do not commit credentials.

## Useful Endpoints

- `/`: dashboard.
- `/static/`: public CSS and JavaScript only.
- `/api/health`: selected UP, account summary, and request rate.
- `/api/ups`: saved UP list.
- `/api/progress`: current operation progress.
- `/api/plots`: saved PNG plot list.
- `POST /api/video-lookup`: temporary video lookup using a `video` URL or BV ID.
- `POST /api/video-action`: listing, analysis, division, or plotting.
- `/plots/<file>.png`: generated plot images.

## API Source and License

Bilibili access uses [bilibili-api-python](https://github.com/Nemo2011/bilibili-api).

GPL-3.0 license. See [LICENSE](LICENSE).

Copyright (c) 2026 ChinE4226

All rights reserved.
