export function formatBytes(n: number): string {
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

export function formatSpeed(bps: number): string {
  return `${formatBytes(bps)}/s`;
}

export function formatProgress(job: {
  progress_pct?: number;
  progress_unit?: '' | 'bytes' | 'segments';
  downloaded?: number;
  total?: number;
  speed?: number;
}): string {
  const pct = job.progress_pct || 0;
  const parts = [`${pct.toFixed(1)}%`];

  if (job.progress_unit === 'bytes' && (job.total ?? 0) > 0) {
    parts.push(`${formatBytes(job.downloaded ?? 0)} / ${formatBytes(job.total ?? 0)}`);
  } else if (job.progress_unit === 'segments' && (job.total ?? 0) > 0) {
    parts.push(`${job.downloaded ?? 0} / ${job.total ?? 0} segments`);
  }

  if ((job.speed ?? 0) > 0) {
    parts.push(formatSpeed(job.speed ?? 0));
  }

  return parts.join(' · ');
}
