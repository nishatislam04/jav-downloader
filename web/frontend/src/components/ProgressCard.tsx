import type { JSX } from "solid-js";
import { createEffect, createSignal, For, onCleanup, Show } from "solid-js";
import type { Job } from "../api";
import {
  formatDuration,
  formatProgress,
  formatProgressPhase,
  formatProgressStats,
} from "../lib/format";
import { classifyLogLine, splitLogStamp } from "../lib/loglevel";
import IconButton, {
  ClockIcon,
  CloseIcon,
  CollapseIcon,
  CopyIcon,
  DownloadIcon,
  EncodeIcon,
  ExpandIcon,
  FolderIcon,
  PauseIcon,
  PlayIcon,
  RetryIcon,
  SuccessIcon,
} from "./IconButton";

type Props = {
  job: Job;
  onPause?: (jobId: string) => void;
  onResume?: (jobId: string) => void;
  onCancel?: (jobId: string) => void;
  onRetry?: () => void;
  onReveal?: (path: string) => void;
  revealMode?: "open_file" | "show_in_folder";
  actionBusy?: boolean;
};

function progressText(job: Job): string {
  if (job.status === "completed") {
    return job.output_file ? `Done: ${job.output_file}` : "Download completed";
  }
  if (job.status === "failed") {
    return job.error || "Download failed";
  }
  const stats = formatProgressStats(job);
  if (job.status === "paused") {
    return stats ? `Paused · ${stats}` : "Paused";
  }
  if (formatProgressPhase(job)) {
    return stats;
  }
  return formatProgress(job);
}

