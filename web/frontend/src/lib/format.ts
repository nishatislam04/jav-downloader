export function formatBytes(n: number): string {
  if (!n || n <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
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

/** "1h 5m 3s" style duration for whole seconds. */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds <= 0) {
    return "";
  }
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const parts: string[] = [];
  if (hours > 0) parts.push(`${hours} hr`);
  if (minutes > 0) parts.push(`${minutes} min`);
  if (secs > 0 || parts.length === 0) parts.push(`${secs} sec`);
  return parts.join(" ");
}

export function formatEta(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds <= 0) {
    return "";
  }
  const total = Math.ceil(seconds);
  if (total < 60) {
    return `${total}s left`;
  }
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  if (minutes < 60) {
    return secs > 0 ? `${minutes}m ${secs}s left` : `${minutes}m left`;
  }
  const hours = Math.floor(minutes / 60);
  const remMin = minutes % 60;
  return remMin > 0 ? `${hours}h ${remMin}m left` : `${hours}h left`;
}

export function estimateEta(job: {
  progress_pct?: number;
  progress_unit?: "" | "bytes" | "segments";
  downloaded?: number;
  total?: number;
  speed?: number;
  created_at?: number;
  updated_at?: number;
}): number | null {
  const speed = job.speed ?? 0;
  if (job.progress_unit === "bytes" && speed > 0) {
    const total = job.total ?? 0;
    const downloaded = job.downloaded ?? 0;
    if (total > downloaded) {
      return (total - downloaded) / speed;
    }
  }

  const pct = job.progress_pct ?? 0;
  const created = job.created_at ?? 0;
  const updated = job.updated_at ?? created;
  if (pct > 0 && pct < 100 && updated > created) {
    return ((updated - created) * (100 - pct)) / pct;
  }
  return null;
}

export function formatProgressPhase(job: {
  progress_phase?: string;
  progress_detail?: string;
}): string {
  const phase = job.progress_phase?.trim();
  if (!phase) return "";
  const detail = job.progress_detail?.trim();
  return detail ? `${phase} · ${detail}` : phase;
}

function detailCoversSegments(job: {
  progress_detail?: string;
  downloaded?: number;
  total?: number;
}): boolean {
  const detail = job.progress_detail?.trim().toLowerCase() ?? "";
  if (!detail) return false;
  if (detail.includes("segment")) return true;
  const downloaded = job.downloaded ?? 0;
  const total = job.total ?? 0;
  if (total > 0) {
    return detail.includes(`${downloaded}/${total}`) || detail.includes(`${downloaded} / ${total}`);
  }
  return false;
}

/** Numeric progress only — use under the phase headline to avoid repeating it. */
export function formatProgressStats(job: {
  progress_pct?: number;
  progress_unit?: "" | "bytes" | "segments";
  progress_detail?: string;
  downloaded?: number;
  total?: number;
  speed?: number;
  created_at?: number;
  updated_at?: number;
}): string {
  const pct = job.progress_pct || 0;
  const parts: string[] = [`${pct.toFixed(1)}%`];

  if (job.progress_unit === "bytes") {
    const downloaded = job.downloaded ?? 0;
    const total = job.total ?? 0;
    if (downloaded > 0 || total > 0) {
      parts.push(
        total > 0
          ? `${formatBytes(downloaded)} / ${formatBytes(total)}`
          : `${formatBytes(downloaded)} / ?`,
      );
    }
  } else if (
    job.progress_unit === "segments" &&
    (job.total ?? 0) > 0 &&
    !detailCoversSegments(job)
  ) {
    parts.push(`${job.downloaded ?? 0} / ${job.total ?? 0} segments`);
  }

  if ((job.speed ?? 0) > 0) {
    parts.push(formatSpeed(job.speed ?? 0));
  }

  const eta = formatEta(estimateEta(job));
  if (eta) {
    parts.push(eta);
  }

  return parts.join(" · ");
}

export function formatProgress(job: {
  progress_pct?: number;
  progress_unit?: "" | "bytes" | "segments";
  progress_phase?: string;
  progress_detail?: string;
  downloaded?: number;
  total?: number;
  speed?: number;
  created_at?: number;
  updated_at?: number;
}): string {
  const phase = formatProgressPhase(job);
  if (phase) {
    return formatProgressStats(job);
  }

  const pct = job.progress_pct || 0;
  const parts: string[] = [`${pct.toFixed(1)}%`];

  if (job.progress_unit === "bytes") {
    const downloaded = job.downloaded ?? 0;
    const total = job.total ?? 0;
    if (downloaded > 0 || total > 0) {
      parts.push(
        total > 0
          ? `${formatBytes(downloaded)} / ${formatBytes(total)}`
          : `${formatBytes(downloaded)} / ?`,
      );
    }
  } else if (job.progress_unit === "segments" && (job.total ?? 0) > 0) {
    parts.push(`${job.downloaded ?? 0} / ${job.total ?? 0} segments`);
  }

  if ((job.speed ?? 0) > 0) {
    parts.push(formatSpeed(job.speed ?? 0));
  }

  const eta = formatEta(estimateEta(job));
  if (eta) {
    parts.push(eta);
  }

  return parts.join(" · ");
}
