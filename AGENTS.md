# JAV Downloader — Agent Instructions

Shared project instructions for **Zed Agent** (freebuff2api / GLM 5.3 Flash) and **Cursor via ACP** in Zed.

## Agent setup in this repo

| Agent | How it runs | What it reads |
|-------|-------------|---------------|
| **Zed Agent** | Native panel, freebuff2api → GLM 5.3 Flash | This file (`AGENTS.md`) |
| **Cursor (ACP)** | External agent inside Zed | This file + `.cursor/rules/*.mdc` (file-scoped) |
| **Skills** | On-demand (`/skill-name` in Zed) | `.agents/skills/*/SKILL.md` |

Project `AGENTS.md` overrides personal `~/.config/zed/AGENTS.md` on conflicts.
Cursor ACP may also load `.cursorrules` / `.rules` if present — prefer this file as source of truth.

**GLM 5.3 Flash note:** Keep instructions concrete and file-specific. One task per turn when possible. Prefer small, verifiable diffs; read the target module before editing. For multi-file work, list touched paths up front.

## File editing (MCP / agent tools)

`write_file` is disabled — do not attempt it on existing files.

- **Existing files:** use `edit_file` only, with `oldText` ≤10 lines (exact match including whitespace). One hunk per edit call.
- **Alternative:** StrReplace-style single hunk — one search/replace, minimal surrounding context.
- **New files only:** creating a file from scratch is fine; never rewrite a whole existing file in one shot.
- **If an edit would reformat or touch unrelated lines:** stop — narrow the hunk, do not commit a broad rewrite.
- **Do not `git checkout` to undo** unless the working tree is actually broken; fix forward with a smaller edit instead.

### Multi-file site edits (`sites/*.py`)

One file → one hunk → show diff (`git diff -- path`) → next file. Never batch-edit multiple site files in a single tool call.

---

## What this is

Headless Python 3.10+ download engine + SolidJS web UI.
Resolves HLS or direct MP4 from supported sites → downloads segments → optional ffmpeg post-process → MP4 on disk.

Supported featured sites: JableTV, MissAV, SupJav, Hanime1, Jav.guru, SpankBang (+ legacy URL-only adapters).

---

## Architecture (where code goes)

| Area | Path | Responsibility |
|------|------|----------------|
| Site adapters | `src/jav_downloader/sites/` | URL validation, page parsing, stream resolve |
| Shared infra | `src/jav_downloader/core/` | config, SSL, paths, video identity, migrations |
| Encoding pipeline | `sites/media_*.py`, `encoding_*.py` | ffprobe → decide → strategy → ffmpeg |
| Web API | `src/jav_downloader/web/` | HTTP server, jobs, progress, cleanup |
| Frontend source | `web/frontend/` | Vite + SolidJS |
| Frontend shipped | `src/jav_downloader/web/static/` | **Committed** production bundle (Termux has no Node) |
| Tests | `tests/` | pytest, mock fixtures preferred |
| Docs | `docs/` | encoding architecture, benchmarks, roadmaps |

Deep encoding map: `docs/encoding-architecture.md`.

---

## Dev commands

```bash
make install          # venv + editable install
make test             # full pytest suite
make start            # build UI if needed + serve :8765
make web-api          # API only on :8765
make web-dev          # Vite HMR :5173 (run web-api first)
make web-build        # rebuild frontend → web/static/
make web-format       # Biome format (frontend)
make web-lint         # Biome lint (frontend)
```

Python entry point: `jav-web` (web UI + API server).

---

## Hard constraints (never violate)

- Site-specific parsing stays in `sites/` — not `core/` or `web/`
- Preserve legacy public API typos: `CreateSite`, `is_url_vaildate`, `VaildateUrl` (`# noqa` retained)
- Preserve state migration unless an explicit major-version break is requested
- Never commit: cookies, proxy credentials, API keys, downloaded videos, PII logs, model packs
- Windows exe releases: GitHub Actions CI only — never attach local builds to releases
- Frontend static bundle is committed for Termux — runtime must not require Node/npm
- Do not create git commits or PRs unless explicitly asked
- Do not write markdown docs unless explicitly asked

---

## Platform awareness

