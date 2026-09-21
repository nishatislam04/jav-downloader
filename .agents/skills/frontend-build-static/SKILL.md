---
name: frontend-build-static
description: Rebuild SolidJS frontend and commit static assets for Termux
disable-model-invocation: false
---

# Frontend Build → Static Commit

Use after any change under `web/frontend/`.

## Why

Termux/Android installs have **no Node.js**. Production serves pre-built assets from `src/jav_downloader/web/static/`. Uncommitted static = broken UI on phone.

## Steps

```bash
# 1. Lint/format (optional but recommended)
make web-format
make web-lint

# 2. Build
make web-build

# 3. Verify output exists
ls src/jav_downloader/web/static/index.html

# 4. Stage static + source together
git add web/frontend/ src/jav_downloader/web/static/
```

## Dev workflow (laptop only)

Terminal 1: `make web-api` (Python :8765)
Terminal 2: `make web-dev` (Vite :5173, proxies `/api`)

## Do not

- Edit `src/jav_downloader/web/static/assets/*` by hand
- Skip build when changing `.tsx`, `.ts`, or `app.css`
- Use React patterns — this is SolidJS
