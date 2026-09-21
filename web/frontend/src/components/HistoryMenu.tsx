import { createEffect, createSignal, For, onCleanup, Show } from "solid-js";
import {
  clearHistory,
  cropHistoryTitle,
  deleteHistory,
  formatHistoryWhen,
  type HistoryEntry,
  loadHistory,
} from "../lib/history";
import ConfirmDialog from "./ConfirmDialog";
import { CloseIcon, HistoryIcon, TrashIcon } from "./IconButton";
import { thumbnailSrc } from "./ThumbnailPreview";

type Props = {
  onSelect: (entry: HistoryEntry) => void;
};

type PendingDelete = { type: "entry"; id: string } | { type: "all" };

export default function HistoryMenu(props: Props) {
  const [open, setOpen] = createSignal(false);
  const [entries, setEntries] = createSignal<HistoryEntry[]>(loadHistory());
  const [pending, setPending] = createSignal<PendingDelete | null>(null);
  const [pendingLoad, setPendingLoad] = createSignal<HistoryEntry | null>(null);

  function refresh() {
    setEntries(loadHistory());
  }

  function toggle() {
    refresh();
    setOpen((value) => !value);
  }

  function close() {
    setOpen(false);
  }

  function onDocClick(event: MouseEvent) {
    const target = event.target as Node | null;
    const root = document.getElementById("history-menu-root");
    if (root && target && !root.contains(target)) {
      close();
    }
  }

  function onDocKeyDown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
    }
  }

  createEffect(() => {
    if (!open()) return;
    document.addEventListener("click", onDocClick);
    document.addEventListener("keydown", onDocKeyDown);
    onCleanup(() => {
      document.removeEventListener("click", onDocClick);
      document.removeEventListener("keydown", onDocKeyDown);
    });
  });

  function removeEntry(id: string) {
    setPending({ type: "entry", id });
  }

  function onClearAll() {
    setPending({ type: "all" });
  }

  function confirmPending() {
    const action = pending();
    if (!action) return;
    if (action.type === "entry") {
      setEntries(deleteHistory(action.id));
    } else {
      setEntries(clearHistory());
    }
    setPending(null);
    close();
  }

  function cancelPending() {
    setPending(null);
  }

  function confirmLoad() {
    const entry = pendingLoad();
    setPendingLoad(null);
    if (!entry) return;
    props.onSelect(entry);
    close();
  }

  return (
    <div id="history-menu-root" class="history-menu">
      <button
        type="button"
        class="history-menu-btn"
        classList={{ active: open() }}
        aria-label="History"
        aria-expanded={open()}
        title="History"
        onClick={toggle}
      >
        <HistoryIcon />
      </button>
      <Show when={open()}>
        <div class="drawer-backdrop" aria-hidden="true" onClick={close} />
        <div class="history-drawer" role="menu">
          <div class="history-drawer-head">
            <p class="history-drawer-title">History</p>
            <button
              type="button"
              class="history-drawer-close"
              aria-label="Close history"
              title="Close"
              onClick={close}
            >
              <CloseIcon />
            </button>
          </div>
          <div class="history-drawer-body">
            <Show when={entries().length} fallback={<p class="history-empty">No downloads yet</p>}>
              <For each={entries()}>
                {(entry) => (
                  <div class="history-item">
                    <button
                      type="button"
                      class="history-item-main"
                      role="menuitem"
                      onClick={() => setPendingLoad(entry)}
                    >
                      <Show when={entry.thumbnail}>
                        <img
                          src={thumbnailSrc(entry.thumbnail)}
                          alt=""
                          class="history-item-thumb"
                          loading="lazy"
                        />
                      </Show>
                      <span class="history-item-body">
                        <span class="history-item-title">{cropHistoryTitle(entry.title)}</span>
                        <span class="history-item-when">
                          {formatHistoryWhen(entry.downloadedAt)}
                        </span>
                      </span>
                    </button>
                    <button
                      type="button"
                      class="history-item-del"
                      aria-label="Delete entry"
                      title="Delete"
                      onClick={() => removeEntry(entry.id)}
                    >
                      <TrashIcon />
                    </button>
                  </div>
                )}
              </For>
            </Show>
          </div>
          <Show when={entries().length}>
            <div class="history-footer">
              <button type="button" class="history-clear-btn" onClick={onClearAll}>
                <TrashIcon />
                Clear all
              </button>
            </div>
          </Show>
        </div>
      </Show>
      <Show when={pendingLoad()}>
        {(entry) => (
          <ConfirmDialog
            title="Load this video?"
            message={`"${cropHistoryTitle(entry().title)}" will be filled into the URL field.`}
            confirmLabel="Load"
            onConfirm={confirmLoad}
            onCancel={() => setPendingLoad(null)}
          />
        )}
      </Show>
      <Show when={pending()}>
        {(action) => (
          <ConfirmDialog
            title={action().type === "all" ? "Clear all history?" : "Delete entry?"}
            message={
              action().type === "all"
                ? "All download entries will be removed."
                : "This download will be removed from your history."
            }
            confirmLabel="Delete"
            onConfirm={confirmPending}
            onCancel={cancelPending}
          />
        )}
      </Show>
    </div>
  );
}
