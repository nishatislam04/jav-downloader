# JAV Downloader Web UI

Vite + SolidJS frontend. Built assets land in `src/jav_downloader/web/static/` for the Python server.

## Commands

```bash
npm install      # or: make install-web
npm run dev      # :5173, proxies /api → :8765 (run make web-api first)
npm run build    # or: make web-build
```

## Layout

```
src/
  App.tsx              main page
  api.ts               fetch wrappers
  components/          UI pieces (expand editor here)
  lib/format.ts        bytes/speed/progress helpers
  styles/app.css       global styles
```
