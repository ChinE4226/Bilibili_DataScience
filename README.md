# Bilibili Data Science 

## The Repository

This is an object-oriented and python-based data science project, for Bilibili vloggers, using the APIs of Bilibili.

## Getting Started

double-click the file "start-macos.command"

the automatic programme will check the environment and get start

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
- `main/main.py`: main terminal programme, menu flow, sign-in, UP selection, and Bilibili API requests.
- `objects/ups.json`: permanent UP list. This file should store only UP identity data.
- `.runtime/`: local runtime cache for sign-in accounts, active account selection, and QR code images. The directory placeholder is tracked by git; generated files inside it are ignored.

### `objects/ups.json` Structure

`objects/ups.json` should keep only the UP accounts that can be selected by the programme.

```json
{
  "ups": [
    {
      "name": "Geekerwan",
      "space": "https://space.bilibili.com/25876945",
      "uid": "25876945"
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

6. plot the data of the UP's videos, selected by the specific data

## the APIs source

https://github.com/Nemo2011/bilibili-api

GPL-3.0 license

## License

GPL-3.0 license

Copyright (c) 2026 ChinE4226 

All rights reserved.
