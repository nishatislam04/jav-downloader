---
name: add-site-adapter
description: Add a new supported site adapter with registry entry and regression tests
disable-model-invocation: false
---

# Add Site Adapter

Use when adding download support for a new streaming site.

## Checklist

1. **Pick template** by download type:
   - HLS segments → `jabletv.py` / `missav.py`
   - Direct progressive MP4 → `spankbang.py` / `hanime1.py`
   - Multi-server embed fallback → `javguru.py`

2. **Create** `src/jav_downloader/sites/<name>.py`:
   - `validate_url(url)` classmethod
   - `is_url_vaildate()` instance method (**keep typo**)
   - Resolve + download logic

3. **Register** in `sites/__init__.py`:
   - Featured → `FEATURED_SITE_CLASSES`
   - Legacy URL-only → `LEGACY_URL_ONLY_SITE_CLASSES` under `sites/legacy/`

4. **Tests** — `tests/test_<name>.py`:
   - Mock HTML fixtures (save real page structure, strip cookies/tokens)
   - Assert `validate_url`, stream URL extraction, edge cases
   - No live HTTP

5. **Docs** — update README supported-sites table if user-facing featured site

6. **Verify** — `make test`

## Do not

- Put site parsing in `core/` or `web/`
- Add to featured list without tests
- Hardcode credentials or user cookies
- Hit live URLs in pytest
