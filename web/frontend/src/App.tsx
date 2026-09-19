import { createEffect, createMemo, createSignal, onCleanup, onMount, Show } from 'solid-js';
import {
  cancelJob,
  fetchHealth,
  fetchJob,
  pauseJob,
  resolveUrl,
  resumeJob,
  startDownload,
  type Job,
  type ResolveResult,
} from './api';
import { DownloadIcon } from './components/IconButton';
import MetaCard from './components/MetaCard';
import ProgressCard from './components/ProgressCard';
import TimeField, { durationHint } from './components/TimeField';
import {
  formatDurationSec,
  looksLikeSupportedUrl,
  normalizeTimeInput,
  validateCutRange,
} from './lib/time';

export default function App() {
  const [url, setUrl] = createSignal('');
  const [cutStart, setCutStart] = createSignal('');
  const [cutEnd, setCutEnd] = createSignal('');
  const [downloadDir, setDownloadDir] = createSignal('Loading…');
  const [status, setStatus] = createSignal('');
  const [statusKind, setStatusKind] = createSignal<'ok' | 'error' | ''>('');
  const [resolved, setResolved] = createSignal<ResolveResult | null>(null);
  const [job, setJob] = createSignal<Job | null>(null);
  const [busy, setBusy] = createSignal(false);
  const [resolving, setResolving] = createSignal(false);
  const [actionBusy, setActionBusy] = createSignal(false);

  let pollTimer: ReturnType<typeof setInterval> | undefined;
  let resolveTimer: ReturnType<typeof setTimeout> | undefined;
  let resolveRequest = 0;

  onCleanup(() => {
    if (pollTimer) clearInterval(pollTimer);
    if (resolveTimer) clearTimeout(resolveTimer);
  });

  onMount(async () => {
    const health = await fetchHealth();
    if (health.download_dir) setDownloadDir(health.download_dir);
  });

  function setStatusMessage(text: string, kind: 'ok' | 'error' | '' = '') {
    setStatus(text);
    setStatusKind(kind);
  }

  const durationSec = () => resolved()?.duration_sec ?? null;

  const cutValidation = createMemo(() =>
    validateCutRange(durationSec(), cutStart(), cutEnd()),
  );

  function cutPayload() {
    const payload: { cut_start?: string; cut_end?: string } = {};
    const start = cutStart().trim();
    const end = cutEnd().trim();
    if (start) payload.cut_start = start;
    if (end) payload.cut_end = end;
    return payload;
  }

  async function runResolve(trigger: 'url' | 'cut' = 'url') {
    const value = url().trim();
    if (!looksLikeSupportedUrl(value)) {
      setResolved(null);
      if (!value) setStatusMessage('');
      return;
    }

    if (cutValidation()) {
      setResolved(null);
      setStatusMessage(cutValidation()!, 'error');
      return;
    }

    const requestId = ++resolveRequest;
    setResolving(true);
    if (trigger === 'url') {
      setStatusMessage('Resolving metadata…');
    }
    const data = await resolveUrl(value, cutPayload());
    if (requestId !== resolveRequest) return;
    setResolving(false);

    if (!data.ok) {
      setResolved(null);
      setStatusMessage(data.error || 'Resolve failed', 'error');
      return;
    }

    setResolved(data);
    if (cutValidation()) {
      setStatusMessage(cutValidation()!, 'error');
      return;
    }
    setStatusMessage(
      data.exists
        ? 'File already exists in the download folder.'
        : 'Ready to download.',
      'ok',
    );
  }

  function scheduleResolve(trigger: 'url' | 'cut' = 'url') {
    if (resolveTimer) clearTimeout(resolveTimer);
    resolveTimer = setTimeout(() => {
      void runResolve(trigger);
    }, trigger === 'url' ? 650 : 450);
  }

  createEffect(() => {
    const value = url();
    if (!value.trim()) {
      setResolved(null);
      return;
    }
    scheduleResolve('url');
  });

  createEffect(() => {
    cutStart();
    cutEnd();
    if (!looksLikeSupportedUrl(url())) return;
    scheduleResolve('cut');
  });

  async function pollJob(jobId: string) {
    if (pollTimer) clearInterval(pollTimer);

    const tick = async () => {
      const data = await fetchJob(jobId);
      if (!data.ok || !data.job) return;
      setJob(data.job);
      if (data.job.status === 'completed') {
        setStatusMessage('Download finished.', 'ok');
        setBusy(false);
        if (pollTimer) clearInterval(pollTimer);
      } else if (data.job.status === 'failed') {
        setStatusMessage(data.job.error || 'Download failed', 'error');
        setBusy(false);
        if (pollTimer) clearInterval(pollTimer);
      } else if (data.job.status === 'paused') {
        setBusy(false);
        setStatusMessage('Download paused.', '');
        if (pollTimer) clearInterval(pollTimer);
      }
    };

    await tick();
    pollTimer = setInterval(tick, 800);
  }

  async function handlePause(jobId: string) {
    setActionBusy(true);
    const data = await pauseJob(jobId);
    setActionBusy(false);
    if (!data.ok || !data.job) {
      setStatusMessage(data.error || 'Could not pause download', 'error');
      return;
    }
    setJob(data.job);
    setBusy(false);
    setStatusMessage('Download paused.', '');
  }

  async function handleResume(jobId: string) {
    setActionBusy(true);
    const data = await resumeJob(jobId);
    setActionBusy(false);
    if (!data.ok || !data.job) {
      setStatusMessage(data.error || 'Could not resume download', 'error');
      return;
    }
    setJob(data.job);
    setBusy(true);
    setStatusMessage('Resuming download…');
    await pollJob(jobId);
  }

  async function handleCancel(jobId: string) {
    setActionBusy(true);
    const data = await cancelJob(jobId);
    setActionBusy(false);
    if (!data.ok || !data.job) {
      setStatusMessage(data.error || 'Could not cancel download', 'error');
      return;
    }
    setJob(data.job);
    setBusy(false);
    setStatusMessage('Download cancelled.', 'error');
  }

  async function startDownloadJob() {
    const meta = resolved();
    const value = meta?.url || url().trim();
    if (!value) {
      setStatusMessage('Paste a supported URL first.', 'error');
      return;
    }
    if (cutValidation()) {
      setStatusMessage(cutValidation()!, 'error');
      return;
    }
    if (!meta?.ok) {
      setStatusMessage('Waiting for metadata…', 'error');
      return;
    }

    setBusy(true);
    setStatusMessage('Starting download…');
    const data = await startDownload(value, cutPayload());
    if (!data.ok || !data.job) {
      setStatusMessage(data.error || 'Could not start download', 'error');
      setBusy(false);
      return;
    }

    setJob(data.job);
    await pollJob(data.job.id);
  }

  async function handleDownload() {
    await startDownloadJob();
  }

  async function handleRetry() {
    await startDownloadJob();
  }

  function normalizeStart(value: string) {
    setCutStart(normalizeTimeInput(value));
  }

  function normalizeEnd(value: string) {
    setCutEnd(normalizeTimeInput(value));
  }

  const endPlaceholder = () => {
    const duration = durationSec();
    return duration && duration > 0 ? formatDurationSec(duration) : '2:00';
  };

  const startFieldError = createMemo(() => {
    const err = cutValidation();
    if (!err) return '';
    if (err.startsWith('Start') || err === 'Invalid start time') return err;
    if (err === 'End must be after start') return err;
    return '';
  });

  const endFieldError = createMemo(() => {
    const err = cutValidation();
    if (!err) return '';
    if (err.startsWith('End') || err === 'Invalid end time') return err;
    return '';
  });

  const urlUnsupported = createMemo(() => {
    const value = url().trim();
    return value.length > 0 && !looksLikeSupportedUrl(value);
  });

  const canDownload = createMemo(
    () => !!resolved()?.ok && !cutValidation() && !busy() && !resolving(),
  );

  return (
    <main class="shell">
      <header>
        <h1>JAV Downloader</h1>
      </header>

      <section class="card">
        <label for="url" class="url-label">
          <span>Video URL</span>
          <Show when={urlUnsupported()}>
            <span class="badge-unsupported">Unsupported</span>
          </Show>
          <Show when={resolving()}>
            <span class="spinner" aria-label="Resolving" title="Resolving" />
          </Show>
        </label>
        <div class="url-input-row">
          <input
            id="url"
            type="url"
            placeholder="https://jav.guru/123456/example-title/"
            autocomplete="off"
            spellcheck={false}
            value={url()}
            onInput={(event) => setUrl(event.currentTarget.value)}
          />
          <Show when={canDownload()}>
            <button
              type="button"
              class="download-circle"
              aria-label="Download"
              title="Download"
              onClick={handleDownload}
            >
              <DownloadIcon />
            </button>
          </Show>
        </div>

        <div class="cut-row">
          <TimeField
            id="cut-start"
            label="Start at"
            value={cutStart()}
            placeholder="0:00"
            hint={durationHint(durationSec())}
            error={startFieldError()}
            onChange={setCutStart}
            onBlurNormalize={normalizeStart}
          />
          <TimeField
            id="cut-end"
            label="End at"
            value={cutEnd()}
            placeholder={endPlaceholder()}
            hint={
              durationSec()
                ? `Max ${formatDurationSec(durationSec())} · leave empty for full`
                : 'Leave empty for full video'
            }
            error={endFieldError()}
            onChange={setCutEnd}
            onBlurNormalize={normalizeEnd}
          />
        </div>
        <p class="hint">
          Timestamps must be within the video length once metadata loads. Use{' '}
          <code>mm:ss</code> or seconds (e.g. <code>90</code> → <code>1:30</code>
          ).
        </p>

        <p class={`status ${statusKind()}`} aria-live="polite">
          {status()}
        </p>
      </section>

      <Show when={resolved()} keyed>
        {(meta) => (meta.ok ? <MetaCard meta={meta} /> : null)}
      </Show>

      <Show when={job()}>
        {(current) => (
          <ProgressCard
            job={current()}
            onPause={handlePause}
            onResume={handleResume}
            onCancel={handleCancel}
            onRetry={handleRetry}
            actionBusy={actionBusy()}
          />
        )}
      </Show>

      <section class="card foot">
        <p class="label">Output directory</p>
        <p class="mono">{downloadDir()}</p>
      </section>
    </main>
  );
}
