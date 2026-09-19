export type HlsTier = {
  id: string;
  label: string;
  height?: number | null;
  bandwidth?: number | null;
  pref?: string;
};

export type ResolveResult = {
  ok: boolean;
  url?: string;
  site?: string;
  title?: string;
  thumbnail?: string;
  dest_folder?: string;
  duration_sec?: number | null;
  quality?: string;
  views?: string;
  uploader?: string;
  stream_mirrors?: string[];
  active_stream?: string;
  hls_tiers?: HlsTier[];
  active_hls_tier?: string;
  output_size_bytes?: number | null;
  output_size_exact?: boolean;
  exists?: boolean;
  error?: string;
};

export type Job = {
  id: string;
  url: string;
  status: 'pending' | 'downloading' | 'paused' | 'completed' | 'failed';
  title?: string;
  site?: string;
  thumbnail?: string;
  dest_folder?: string;
  output_file?: string;
  downloaded?: number;
  total?: number;
  speed?: number;
  progress_pct?: number;
  progress_unit?: '' | 'bytes' | 'segments';
  error?: string;
  log?: string[];
  created_at?: number;
  updated_at?: number;
};

export type FolderPathResult = {
  ok: boolean;
  path?: string;
  error?: string;
};

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const resp = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  const data = (await resp.json().catch(() => ({}))) as T & { error?: string };
  if (!resp.ok && !data.error) {
    (data as { error?: string }).error = `HTTP ${resp.status}`;
  }
  return data;
}

export function fetchHealth() {
  return request<{ ok: boolean; download_dir?: string }>('/api/health');
}

export type DownloadOptions = {
  cut_start?: string;
  cut_end?: string;
  cuts?: Array<{ start?: string; end?: string }>;
  dest_folder?: string;
  output_title?: string;
  audio_fade?: boolean;
  audio_loudnorm?: boolean;
  audio_mute?: boolean;
  audio_bitrate?: number;
  audio_volume?: number;
  stream_preference?: string;
  resolution_pref?: string;
  hls_tier?: string;
  encode?: boolean;
  encode_codec?: string;
  encode_crf?: number;
  encode_max_height?: number;
  encode_output_mode?: string;
  encode_preset?: string;
  encode_threads?: number;
};

export function resolveUrl(url: string, options: DownloadOptions = {}) {
  return request<ResolveResult>('/api/resolve', {
    method: 'POST',
    body: JSON.stringify({ url, ...options }),
  });
}

export function startDownload(url: string, options: DownloadOptions = {}) {
  return request<{ ok: boolean; job?: Job; error?: string }>('/api/download', {
    method: 'POST',
    body: JSON.stringify({ url, ...options }),
  });
}

export function validateFolder(path: string) {
  return request<FolderPathResult>('/api/validate-folder', {
    method: 'POST',
    body: JSON.stringify({ path }),
  });
}

export function revealFile(path: string) {
  return request<{ ok: boolean; error?: string }>('/api/reveal', {
    method: 'POST',
    body: JSON.stringify({ path }),
  });
}

export function fetchJob(jobId: string) {
  return request<{ ok: boolean; job?: Job; error?: string }>(`/api/jobs/${jobId}`);
}

export function pauseJob(jobId: string) {
  return request<{ ok: boolean; job?: Job; error?: string }>(
    `/api/jobs/${jobId}/pause`,
    { method: 'POST', body: '{}' },
  );
}

export function resumeJob(jobId: string) {
  return request<{ ok: boolean; job?: Job; error?: string }>(
    `/api/jobs/${jobId}/resume`,
    { method: 'POST', body: '{}' },
  );
}

export function cancelJob(jobId: string) {
  return request<{ ok: boolean; job?: Job; error?: string }>(
    `/api/jobs/${jobId}/cancel`,
    { method: 'POST', body: '{}' },
  );
}
