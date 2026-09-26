import { createEffect, createSignal, For, onCleanup, Show } from "solid-js";
import {
  clearHistoryOnServer,
  deleteHistoryOnServer,
  formatHistoryWhen,
  groupHistoryEntries,
  type HistoryEntry,
  HISTORY_PAGE_SIZE,
  historyStatusLabel,
  loadHistoryFromServer,
} from "../lib/history";
import ConfirmDialog from "./ConfirmDialog";
import HistoryDetailDialog from "./HistoryDetailDialog";
import { CloseIcon, HistoryIcon, TrashIcon } from "./IconButton";
import { thumbnailSrc } from "./ThumbnailPreview";

type Props = {
  onSelect: (entry: HistoryEntry) => void;
  refreshKey?: number;
};

type PendingDelete = { type: "entry"; id: string } | { type: "all" };

export default function HistoryMenu(props: Props) {
  const [open, setOpen] = createSignal(false);
  const [entries, setEntries] = createSignal<HistoryEntry[]>([]);
  const [total, setTotal] = createSignal(0);
  const [hasMore, setHasMore] = createSignal(false);
  const [loading, setLoading] = createSignal(false);
  const [loadingMore, setLoadingMore] = createSignal(false);
  const [groupByUrl, setGroupByUrl] = createSignal(false);
  const [expandedUrls, setExpandedUrls] = createSignal<Set<string>>(new Set());
  const [pending, setPending] = createSignal<PendingDelete | null>(null);
  const [detailId, setDetailId] = createSignal<string | null>(null);

  async function refresh(append = false) {
    const offset = append ? entries().length : 0;
    if (append) setLoadingMore(true);
    else setLoading(true);
    try {
      const page = await loadHistoryFromServer(offset, HISTORY_PAGE_SIZE);
      setTotal(page.total);
      setHasMore(page.hasMore);
      setEntries(append ? [...entries(), ...page.entries] : page.entries);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }

  function toggle() {
    void refresh(false);
    setOpen((value) => !value);
  }

  function close() {
    setOpen(false);
    setDetailId(null);
  }

  function toggleGroupExpand(url: string) {
    setExpandedUrls((prev) => {
      const next = new Set(prev);
      if (next.has(url)) next.delete(url);
      else next.add(url);
      return next;
    });
  }

  function onDocClick(event: MouseEvent) {
    const target = event.target as Node | null;
    if (!target?.isConnected) return;
    const root = document.getElementById("history-menu-root");
    if (root && !root.contains(target)) {
      close();
    }
  }

  function onDocKeyDown(event: KeyboardEvent) {
    if (event.key === "Escape" && !detailId()) {
      event.preventDefault();
      close();
    }
  }

  createEffect(() => {
    if (!open()) return;
    document.addEventListener("click", onDocClick);
    document.addEventListener("keydown", onDocKeyDown);
    const timer = window.setInterval(() => {
      void refresh(false);
    }, 5000);
    onCleanup(() => {
      document.removeEventListener("click", onDocClick);
      document.removeEventListener("keydown", onDocKeyDown);
      window.clearInterval(timer);
    });
  });

  createEffect(() => {
    props.refreshKey;
    if (open()) void refresh(false);
  });

  function removeEntry(id: string) {
    setPending({ type: "entry", id });
  }

  function onClearAll() {
    setPending({ type: "all" });
  }

  async function confirmPending() {
    const action = pending();
    if (!action) return;
    if (action.type === "entry") {
      const page = await deleteHistoryOnServer(action.id);
      setEntries(page.entries);
      setTotal(page.total);
      setHasMore(page.hasMore);
    } else {
      const page = await clearHistoryOnServer();
      setEntries(page.entries);
      setTotal(page.total);
      setHasMore(page.hasMore);
    }
    setPending(null);
  }

  function cancelPending() {
    setPending(null);
  }

  function renderEntry(entry: HistoryEntry, nested = false) {
    return (
      <div class="history-item" classList={{ "history-item-nested": nested }}>
        <button
          type="button"
          class="history-item-main"
          role="menuitem"
          onClick={() => setDetailId(entry.id)}
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
            <span class="history-item-title">{entry.title.trim() || "Untitled"}</span>
            <span class="history-item-when">
              {formatHistoryWhen(entry.downloadedAt)}
              <Show when={historyStatusLabel(entry.status)}>
                {(label) => <> · {label()}</>}
              </Show>
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
    );
  }

  const flatList = () => entries();
  const groupedList = () => groupHistoryEntries(entries());

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
              class="history-group-toggle"
              classList={{ active: groupByUrl() }}
              aria-pressed={groupByUrl()}
              title="Group by URL"
              onClick={() => setGroupByUrl((v) => !v)}
            >
              Group
            </button>
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
            <Show when={!loading()} fallback={<p class="history-empty">Loading…</p>}>
              <Show when={entries().length} fallback={<p class="history-empty">No downloads yet</p>}>
                <Show when={!groupByUrl()}>
                  <For each={flatList()}>{(entry) => renderEntry(entry)}</For>
                </Show>
                <Show when={groupByUrl()}>
                  <For each={groupedList()}>
                    {(group) => (
                      <div class="history-group">
                        <div class="history-group-head">
                          {renderEntry(group.latest)}
                          <Show when={group.count > 1}>
                            <button
                              type="button"
                              class="history-group-badge"
                              onClick={() => toggleGroupExpand(group.url)}
                            >
                              {group.count} runs
                              {expandedUrls().has(group.url) ? " ▾" : " ▸"}
                            </button>
                          </Show>
                        </div>
                        <Show when={expandedUrls().has(group.url) && group.count > 1}>
                          <For each={group.runs.slice(1)}>
                            {(entry) => renderEntry(entry, true)}
                          </For>
                        </Show>
                      </div>
                    )}
                  </For>
                </Show>
                <Show when={hasMore()}>
                  <button
                    type="button"
                    class="history-load-more"
                    disabled={loadingMore()}
                    onClick={() => void refresh(true)}
                  >
                    {loadingMore() ? "Loading…" : `Load more (${entries().length}/${total()})`}
                  </button>
                </Show>
              </Show>
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
      <Show when={detailId()}>
        {(id) => (
          <HistoryDetailDialog
            recordId={id()}
            onClose={() => setDetailId(null)}
            onLoadUrl={(url) => props.onSelect({ id: id(), url, title: "", thumbnail: "", downloadedAt: 0 })}
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
            onConfirm={() => void confirmPending()}
            onCancel={cancelPending}
          />
        )}
      </Show>
    </div>
  );
}
