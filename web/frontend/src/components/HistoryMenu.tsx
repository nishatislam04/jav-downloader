import { createEffect, createSignal, For, onCleanup, Show } from 'solid-js';
import {
  cropHistoryTitle,
  formatHistoryWhen,
  loadHistory,
  type HistoryEntry,
} from '../lib/history';
import { thumbnailSrc } from './ThumbnailPreview';

type Props = {
  onSelect: (entry: HistoryEntry) => void;
};

export default function HistoryMenu(props: Props) {
  const [open, setOpen] = createSignal(false);
  const [entries, setEntries] = createSignal<HistoryEntry[]>(loadHistory());

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
    const root = document.getElementById('history-menu-root');
    if (root && target && !root.contains(target)) {
      close();
    }
  }

  createEffect(() => {
    if (!open()) return;
    document.addEventListener('click', onDocClick);
    onCleanup(() => document.removeEventListener('click', onDocClick));
  });

  return (
    <div id="history-menu-root" class="history-menu">
      <button type="button" class="history-menu-btn" onClick={toggle}>
        History
      </button>
      <Show when={open()}>
        <div class="history-dropdown" role="menu">
          <Show
            when={entries().length}
            fallback={<p class="history-empty">No downloads yet</p>}
          >
            <For each={entries()}>
              {(entry) => (
                <button
                  type="button"
                  class="history-item"
                  role="menuitem"
                  onClick={() => {
                    props.onSelect(entry);
                    close();
                  }}
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
                    <span class="history-item-title">
                      {cropHistoryTitle(entry.title)}
                    </span>
                    <span class="history-item-when">
                      {formatHistoryWhen(entry.downloadedAt)}
                    </span>
                  </span>
                </button>
              )}
            </For>
          </Show>
        </div>
      </Show>
    </div>
  );
}
