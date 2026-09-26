import type { AudioSettings, EncodeSettings } from "./lib/persist";

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
  code?: string;
  release_date?: string;
  studio?: string;
  label?: string;
  tags?: string[];
  actresses?: string[];
  posted?: string;
  stream_mirrors?: string[];
  output_size_bytes?: number | null;
  output_size_exact?: boolean;
  stream_type?: string;
  hls_tiers?: HlsTier[];
  exists?: boolean;
  error?: string;
};

export type Job = {
  id: string;
  url: string;
  status: "pending" | "downloading" | "paused" | "completed" | "failed";
  title?: string;
  site?: string;
  thumbnail?: string;
  dest_folder?: string;
  output_file?: string;
  downloaded?: number;
  total?: number;
  speed?: number;
  progress_pct?: number;
  progress_unit?: "" | "bytes" | "segments" | "time";
  progress_phase?: string;
  progress_detail?: string;
  error?: string;
  log?: string[];
  created_at?: number;
  started_at?: number;
  completed_at?: number;
  elapsed_sec?: number;
  download_phase_sec?: number;
  encode_phase_sec?: number;
  updated_at?: number;
};

export type FolderPathResult = {
  ok: boolean;
  path?: string;
  error?: string;
};

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = (await resp.json().catch(() => ({}))) as T & { error?: string };
  if (!resp.ok && !data.error) {
    (data as { error?: string }).error = `HTTP ${resp.status}`;
  }
  return data;
}

export type AppSettings = {
  hide_thumbnails?: boolean;
  history_group_by_url?: boolean;
  remember_save_path?: boolean;
  save_path?: string;
  remember_audio?: boolean;
  audio_settings?: Partial<AudioSettings>;
  remember_encode?: boolean;
  encode_settings?: Partial<EncodeSettings>;
};

export function fetchHealth() {
  return request<{
    ok: boolean;
    download_dir?: string;
    platform?: "termux" | "desktop";
    reveal_mode?: "open_file" | "show_in_folder";
    history_db?: string;
    history_ok?: boolean;
    history_last_error?: string | null;
    settings?: AppSettings;
  }>("/api/health");
}

export function fetchSettings() {
  return request<{ ok: boolean; settings?: AppSettings; error?: string }>(
    "/api/settings",
  );
}

export function saveSettings(settings: AppSettings) {
  return request<{ ok: boolean; settings?: AppSettings; error?: string }>(
    "/api/settings",
    {
      method: "POST",
      body: JSON.stringify(settings),
    },
  );
}

export function fetchEncodingCapabilities() {
  return request<EncodingCapabilities>("/api/encoding/capabilities");
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
  encode?: boolean;
  encode_codec?: string;
  encode_crf?: number;
  encode_max_height?: number;
  encode_output_mode?: string;
  encode_preset?: string;
  encode_threads?: number;
  encode_engine?: string;
  encode_hardware_bitrate_kbps?: number;
  encode_hardware_gop?: number;
  encode_hardware_bitrate_mode?: string;
  encode_small_file?: boolean;
};

export type HardwareCodecCapability = {
  available: boolean;
  encoder?: string | null;
  reason?: string | null;
};

export type EncodingCapabilities = {
  ok: boolean;
  platform?: string;
  hardware_codecs?: Record<string, HardwareCodecCapability>;
  hardware_bitrate_modes?: string[];
};

export function resolveUrl(url: string, options: DownloadOptions = {}, signal?: AbortSignal) {
  return request<ResolveResult>("/api/resolve", {
    method: "POST",
    body: JSON.stringify({ url, ...options }),
    signal,
  });
}

export function startDownload(url: string, options: DownloadOptions = {}) {
  return request<{ ok: boolean; job?: Job; error?: string }>("/api/download", {
    method: "POST",
    body: JSON.stringify({ url, ...options }),
  });
}

export function validateFolder(path: string) {
  return request<FolderPathResult>("/api/validate-folder", {
    method: "POST",
    body: JSON.stringify({ path }),
  });
}

export function revealFile(path: string) {
  return request<{ ok: boolean; error?: string }>("/api/reveal", {
    method: "POST",
    body: JSON.stringify({ path }),
  });
}

export function fetchJob(jobId: string) {
  return request<{ ok: boolean; job?: Job; error?: string }>(`/api/jobs/${jobId}`);
}

export function pauseJob(jobId: string) {
  return request<{ ok: boolean; job?: Job; error?: string }>(`/api/jobs/${jobId}/pause`, {
    method: "POST",
    body: "{}",
  });
}

export function resumeJob(jobId: string) {
  return request<{ ok: boolean; job?: Job; error?: string }>(`/api/jobs/${jobId}/resume`, {
    method: "POST",
    body: "{}",
  });
}

export function cancelJob(jobId: string) {
  return request<{ ok: boolean; job?: Job; error?: string }>(`/api/jobs/${jobId}/cancel`, {
    method: "POST",
    body: "{}",
  });
}

export type CleanupResult = {
  ok: boolean;
  removed_files: number;
  removed_dirs: number;
  freed_bytes: number;
  skipped: number;
  error?: string;
};

export function cleanupJob(jobId: string) {
  return request<CleanupResult>("/api/jobs/cleanup", {
    method: "POST",
    body: JSON.stringify({ job_id: jobId }),
  });
}

export type HistoryEntry = {
  id: string;
  url: string;
  title: string;
  thumbnail: string;
  downloadedAt: number;
  status?: string;
  updatedAt?: number;
};

export type HistoryRecord = HistoryEntry & {
  site?: string;
  dest_folder?: string;
  output_file?: string;
  downloaded?: number;
  total?: number;
  speed?: number;
  progress_pct?: number;
  progress_unit?: string;
  progress_phase?: string;
  progress_detail?: string;
  error?: string;
  log?: string[];
  meta?: Record<string, unknown>;
  created_at?: number;
  started_at?: number;
  completed_at?: number;
  elapsed_sec?: number;
  download_phase_sec?: number;
  encode_phase_sec?: number;
};

export function fetchHistory(limit = 40, offset = 0) {
  const qs = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return request<{
    ok: boolean;
    entries?: HistoryEntry[];
    total?: number;
    has_more?: boolean;
    error?: string;
  }>(`/api/history?${qs.toString()}`);
}

export function fetchHistoryRecord(id: string) {
  return request<{ ok: boolean; record?: HistoryRecord; error?: string }>(
    `/api/history/${encodeURIComponent(id)}`,
  );
}

export function deleteHistoryEntry(id: string) {
  return request<{ ok: boolean; error?: string }>("/api/history/delete", {
    method: "POST",
    body: JSON.stringify({ id }),
  });
}

export function clearHistoryApi() {
  return request<{ ok: boolean; error?: string }>("/api/history/delete", {
    method: "POST",
    body: JSON.stringify({ all: true }),
  });
}

export function importHistoryEntries(entries: HistoryEntry[]) {
  return request<{ ok: boolean; imported?: number; error?: string }>(
    "/api/history/import",
    {
      method: "POST",
      body: JSON.stringify({ entries }),
    },
  );
}