export default function ProgressCard(props: Props) {
  let logEl: HTMLDivElement | undefined;

  // Copy affordance appears only once log output has settled for a moment.
  const [logIdle, setLogIdle] = createSignal(false);
  const [copied, setCopied] = createSignal(false);
  const [logFull, setLogFull] = createSignal(false);
  const [playOpen, setPlayOpen] = createSignal(false);
  let idleTimer: ReturnType<typeof setTimeout> | undefined;
  let copiedTimer: ReturnType<typeof setTimeout> | undefined;
  let lastLogKey = "";

  const logLines = () => props.job.log || [];

  createEffect(() => {
    const key = logLines().join("\n");
    if (key === lastLogKey) return;
    lastLogKey = key;
    setLogIdle(false);
    setCopied(false);
    if (idleTimer) clearTimeout(idleTimer);
    if (!key) return;
    idleTimer = setTimeout(() => setLogIdle(true), 1500);
  });

  onCleanup(() => {
    if (idleTimer) clearTimeout(idleTimer);
    if (copiedTimer) clearTimeout(copiedTimer);
  });

  function toggleLogFull() {
    setLogFull((value) => !value);
  }

  function onLogFullKey(event: KeyboardEvent) {
    if (event.key === "Escape" && logFull()) {
      event.preventDefault();
      setLogFull(false);
    }
  }

  createEffect(() => {
    if (!logFull()) return;
    window.addEventListener("keydown", onLogFullKey);
    onCleanup(() => window.removeEventListener("keydown", onLogFullKey));
  });

  async function copyLog() {
    const text = logLines().join("\n");
    if (!text) return;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
      } else {
        // Clipboard API is unavailable on insecure origins (plain http).
        const area = document.createElement("textarea");
        area.value = text;
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();
        document.execCommand("copy");
        area.remove();
      }
      setCopied(true);
      if (copiedTimer) clearTimeout(copiedTimer);
      copiedTimer = setTimeout(() => setCopied(false), 1600);
    } catch {
      /* copy unavailable; leave button as-is */
    }
  }

  const pct = () => props.job.progress_pct || 0;
  const isDownloading = () => props.job.status === "downloading";
  const isPaused = () => props.job.status === "paused";
  const isFailed = () => props.job.status === "failed";
  const isCompleted = () => props.job.status === "completed";
  const isCancelled = () => isFailed() && props.job.error === "Download cancelled";
  const barWidth = () => {
    if (isCancelled()) return 0;
    const value = pct();
    if (value <= 0) return 0;
    return Math.max(value, 1.5);
  };
  const canRetry = () => isFailed() && !isCancelled();
  const showControls = () => isDownloading() || isPaused() || canRetry();
  const outputFile = () => props.job.output_file || "";
  const phaseText = () => formatProgressPhase(props.job);
  const totalTime = () => formatDuration(props.job.elapsed_sec);
  const mediaUrl = () => `/api/jobs/${props.job.id}/media`;

  const phaseTimes = () => {
    const dl = props.job.download_phase_sec ?? 0;
    const enc = props.job.encode_phase_sec ?? 0;
    if (dl <= 0 && enc <= 0) return "";
    const parts: string[] = [];
    if (dl > 0) parts.push(`download ${formatDuration(dl)}`);
    if (enc > 0) parts.push(`encode ${formatDuration(enc)}`);
    return parts.join(" · ");
  };

  // One glanceable glyph for "what is happening right now".
  const statusIcon = (): {
    icon: JSX.Element;
    cls: string;
    label: string;
  } | null => {
    if (isCancelled()) return null;
    if (isCompleted()) {
      return { icon: <SuccessIcon />, cls: "done", label: "Completed" };
    }
    if (isFailed()) {
      return { icon: <CloseIcon />, cls: "failed", label: "Failed" };
    }
    if (isPaused()) {
      return { icon: <PauseIcon />, cls: "paused", label: "Paused" };
    }
    if (/encoding/i.test(props.job.progress_phase || "")) {
      return { icon: <EncodeIcon />, cls: "encoding", label: "Encoding" };
    }
    if (isDownloading() && !/^preparing$/i.test(props.job.progress_phase || "")) {
      return {
        icon: <DownloadIcon />,
        cls: "downloading",
        label: "Downloading",
      };
    }
    return { icon: <ClockIcon />, cls: "pending", label: "Waiting" };
  };
  const status = () => statusIcon();

  createEffect(() => {
    logLines();
    if (logEl) {
      logEl.scrollTop = logEl.scrollHeight;
    }
  });

  return (
    <section class="card progress-card">
      <div class="progress-head">
        <div class="progress-head-left">
          <p class="label">Progress</p>
          <Show when={isCompleted() && (totalTime() || phaseTimes())}>
            <div class="progress-timing mono">
              <Show when={totalTime()}>
                <span class="total-time">{totalTime()}</span>
              </Show>
              <Show when={phaseTimes()}>
                <span class="phase-times">{phaseTimes()}</span>
              </Show>
            </div>
          </Show>
        </div>
        <Show when={showControls() || (isCompleted() && outputFile())}>
          <div class="progress-actions">
            <Show when={isCompleted() && outputFile()}>
              <button
                type="button"
                class="tool-btn subtle reveal-btn"
                title="Play encoded output in this browser"
                onClick={() => setPlayOpen(true)}
              >
                <PlayIcon />
                <span>Play</span>
              </button>
            </Show>
            <Show
              when={
                isCompleted() &&
                outputFile() &&
                props.onReveal &&
                props.revealMode !== "open_file"
              }
            >
              <button
                type="button"
                class="tool-btn subtle reveal-btn"
                onClick={() => props.onReveal?.(outputFile())}
              >
                <FolderIcon />
                <span>Show in folder</span>
              </button>
            </Show>
            <Show when={isDownloading() && props.onPause}>
              <IconButton
                label="Pause download"
                title="Pause"
                disabled={props.actionBusy}
                onClick={() => props.onPause?.(props.job.id)}
              >
                <PauseIcon />
              </IconButton>
            </Show>
            <Show when={isPaused() && props.onResume}>
              <IconButton
                label="Resume download"
                title="Resume"
                disabled={props.actionBusy}
                onClick={() => props.onResume?.(props.job.id)}
              >
                <PlayIcon />
              </IconButton>
            </Show>
            <Show when={canRetry() && props.onRetry}>
              <IconButton
                label="Retry download"
                title="Retry"
                disabled={props.actionBusy}
                onClick={() => props.onRetry?.()}
              >
                <RetryIcon />
              </IconButton>
            </Show>
            <Show when={(isDownloading() || isPaused()) && props.onCancel}>
              <IconButton
                label="Cancel download"
                title="Cancel"
                variant="danger"
                disabled={props.actionBusy}
                onClick={() => props.onCancel?.(props.job.id)}
              >
                <CloseIcon />
              </IconButton>
            </Show>
          </div>
        </Show>
      </div>
      <Show when={playOpen() && isCompleted() && outputFile()}>
        <div
          class="video-play-overlay"
          role="dialog"
          aria-label="Play video"
          onClick={() => setPlayOpen(false)}
        >
          <div class="video-play-panel" onClick={(event) => event.stopPropagation()}>
            <video
              class="video-play-player"
              controls
              playsinline
              preload="metadata"
              src={mediaUrl()}
            />
            <p class="hint video-play-hint">
              Encoded output · keep_both saves a separate original on disk
            </p>
            <button type="button" class="tool-btn subtle" onClick={() => setPlayOpen(false)}>
              Close
            </button>
          </div>
        </div>
      </Show>
      <div class="progress-body">
        <Show when={!isCancelled()}>
          <div class="bar-track" aria-hidden="true">
            <div class="bar-fill" style={{ width: `${barWidth()}%` }} />
          </div>
        </Show>
        <Show when={phaseText() && !isCompleted() && !isCancelled()}>
          <p class="progress-phase">{phaseText()}</p>
        </Show>
        <p class="mono progress-text">
          <Show when={status()} fallback={"Download cancelled"}>
            {(s) => (
              <>
                <span
                  class={`status-icon status-icon-${s().cls}`}
                  role="img"
                  aria-label={s().label}
                  title={s().label}
                >
                  {s().icon}
                </span>
                {progressText(props.job)}
              </>
            )}
          </Show>
        </p>
        <Show when={logLines().length > 0}>
          <div class="log-block" classList={{ "log-block-full": logFull() }}>
            <div class="log-block-head">
              <span class="log-block-actions">
                <Show when={logIdle()}>
                  <button
                    type="button"
                    class="log-copy-btn"
                    aria-label="Copy log"
                    onClick={() => void copyLog()}
                  >
                    <CopyIcon />
                    <span>{copied() ? "Copied" : "Copy"}</span>
                  </button>
                </Show>
                <button
                  type="button"
                  class="log-copy-btn log-full-btn"
                  aria-label={logFull() ? "Exit fullscreen log" : "View fullscreen log"}
                  title={logFull() ? "Exit fullscreen" : "Fullscreen"}
                  onClick={toggleLogFull}
                >
                  <Show when={logFull()} fallback={<ExpandIcon />}>
                    <CollapseIcon />
                  </Show>
                </button>
              </span>
            </div>
            <div class="job-log" ref={logEl} aria-live="polite">
              <For each={logLines()}>
                {(line) => {
                  const level = classifyLogLine(line);
                  const { stamp, message } = splitLogStamp(line);
                  return (
                    <div class="job-log-line" classList={{ "error-line": level === "error" }}>
                      <Show when={stamp}>
                        <span class="log-stamp">{stamp}</span>
                      </Show>
                      <span class={`log-msg ${level}`}>{message}</span>
                    </div>
                  );
                }}
              </For>
            </div>
          </div>
        </Show>
      </div>
    </section>
  );
}
