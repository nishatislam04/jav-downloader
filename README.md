<h1 align="center">UAV Downloader</h1>

<p align="center">
  Headless download engine for supported streaming sites.<br />
  Pass one or more video URLs; the core resolves streams, downloads segments, and writes MP4 files to disk.
</p>

<p align="center">
  <a href="https://github.com/Alos21750/UAV-Downloader/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/Alos21750/UAV-Downloader?style=flat-square&label=release&color=ff5263" /></a>
  <a href="https://github.com/Alos21750/UAV-Downloader"><img alt="GitHub stars" src="https://img.shields.io/github/stars/Alos21750/UAV-Downloader?style=flat-square&logo=github&color=f5b942" /></a>
  <a href="./LICENSE"><img alt="Apache 2.0 license" src="https://img.shields.io/github/license/Alos21750/UAV-Downloader?style=flat-square" /></a>
</p>

## Supported sites

| Site | CLI / library download |
|---|:---:|
| JableTV | ✓ |
| MissAV | ✓ |
| SupJav | ✓ |
| Hanime1 | ✓ |
| Jav.guru | ✓ |

Additional legacy URL adapters remain registered for compatibility. Sites and CDNs can change without notice; if one stops working, update to the latest version and open an Issue with a reproducible URL.

**Hanime1** covers official `watch?v=` URLs plus signed MP4 resolution with quality preference, ranged connections, resume, and serial fallback.

**Jav.guru** resolves multi-server STREAM embeds (SB, TV, VO, LU, DD, JK, and related mirrors) with automatic fallback when one host fails.

## Quick start

Requires **Python 3.10+**.

```bash
git clone https://github.com/Alos21750/UAV-Downloader.git
cd UAV-Downloader
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python -m pip install -e .

# One URL
DOWNLOAD_DIR=./download uav-downloader-cli "https://jable.tv/videos/example/"

# Multiple URLs
DOWNLOAD_DIR=./download uav-downloader-cli \
  "https://jable.tv/videos/a/" \
  "https://supjav.com/123456.html"
```

Installed console entry points:

| Command | Purpose |
|---|---|
| `uav-downloader-cli` | Headless batch downloader (primary) |
| `uav-downloader` / `uav` | Same entry point as `uav-downloader-cli` |

## URL input

URLs are collected in this order:

1. Command-line arguments
2. `URLS` or `URL` environment variable (space- or comma-separated)
3. A text file (`URLS_FILE`, default `<DOWNLOAD_DIR>/urls.txt`, one URL per line, `#` comments allowed)

If no URL is found, the CLI exits with a usage message.

## Environment variables

| Variable | Purpose |
|---|---|
| `DOWNLOAD_DIR` | Output directory (default `/downloads`; use a writable path on local machines) |
| `RESOLUTION` | `highest`, `1080`, `720`, `480`, `360`, or `lowest` |
| `MAX_WORKERS_PER_VIDEO` | Segment workers per video, `1`–`16`; lower values reduce load on proxies or slow links |
| `URL` / `URLS` | One or more URLs |
| `URLS_FILE` | URL list file; defaults to `<DOWNLOAD_DIR>/urls.txt` |

MissAV automatically caps per-video and total workers when downloading; SupJav and Hanime1 direct downloads use at most four ranged connections.

## Library use

The same engine powers the CLI:

```python
from uav_downloader import sites

site = sites.CreateSite("https://jable.tv/videos/example/", "/path/to/output")
if site and site.is_url_vaildate():
    site.start_download()
```

`sites.validate_url(url)` returns the matching site class without starting a download.

## Troubleshooting

When opening a [GitHub Issue](https://github.com/Alos21750/UAV-Downloader/issues/new), include:

- Version, Python version, and operating system
- Site and reproducible URL, plus expected and actual behavior
- For crashes, attach `crash_log.txt` or `crash_native.log` if present
- Do not upload cookies, proxy credentials, tokens, or other private values

## License and responsible use

Code is licensed under the [Apache License 2.0](./LICENSE). Use this tool only for lawful personal or research purposes. Follow local law, site terms, and content rights, and download only material you are authorized to access.

See [Releases](https://github.com/Alos21750/UAV-Downloader/releases) for version notes.

<p align="center">Built and maintained by <a href="https://github.com/Alos21750">ALOS</a>.</p>