- **Termux:** `TERMUX_VERSION`, bind `0.0.0.0`, default downloads to `~/storage/downloads`, x264 preset default `veryfast`
- **Windows:** `CREATE_NO_WINDOW` for subprocesses; filename sanitization in `base.py` matters
- **ffmpeg lifecycle:** active PIDs on `site._ffmpeg_proc` — must be killed on cancel/pause via `_stop_workers()`

---

## Encoding pipeline (current)

Download complete → optional `post_process_media()`:

```text
ffprobe (media_probe) → decide_encoding (encoding_decision) → strategy (encoding_strategies) → ffmpeg
```

Modes: `skip` | `direct_remux` | `software_encode` | hardware (MediaCodec / NVENC / QSV / VAAPI / VideoToolbox).

Capability probe + hardware→software fallback in `encoding_capabilities.py`.
Web exposes `GET /api/encoding/capabilities`. Encode options are web/API-first.

---

## Site adapters

- New **featured** site: class in `sites/<name>.py`, register in `FEATURED_SITE_CLASSES` (`sites/__init__.py`)
- **Legacy-only** adapters: `sites/legacy/` — do not pollute featured list
- HLS sites extend `M3U8Crawler` (`base.py`); direct MP4 follow `direct_mp4.py`; multi-server mirrors like `javguru.py`
- Must implement: `validate_url()`, `is_url_vaildate()` (keep typo), download entry
- Worker caps: MissAV auto-caps workers; SupJav/Hanime1 max 4 ranged connections
- Site CDNs break often — use fixture-based parser tests, not live URLs in CI

---

## Web + frontend

- **Backend:** `server.py` HTTP only; business logic in `service.py`, `jobs.py`, `job_store.py`
- Encode options: API JSON → `_encode_options_from_mapping()` → `site._encode_*` via `apply_encode_options()`
- **Frontend:** SolidJS (not React). Biome for lint/format. API in `api.ts`. Settings in `lib/persist.ts`
- Encode UI: `EditToolsCard.tsx` — advanced encoding section is opt-in
- **After any UI change:** `make web-build` → commit `src/jav_downloader/web/static/`
- Never edit bundled JS/CSS in `web/static/` by hand

---

## Tests

- Run: `make test` or `.venv/bin/python -m pytest tests -q`
- Mock over live: HTML fixtures, ffprobe JSON, `DummySite` objects (see `test_encoding_decision.py`)
- Naming: `test_<site>.py`, `test_encoding_*.py`, `test_web*.py`
- Bug fix or crawler change = regression test required
- No real network, ffmpeg encode, or downloaded segments in unit tests

---

## When adding features

1. Read the existing module — extend, do not parallel-implement
2. Minimal diff — no drive-by refactors
3. Add regression tests with mocks
4. UI change → rebuild static → commit bundle
5. Site change → update README supported-sites table if user-facing

---

## Active development (update as work progresses)

- More site adapters incoming — follow featured site pattern + tests
- Encoding pipeline mature (phases 1–10 done) — changes need decision/strategy/capability sync
- `docs/android-root-performance-optimization.md` is roadmap-only, not implemented

---

## Do / Don't

| Do | Don't |
|----|-------|
| Extend existing modules | Create parallel `*_v2.py` helpers |
| Mock fixtures in tests | Hit live site URLs in CI |
| `make web-build` after UI edits | Edit `web/static/` by hand |
| Keep legacy API names | "Fix" `is_url_vaildate` typo |
| Check Termux + Windows impact | Assume desktop-only |
| Kill ffmpeg on cancel | Orphan subprocesses |
| Read encoding-architecture.md before encoding work | Invent a new pipeline |
| Small focused diffs (good for GLM 5.3 Flash) | Large unsolicited refactors |
| `edit_file` with ≤10-line `oldText` hunks | Full-file rewrite or reformat |
| One site file per edit + diff before next | Multi-file edits in one call |
| Fix forward with a smaller hunk | `git checkout` loop to undo every miss |

---

## On-demand skills

| Skill | Use when |
|-------|----------|
| `/add-site-adapter` | Adding a new supported site |
| `/frontend-build-static` | Any frontend change needing static commit |

See `.agents/skills/*/SKILL.md`.
