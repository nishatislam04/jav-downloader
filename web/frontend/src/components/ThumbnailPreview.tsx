import { createEffect, createSignal, onCleanup, Show } from 'solid-js';

type Props = {
  src: string;
  alt?: string;
};

const MIN_SCALE = 1;
const MAX_SCALE = 4;
const ZOOM_STEP = 0.25;

function clampScale(value: number): number {
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, value));
}

export default function ThumbnailPreview(props: Props) {
  const [open, setOpen] = createSignal(false);
  const [scale, setScale] = createSignal(1);
  const [pan, setPan] = createSignal({ x: 0, y: 0 });
  const [dragging, setDragging] = createSignal(false);

  let dragStart = { x: 0, y: 0 };
  let panStart = { x: 0, y: 0 };

  function resetView() {
    setScale(1);
    setPan({ x: 0, y: 0 });
  }

  function openPreview() {
    resetView();
    setOpen(true);
  }

  function closePreview() {
    setOpen(false);
    resetView();
  }

  function zoomBy(delta: number) {
    setScale((current) => {
      const next = clampScale(Number((current + delta).toFixed(2)));
      if (next <= MIN_SCALE) {
        setPan({ x: 0, y: 0 });
      }
      return next;
    });
  }

  function zoomToFit() {
    resetView();
  }

  function onWheel(event: WheelEvent) {
    event.preventDefault();
    zoomBy(event.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP);
  }

  function onPointerDown(event: PointerEvent) {
    if (scale() <= MIN_SCALE) return;
    setDragging(true);
    dragStart = { x: event.clientX, y: event.clientY };
    panStart = pan();
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  }

  function onPointerMove(event: PointerEvent) {
    if (!dragging()) return;
    setPan({
      x: panStart.x + event.clientX - dragStart.x,
      y: panStart.y + event.clientY - dragStart.y,
    });
  }

  function onPointerUp(event: PointerEvent) {
    setDragging(false);
    try {
      (event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId);
    } catch {
      /* ignore */
    }
  }

  function onKeyDown(event: KeyboardEvent) {
    if (!open()) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      closePreview();
      return;
    }
    if (event.key === '+' || event.key === '=') {
      event.preventDefault();
      zoomBy(ZOOM_STEP);
      return;
    }
    if (event.key === '-' || event.key === '_') {
      event.preventDefault();
      zoomBy(-ZOOM_STEP);
      return;
    }
    if (event.key === '0' || event.key === 'f' || event.key === 'F') {
      event.preventDefault();
      zoomToFit();
    }
  }

  createEffect(() => {
    if (!open()) return;
    document.body.style.overflow = 'hidden';
    onCleanup(() => {
      document.body.style.overflow = '';
    });
  });

  createEffect(() => {
    if (!open()) return;
    window.addEventListener('keydown', onKeyDown);
    onCleanup(() => window.removeEventListener('keydown', onKeyDown));
  });

  return (
    <>
      <button
        type="button"
        class="thumb-preview-trigger"
        aria-label="Open thumbnail preview"
        onClick={openPreview}
      >
        <img src={props.src} alt={props.alt || ''} class="thumb" loading="lazy" />
      </button>

      <Show when={open()}>
        <div
          class="thumb-lightbox"
          role="dialog"
          aria-modal="true"
          aria-label="Thumbnail preview"
          onClick={(event) => {
            if (event.target === event.currentTarget) closePreview();
          }}
        >
          <div class="thumb-lightbox-toolbar">
            <button
              type="button"
              class="thumb-lightbox-btn"
              aria-label="Zoom out"
              onClick={() => zoomBy(-ZOOM_STEP)}
            >
              −
            </button>
            <span class="thumb-lightbox-zoom">{Math.round(scale() * 100)}%</span>
            <button
              type="button"
              class="thumb-lightbox-btn"
              aria-label="Zoom in"
              onClick={() => zoomBy(ZOOM_STEP)}
            >
              +
            </button>
            <button
              type="button"
              class="thumb-lightbox-btn"
              aria-label="Fit to screen"
              onClick={zoomToFit}
            >
              Fit
            </button>
            <button
              type="button"
              class="thumb-lightbox-btn thumb-lightbox-close"
              aria-label="Close preview"
              onClick={closePreview}
            >
              ×
            </button>
          </div>

          <div class="thumb-lightbox-viewport" onWheel={onWheel}>
            <img
              src={props.src}
              alt={props.alt || ''}
              class="thumb-lightbox-image"
              classList={{ dragging: dragging() }}
              style={{
                transform: `translate(${pan().x}px, ${pan().y}px) scale(${scale()})`,
              }}
              onDblClick={() => {
                if (scale() > MIN_SCALE) zoomToFit();
                else setScale(2);
              }}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerCancel={onPointerUp}
              onClick={(event) => event.stopPropagation()}
            />
          </div>

          <p class="thumb-lightbox-hint">Esc close · scroll zoom · drag when zoomed · double-click toggle</p>
        </div>
      </Show>
    </>
  );
}

export function thumbnailSrc(url: string): string {
  if (!url) return '';
  if (url.startsWith('/')) return url;
  return `/api/thumbnail?url=${encodeURIComponent(url)}`;
}
