import { createSignal, onCleanup, onMount, Show } from 'solid-js';
import {
  cancelJob,
  fetchHealth,
  fetchJob,
  resolveUrl,
  startDownload,
  type Job,
  type ResolveResult,
} from './api';
import MetaCard from './components/MetaCard';
import ProgressCard from './components/ProgressCard';

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
  const [cancelling, setCancelling] = createSignal(false);

  let pollTimer: ReturnType<typeof setInterval> | undefined;

  onCleanup(() => {
    if (pollTimer) clearInterval(pollTimer);
  });

  onMount(async () => {
    const health = await fetchHealth();
    if (health.download_dir) setDownloadDir(health.download_dir);
  });

  function setStatusMessage(text: string, kind: 'ok' | 'error' | '' = '') {
    setStatus(text);
    setStatusKind(kind);
  }

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
      }
    };

    await tick();
    pollTimer = setInterval(tick, 800);
  }

  function cutPayload() {
    const payload: { cut_start?: string; cut_end?: string } = {};
    const start = cutStart().trim();
    const end = cutEnd().trim();
    if (start) payload.cut_start = start;
    if (end) payload.cut_end = end;
    return payload;
  }

  async function handleResolve() {
    const value = url().trim();
    if (!value) {
      setStatusMessage('Enter a URL first.', 'error');
      return;
    }

    setBusy(true);
    setStatusMessage('Resolving metadata…');
    const data = await resolveUrl(value, cutPayload());
    setBusy(false);

    if (!data.ok) {
      setResolved(null);
      setStatusMessage(data.error || 'Resolve failed', 'error');
      return;
    }

    setResolved(data);
    setStatusMessage(
      data.exists
        ? 'File already exists in the download folder.'
        : 'Metadata ready. Click Download.',
      'ok',
    );
  }

  async function handleCancel(jobId: string) {
    setCancelling(true);
    const data = await cancelJob(jobId);
    setCancelling(false);
    if (!data.ok || !data.job) {
      setStatusMessage(data.error || 'Could not cancel download', 'error');
      return;
    }
    setJob(data.job);
    setBusy(false);
    setStatusMessage('Download cancelled.', 'error');
  }

  async function handleDownload() {
    const meta = resolved();
    const value = meta?.url || url().trim();
    if (!value) {
      setStatusMessage('Resolve a URL first.', 'error');
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

  return (
    <main class="shell">
      <header>
        <h1>JAV Downloader</h1>
        <p class="subtitle">
          Paste a JableTV, MissAV, SupJav, Hanime1, Jav.guru, or SpankBang URL.
        </p>
      </header>

      <section class="card">
        <label for="url">Video URL</label>
        <input
          id="url"
          type="url"
          placeholder="https://jav.guru/123456/example-title/"
          autocomplete="off"
          spellcheck={false}
          value={url()}
          onInput={(event) => setUrl(event.currentTarget.value)}
        />

        <div class="cut-row">
          <div>
            <label for="cut-start">Start (optional)</label>
            <input
              id="cut-start"
              type="text"
              placeholder="0:00 or 90"
              autocomplete="off"
              spellcheck={false}
              value={cutStart()}
              onInput={(event) => setCutStart(event.currentTarget.value)}
            />
          </div>
          <div>
            <label for="cut-end">End (optional)</label>
            <input
              id="cut-end"
              type="text"
              placeholder="5:00"
              autocomplete="off"
              spellcheck={false}
              value={cutEnd()}
              onInput={(event) => setCutEnd(event.currentTarget.value)}
            />
          </div>
        </div>
        <p class="hint">
          Leave both empty for the full video. Partial cuts use ffmpeg for MP4
          sources and segment filtering for HLS. Interrupted full downloads
          resume from the existing <code>.part</code> file.
        </p>

        <div class="actions">
          <button type="button" disabled={busy()} onClick={handleResolve}>
            Resolve
          </button>
          <button
            type="button"
            class="download-btn"
            disabled={busy() || !resolved()?.ok}
            onClick={handleDownload}
          >
            Download
          </button>
        </div>

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
            onCancel={handleCancel}
            cancelling={cancelling()}
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
