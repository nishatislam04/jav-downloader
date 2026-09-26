import { createEffect, createSignal, For, onCleanup, Show } from "solid-js";
import { fetchHistoryRecord, type HistoryRecord } from "../api";
import { cropHistoryTitle, formatHistoryWhen, historyStatusLabel } from "../lib/history";
import { classifyLogLine } from "../lib/loglevel";
import ConfirmDialog from "./ConfirmDialog";
import { CloseIcon } from "./IconButton";

type Props = {
  recordId: string;
  onClose: () => void;
  onLoadUrl: (url: string) => void;
};

export default function HistoryDetailDialog(props: Props) {
  const [record, setRecord] = createSignal<HistoryRecord | null>(null);
  const [loading, setLoading] = createSignal(true);
  const [error, setError] = createSignal("");
  const [confirmLoad, setConfirmLoad] = createSignal(false);

  async function load(silent = false) {
    if (!silent) setLoading(true);
    try {
      const data = await fetchHistoryRecord(props.recordId);
      if (!data.ok || !data.record) {
        setError(data.error || "Could not load record");
        setRecord(null);
        return;
      }
      setError("");
      setRecord(data.record);
    } finally {
      if (!silent) setLoading(false);
    }
  }

  createEffect(() => {
    props.recordId;
    void load(false);
    const timer = window.setInterval(() => {
      const current = record();
      const status = (current?.status || "").toLowerCase();
      if (status === "downloading" || status === "pending" || status === "paused") {
        void load(true);
      }
    }, 4000);
    onCleanup(() => window.clearInterval(timer));
  });

  return (
    <div
      class="history-detail-overlay"
      role="dialog"
      aria-modal="true"
      onClick={(event) => {
        if (event.target === event.currentTarget) props.onClose();
      }}
    >
      <div class="history-detail-panel">
        <div class="history-detail-head">
          <Show when={record()} fallback={<p class="history-detail-title">History</p>}>
            {(rec) => (
              <div class="history-detail-head-text">
                <p class="history-detail-title">{rec().title.trim() || "Untitled"}</p>
                <p class="history-detail-meta">
                  {formatHistoryWhen(rec().downloadedAt)}
                  <Show when={historyStatusLabel(rec().status)}>
                    {(label) => <> · {label()}</>}
                  </Show>
                </p>
              </div>
            )}
          </Show>
          <button
            type="button"
            class="history-drawer-close"
            aria-label="Close"
            onClick={props.onClose}
          >
            <CloseIcon />
          </button>
        </div>
        <Show when={loading() && !record()}>
          <p class="history-empty">Loading…</p>
        </Show>
        <Show when={error()}>
          <p class="history-empty">{error()}</p>
        </Show>
        <Show when={record()}>
          {(rec) => (
            <>
              <div class="history-detail-stats">
                <Show when={rec().progress_phase}>
                  <span>
                    {rec().progress_phase}
                    {rec().progress_detail ? ` · ${rec().progress_detail}` : ""}
                  </span>
                </Show>
                <Show when={(rec().progress_pct ?? 0) > 0}>
                  <span>{rec().progress_pct?.toFixed(0)}%</span>
                </Show>
                <Show when={rec().error}>
                  <span class="history-detail-error">{rec().error}</span>
                </Show>
              </div>
              <div class="history-detail-log">
                <For each={rec().log || []}>
                  {(line) => {
                    const level = classifyLogLine(line);
                    return <div class={`log-line log-${level}`}>{line}</div>;
                  }}
                </For>
                <Show when={!(rec().log || []).length}>
                  <p class="history-empty">No log saved for this run.</p>
                </Show>
              </div>
              <div class="history-detail-actions">
                <button type="button" class="history-clear-btn" onClick={() => setConfirmLoad(true)}>
                  Load URL
                </button>
                <button type="button" class="confirm-cancel" onClick={props.onClose}>
                  Close
                </button>
              </div>
            </>
          )}
        </Show>
      </div>
      <Show when={confirmLoad() && record()}>
        {(rec) => (
          <ConfirmDialog
            title="Load this video?"
            message={`"${cropHistoryTitle(rec().title)}" will be filled into the URL field.`}
            confirmLabel="Load"
            confirmClass="confirm-cancel"
            onConfirm={() => {
              props.onLoadUrl(rec().url);
              setConfirmLoad(false);
              props.onClose();
            }}
            onCancel={() => setConfirmLoad(false)}
          />
        )}
      </Show>
    </div>
  );
}
