# Bilibili Data Science 

## The Repository

This is an object-oriented and python-based data science project, for Bilibili vloggers, using the APIs of Bilibili.

## Getting Started

double-click the file "start-macos.command"

the automatic programme will check the environment and get start

To start the local web UI in Google Chrome, double-click `start-web.command` or run:

```
$ python3 web_server.py
```

Then open:

```
http://127.0.0.1:8000
```

```
$ pip3 install bilibili-api-python

$ pip3 install httpx
```

## Project Structure

```
Bilibili_DataScience/
├── README.md
├── LICENSE
├── start-macos.command
├── start-web.command
├── web_server.py
├── main/
│   └── main.py
├── objects/
│   └── ups.json
└── .runtime/
    ├── active_account.json
    ├── bilibili_credential.json
    ├── bilibili_qrcode.png
    └── accounts/
```

### Main Files

- `start-macos.command`: macOS launcher. Double-click it to start `main/main.py`.
- `start-web.command`: macOS launcher. Double-click it to start the local web server.
- `main/main.py`: main terminal programme, menu flow, sign-in, UP selection, and Bilibili API requests.
- `web_server.py`: local Python web server for viewing saved plots, saved UPs, and project status in a browser.
- `objects/ups.json`: permanent UP list. This file should store only UP identity data.
- `.runtime/`: local runtime cache for sign-in accounts, active account selection, and QR code images. The directory placeholder is tracked by git; generated files inside it are ignored.

### `objects/ups.json` Structure

`objects/ups.json` should keep only the UP accounts that can be selected by the programme.

```json
{
  "ups": [
    {
      "name": "Example",
      "space": "https://space.bilibili.com/123Example456",
      "uid": "123Example456"
    }
  ]
}
```

Rules:

- `name`: display name shown in the menu.
- `space`: Bilibili space URL.
- `uid`: Bilibili user ID parsed from the space URL.
- `selected_uid` is not stored in this file. The selected UP is kept in memory only while the programme is running.
- Account credentials, QR codes, cookies, and active account data belong in `.runtime/`, not in `objects/ups.json`.
- Detailed UP profile data fetched from the API is printed in the terminal and should not be stored in `objects/ups.json`.

## Project Functions

1. sign in through the QR code and sign out, as well as keep caches

2. view account details of your account

3. view account details of the selected UP

4. get the video list of the selected UP by selecting videos with a published time range, a data value range, or a published-time ordered number range

5. analyse videos selected by the same range menu, then calculate mean average and median for views, likes, replies, favorites, coins, and shares

6. divide one selected data set by another, either for every selected video or once across all selected videos, using views, likes, replies, favorites, coins, shares, or followers. In aggregate mode, followers are multiplied by the selected video count.

7. plot selected videos by published time as a PNG, either for one data field or for the quotient of one data set divided by another

8. run a local web server to use the main account, UP, video listing, analysis, division, and plotting functions from a browser

## Web Server

The local web server uses only Python standard-library HTTP server tools. It binds to `127.0.0.1:8000` by default, or the next free port if `8000` is already in use. The macOS launcher opens the page with Google Chrome.

Useful endpoints:

- `/`: browser dashboard
- `/api/health`: project status, selected UP, account condition, and request frequency
- `/api/ups`: saved UP list
- `/api/plots`: generated PNG plot list
- `/plots/<file>.png`: generated plot image files

The dashboard includes controls for:

- selecting and adding UPs
- selecting videos by published-time number range, published time range, or metric value range
- listing videos
- calculating mean and median
- calculating division ratios
- plotting one data field or a quotient in the browser
- viewing account and selected UP details
- QR sign-in, cached account selection, guest mode, sign-out, and request frequency

## the APIs source

https://github.com/Nemo2011/bilibili-api

GPL-3.0 license

## License

GPL-3.0 license

Copyright (c) 2026 ChinE4226 

All rights reserved.
