export type ResolveResult = {
  ok: boolean;
  url?: string;
  site?: string;
  title?: string;
  thumbnail?: string;
  dest_folder?: string;
  exists?: boolean;
  error?: string;
};

export type Job = {
  id: string;
  url: string;
  status: 'pending' | 'downloading' | 'completed' | 'failed';
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

export function resolveUrl(url: string) {
  return request<ResolveResult>('/api/resolve', {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
}

export function startDownload(url: string) {
  return request<{ ok: boolean; job?: Job; error?: string }>('/api/download', {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
}

export function fetchJob(jobId: string) {
  return request<{ ok: boolean; job?: Job; error?: string }>(`/api/jobs/${jobId}`);
}
