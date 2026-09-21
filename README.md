<h1 align="center">JAV Downloader</h1>

<p align="center">
  Headless download engine for supported streaming sites.<br />
  Pass one or more video URLs; the core resolves streams, downloads segments, and writes MP4 files.
</p>

<p align="center">
  <a href="https://github.com/nishatislam04/jav-downloader/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/nishatislam04/jav-downloader?style=flat-square&label=release&color=ff5263" /></a>
  <a href="https://github.com/nishatislam04/jav-downloader"><img alt="GitHub stars" src="https://img.shields.io/github/stars/nishatislam04/jav-downloader?style=flat-square&logo=github&color=f5b942" /></a>
  <a href="./LICENSE"><img alt="Apache 2.0 license" src="https://img.shields.io/github/license/nishatislam04/jav-downloader?style=flat-square" /></a>
</p>

## Supported sites

| Site | Download |
|---|:---:|
| JableTV | ✓ |
| MissAV | ✓ |
| SupJav | ✓ |
| Hanime1 | ✓ |
| Jav.guru | ✓ |
| SpankBang | ✓ |

Legacy URL-only adapters stay registered for compatibility. Sites and CDNs change without notice — update to the latest version and open an Issue with a reproducible URL if something breaks.

## Quick start

Requires **Python 3.10+**. On Windows, install `make` first (e.g. `choco install make`).

```bash
git clone https://github.com/nishatislam04/jav-downloader.git
cd jav-downloader
make install
make start
```

Open **<http://127.0.0.1:8765/**>, paste a URL, download. Files go to your default Downloads folder (or `DOWNLOAD_DIR`).

### CLI only

| Command | Purpose |
|---|---|
| `jav-downloader-cli` | Headless batch download (primary) |
| `jav` / `jav-downloader` | Same entry point |
| `jav-web` | Web UI + API server (what `make start` runs) |

```bash
DOWNLOAD_DIR=./download jav-downloader-cli \
  "https://jable.tv/videos/example/" \
  "https://supjav.com/123456.html"
```

## Termux (Android) — full setup

1. Install **Termux** from [F-Droid](https://f-droid.org/en/packages/com.termux/) or GitHub Releases — not the Play Store build.

2. Update packages and install the toolchain:

   ```bash
   pkg update && pkg upgrade -y
   pkg install -y python git make clang
   ```

3. Grant storage access — tap **Allow**. This enables `~/storage/downloads`:

   ```bash
   termux-setup-storage
   ```

4. Get the code and install:

   ```bash
   git clone https://github.com/nishatislam04/jav-downloader.git
   cd jav-downloader
   make install
   ```

5. Recommended — stops Android from freezing long downloads when the screen turns off:

   ```bash
   termux-wake-lock
   ```

6. Start the server:

   ```bash
   make start
   ```

7. Open the UI:

   - On the phone: **<http://localhost:8765**>
   - From another device on the same Wi-Fi: **http://<phone-ip>:8765** (Termux binds `0.0.0.0`)

Downloads land in the Android **Downloads** folder (`~/storage/downloads`), visible in any file manager. Keep Termux in the foreground or use `termux-wake-lock` while downloading — Android kills background apps.

## Configuration

| Variable | Purpose |
|---|---|
| `DOWNLOAD_DIR` | Output folder (CLI default `/downloads` — set a writable path; Termux: `~/storage/downloads`) |
| `RESOLUTION` | `highest`, `1080`, `720`, `480`, `360`, `lowest` |
| `MAX_WORKERS_PER_VIDEO` | Segment workers per video, `1`–`16` |
| `URL` / `URLS` | URLs via environment (space- or comma-separated) |
| `URLS_FILE` | URL list file, one per line, `#` comments (default `<DOWNLOAD_DIR>/urls.txt`) |
| `WEB_HOST` / `WEB_PORT` | Server bind address / port (default `8765`) |

- URLs are collected in this order: CLI args → `URLS`/`URL` → `URLS_FILE`.
- MissAV caps workers automatically; SupJav and Hanime1 direct downloads use max 4 ranged connections.
- ffmpeg is optional — only needed for remux/encode post-processing.

## Development

```bash
make test        # pytest suite
make web-build   # rebuild UI after frontend edits
```

- Frontend: `web/frontend/` — Vite + SolidJS, Biome lint/format. The built bundle is committed under `src/jav_downloader/web/static/`, so Termux never needs Node.
- Encoding pipeline: see `docs/encoding-architecture.md`.

## License and responsible use

Code is licensed under the [Apache License 2.0](./LICENSE). Use this tool only for lawful personal or research purposes — follow local law, site terms, and content rights, and download only material you are authorized to access.

<p align="center">Maintained by <a href="https://github.com/nishatislam04">nishatislam04</a>.</p>
