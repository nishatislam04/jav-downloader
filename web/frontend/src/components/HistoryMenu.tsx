import { createEffect, createMemo, createSignal, For, onCleanup, Show } from "solid-js";
import {
  clearHistoryOnServer,
  cropHistoryTitle,
  deleteHistoryOnServer,
  formatHistoryWhen,
  groupHistoryEntries,
  type HistoryEntry,
  type HistoryGroup,
  HISTORY_PAGE_SIZE,
  historyStatusLabel,
  loadHistoryFromServer,
} from "../lib/history";
import ConfirmDialog from "./ConfirmDialog";
import { CloseIcon, HistoryIcon, TrashIcon } from "./IconButton";
import { thumbnailSrc } from "./ThumbnailPreview";

type Props = {
  onSelect: (entry: HistoryEntry) => void;
  refreshKey?: number;
  groupByUrl: boolean;
  onGroupByUrlChange: (value: boolean) => void;
};

type PendingDelete = { type: "entry"; id: string } | { type: "all" };

export default function HistoryMenu(props: Props) {
  const [open, setOpen] = createSignal(false);
  const [entries, setEntries] = createSignal<HistoryEntry[]>([]);
  const [total, setTotal] = createSignal(0);
  const [hasMore, setHasMore] = createSignal(false);
  const [loading, setLoading] = createSignal(false);
  const [loadingMore, setLoadingMore] = createSignal(false);
  const [expandedUrls, setExpandedUrls] = createSignal<Set<string>>(new Set());
  const [pending, setPending] = createSignal<PendingDelete | null>(null);
  const [pendingLoad, setPendingLoad] = createSignal<HistoryEntry | null>(null);

  let drawerBody: HTMLDivElement | undefined;
  let scrollIdleTimer: ReturnType<typeof setTimeout> | undefined;
  let silentInFlight = false;
  let refreshQueued = false;
  let groupCache = new Map<string, HistoryGroup>();

  function entryFieldsMatch(a: HistoryEntry, b: HistoryEntry): boolean {
    return (
      a.url === b.url &&
      a.title === b.title &&
      a.thumbnail === b.thumbnail &&
      a.status === b.status &&
      a.downloadedAt === b.downloadedAt &&
      a.updatedAt === b.updatedAt
    );
  }

  function mergeSilentUpdate(
    current: HistoryEntry[],
    fresh: HistoryEntry[],
  ): HistoryEntry[] | null {
    const freshIds = new Set(fresh.map((entry) => entry.id));
    const byId = new Map(current.map((entry) => [entry.id, entry]));
    const head = fresh.map((entry) => {
      const prev = byId.get(entry.id);
      if (prev && entryFieldsMatch(prev, entry)) return prev;
      return prev ? { ...prev, ...entry } : entry;
    });
    const tail = current.filter((entry) => !freshIds.has(entry.id));
    const merged = [...head, ...tail];
    if (merged.length === current.length && merged.every((entry, index) => entry === current[index])) {
      return null;
    }
    return merged;
  }

  function stableGroupHistory(list: HistoryEntry[]) {
    const raw = groupHistoryEntries(list);
    const nextCache = new Map<string, (typeof raw)[number]>();
    const out = raw.map((group) => {
      const prev = groupCache.get(group.url);
      if (
        prev &&
        prev.latest === group.latest &&
        prev.count === group.count &&
        prev.runs.length === group.runs.length &&
        prev.runs.every((run, index) => run === group.runs[index])
      ) {
        nextCache.set(group.url, prev);
        return prev;
      }
      nextCache.set(group.url, group);
      return group;
    });
    groupCache = nextCache;
    return out;
  }

  const groupedList = createMemo(() => stableGroupHistory(entries()));

  function hasInProgressEntries(list: HistoryEntry[]): boolean {
    return list.some((entry) => {
      const status = (entry.status || "").toLowerCase();
      return status === "downloading" || status === "pending" || status === "paused";
    });
  }

  function onDrawerScroll() {
    refreshQueued = true;
    if (scrollIdleTimer) clearTimeout(scrollIdleTimer);
    scrollIdleTimer = setTimeout(() => {
      scrollIdleTimer = undefined;
      if (refreshQueued && open()) {
        refreshQueued = false;
        void refreshSilent();
      }
    }, 450);
  }

  async function refreshInitial() {
    setLoading(true);
    try {
      const page = await loadHistoryFromServer(0, HISTORY_PAGE_SIZE);
      setTotal(page.total);
      setHasMore(page.hasMore);
      setEntries(page.entries);
    } finally {
      setLoading(false);
    }
  }

  async function refreshSilent() {
    if (scrollIdleTimer !== undefined) {
      refreshQueued = true;
      return;
    }
    if (silentInFlight) {
      refreshQueued = true;
      return;
    }
    silentInFlight = true;
    try {
      const current = entries();
      const limit = Math.max(current.length, HISTORY_PAGE_SIZE);
      const page = await loadHistoryFromServer(0, limit);
      if (scrollIdleTimer !== undefined) {
        refreshQueued = true;
        return;
      }
      const merged = mergeSilentUpdate(current, page.entries);
      if (page.total !== total()) setTotal(page.total);
      const loaded = merged ?? current;
      setHasMore(loaded.length < page.total);
      if (merged) setEntries(merged);
    } finally {
      silentInFlight = false;
      if (refreshQueued && scrollIdleTimer === undefined) {
        refreshQueued = false;
        void refreshSilent();
      }
    }
  }

  async function refreshAppend() {
    setLoadingMore(true);
    try {
      const offset = entries().length;
      const page = await loadHistoryFromServer(offset, HISTORY_PAGE_SIZE);
      setTotal(page.total);
      setHasMore(page.hasMore);
      setEntries([...entries(), ...page.entries]);
    } finally {
      setLoadingMore(false);
    }
  }

  function toggle() {
    const next = !open();
    setOpen(next);
    if (!next) return;
    if (entries().length === 0) void refreshInitial();
    else void refreshSilent();
  }

  function close() {
    setOpen(false);
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
    if (event.key === "Escape" && !pendingLoad()) {
      event.preventDefault();
      close();
    }
  }

  createEffect(() => {
    if (!open()) return;
    document.addEventListener("click", onDocClick);
    document.addEventListener("keydown", onDocKeyDown);
    const timer = window.setInterval(() => {
      if (!hasInProgressEntries(entries())) return;
      void refreshSilent();
    }, 8000);
    onCleanup(() => {
      document.removeEventListener("click", onDocClick);
      document.removeEventListener("keydown", onDocKeyDown);
      if (scrollIdleTimer) clearTimeout(scrollIdleTimer);
      scrollIdleTimer = undefined;
      refreshQueued = false;
      window.clearInterval(timer);
    });
  });

  createEffect(() => {
    props.refreshKey;
    if (open()) void refreshSilent();
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

  function confirmLoad() {
    const entry = pendingLoad();
    setPendingLoad(null);
    if (!entry) return;
    props.onSelect(entry);
    close();
  }

  function moreRunsLabel(count: number): string {
    const extra = count - 1;
    if (extra <= 0) return "";
    return extra === 1 ? "1 more run" : `${extra} more runs`;
  }

  function renderEntry(entry: HistoryEntry, nested = false) {
    return (
      <div class="history-item" classList={{ "history-item-nested": nested }}>
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
          <div class="history-view-switch" role="group" aria-label="History layout">
            <button
              type="button"
              class="history-view-switch-btn"
              classList={{ active: props.groupByUrl }}
              aria-pressed={props.groupByUrl}
              onClick={() => props.onGroupByUrlChange(true)}
            >
              By URL
            </button>
            <button
              type="button"
              class="history-view-switch-btn"
              classList={{ active: !props.groupByUrl }}
              aria-pressed={!props.groupByUrl}
              onClick={() => props.onGroupByUrlChange(false)}
            >
              Timeline
            </button>
          </div>
          <div class="history-drawer-body" ref={drawerBody} onScroll={onDrawerScroll}>
            <Show
              when={entries().length > 0 || !loading()}
              fallback={<p class="history-empty">Loading…</p>}
            >
              <Show when={entries().length} fallback={<p class="history-empty">No downloads yet</p>}>
                <Show when={!props.groupByUrl}>
                  <For each={entries()}>{(entry) => renderEntry(entry)}</For>
                </Show>
                <Show when={props.groupByUrl}>
                  <For each={groupedList()}>
                    {(group) => (
                      <div class="history-group">
                        <Show when={group.count > 1}>
                          <button
                            type="button"
                            class="history-group-expand"
                            aria-expanded={expandedUrls().has(group.url)}
                            onClick={() => toggleGroupExpand(group.url)}
                          >
                            {moreRunsLabel(group.count)}
                          </button>
                        </Show>
                        {renderEntry(group.latest)}
                        <Show when={expandedUrls().has(group.url) && group.count > 1}>
                          <div class="history-nested-runs">
                            <For each={group.runs.slice(1)}>
                              {(entry) => renderEntry(entry, true)}
                            </For>
                          </div>
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
                    onClick={() => void refreshAppend()}
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
            onConfirm={() => void confirmPending()}
            onCancel={cancelPending}
          />
        )}
      </Show>
    </div>
  );
}
