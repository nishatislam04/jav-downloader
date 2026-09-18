const urlInput = document.getElementById('url');
const resolveBtn = document.getElementById('resolve-btn');
const downloadBtn = document.getElementById('download-btn');
const statusEl = document.getElementById('status');
const metaEl = document.getElementById('meta');
const progressCard = document.getElementById('progress-card');
const barEl = document.getElementById('bar');
const progressText = document.getElementById('progress-text');
const downloadDirEl = document.getElementById('download-dir');
const siteNameEl = document.getElementById('site-name');
const titleEl = document.getElementById('title');
const destEl = document.getElementById('dest');
const thumbEl = document.getElementById('thumb');

let resolved = null;
let pollTimer = null;

function setStatus(text, kind = '') {
  statusEl.textContent = text;
  statusEl.className = `status ${kind}`.trim();
}

function formatBytes(n) {
  if (!n || n <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = n;
  let idx = 0;
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024;
    idx += 1;
  }
  return `${value.toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`;
}

function formatSpeed(bps) {
  return `${formatBytes(bps)}/s`;
}

async function api(path, options = {}) {
  const resp = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok && !data.error) {
    data.error = `HTTP ${resp.status}`;
  }
  return data;
}

function showMeta(data) {
  metaEl.classList.remove('hidden');
  siteNameEl.textContent = data.site || '—';
  titleEl.textContent = data.title || '—';
  destEl.textContent = data.dest_folder || '—';
  if (data.thumbnail) {
    thumbEl.src = data.thumbnail;
    thumbEl.classList.remove('hidden');
  } else {
    thumbEl.classList.add('hidden');
  }
}

function updateProgress(job) {
  progressCard.classList.remove('hidden');
  const pct = job.progress_pct || 0;
  barEl.style.width = `${pct}%`;
  if (job.status === 'completed') {
    progressText.textContent = job.output_file
      ? `Done: ${job.output_file}`
      : 'Download completed';
    setStatus('Download finished.', 'ok');
    return;
  }
  if (job.status === 'failed') {
    progressText.textContent = job.error || 'Download failed';
    setStatus(job.error || 'Download failed', 'error');
    return;
  }
  const parts = [`${pct.toFixed(1)}%`];
  if (job.progress_unit === 'bytes' && job.total > 0) {
    parts.push(`${formatBytes(job.downloaded)} / ${formatBytes(job.total)}`);
  } else if (job.progress_unit === 'segments' && job.total > 0) {
    parts.push(`${job.downloaded} / ${job.total} segments`);
  }
  if (job.speed > 0) {
    parts.push(formatSpeed(job.speed));
  }
  progressText.textContent = parts.join(' · ');
}

async function pollJob(jobId) {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  const tick = async () => {
    const data = await api(`/api/jobs/${jobId}`);
    if (!data.ok || !data.job) return;
    updateProgress(data.job);
    if (data.job.status === 'completed' || data.job.status === 'failed') {
      clearInterval(pollTimer);
      pollTimer = null;
      downloadBtn.disabled = false;
      resolveBtn.disabled = false;
    }
  };
  await tick();
  pollTimer = setInterval(tick, 800);
}

resolveBtn.addEventListener('click', async () => {
  const url = urlInput.value.trim();
  if (!url) {
    setStatus('Enter a URL first.', 'error');
    return;
  }
  resolveBtn.disabled = true;
  downloadBtn.disabled = true;
  setStatus('Resolving metadata…');
  const data = await api('/api/resolve', {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
  resolveBtn.disabled = false;
  if (!data.ok) {
    resolved = null;
    metaEl.classList.add('hidden');
    setStatus(data.error || 'Resolve failed', 'error');
    return;
  }
  resolved = data;
  showMeta(data);
  downloadBtn.disabled = false;
  if (data.exists) {
    setStatus('File already exists in the download folder.', 'ok');
  } else {
    setStatus('Metadata ready. Click Download.', 'ok');
  }
});

downloadBtn.addEventListener('click', async () => {
  const url = (resolved && resolved.url) || urlInput.value.trim();
  if (!url) {
    setStatus('Resolve a URL first.', 'error');
    return;
  }
  downloadBtn.disabled = true;
  resolveBtn.disabled = true;
  setStatus('Starting download…');
  const data = await api('/api/download', {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
  if (!data.ok || !data.job) {
    setStatus(data.error || 'Could not start download', 'error');
    downloadBtn.disabled = false;
    resolveBtn.disabled = false;
    return;
  }
  updateProgress(data.job);
  await pollJob(data.job.id);
});

async function boot() {
  const health = await api('/api/health');
  if (health.download_dir) {
    downloadDirEl.textContent = health.download_dir;
  }
}

boot();
