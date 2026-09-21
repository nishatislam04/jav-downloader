<h1 align="center">JAV Downloader</h1>

<p align="center">
  Headless download engine for supported streaming sites.<br />
  Paste video URLs in the browser; the core resolves streams, downloads segments, and writes MP4 files.
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

Requires **Python 3.10+**.

```bash
git clone https://github.com/nishatislam04/jav-downloader.git
cd jav-downloader
make install
make start
```

Open the web UI, paste a URL, download. Files go to your default Downloads folder (or `DOWNLOAD_DIR`).

Which address to use:

- Running `make start` (Termux / server): **<http://localhost:8765**> — or **http://<phone-ip>:8765** from another device on the same Wi-Fi
- Frontend development with Vite: **<http://localhost:5173**> (proxies the API to `:8765`)

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
| `DOWNLOAD_DIR` | Output folder (web default: your Downloads folder; Termux: `~/storage/downloads`) |
| `WEB_HOST` / `WEB_PORT` | Server bind address / port (default `8765`) |

- MissAV caps workers automatically; SupJav and Hanime1 direct downloads use max 4 ranged connections.
- ffmpeg is optional — only needed for remux/encode post-processing.

## Development

```bash
make test        # pytest suite
make web-build   # rebuild UI after frontend edits
```

- Frontend dev with hot reload: `make web-api` (API on :8765) + `make web-dev` (Vite on :5173) — laptop only, needs Node.
- Frontend source: `web/frontend/` — Vite + SolidJS, Biome lint/format. The built bundle is committed under `src/jav_downloader/web/static/`, so Termux never needs Node.
- Encoding pipeline: see `docs/encoding-architecture.md`.

## License and responsible use

Code is licensed under the [Apache License 2.0](./LICENSE). Use this tool only for lawful personal or research purposes — follow local law, site terms, and content rights, and download only material you are authorized to access.

<p align="center">Maintained by <a href="https://github.com/nishatislam04">nishatislam04</a>.</p>
