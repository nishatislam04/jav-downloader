/** Parse user time input into canonical m:ss or h:mm:ss. */
export function normalizeTimeInput(raw: string): string {
  const text = raw.trim();
  if (!text) return '';

  if (/^\d+$/.test(text)) {
    return formatDurationSec(Number(text));
  }

  const parts = text.split(':').map((part) => part.trim());
  if (parts.some((part) => part === '' || Number.isNaN(Number(part)))) {
    return text;
  }

  if (parts.length === 2) {
    const [minutes, seconds] = parts.map(Number);
    return formatDurationSec(minutes * 60 + seconds);
  }

  if (parts.length === 3) {
    const [hours, minutes, seconds] = parts.map(Number);
    return formatDurationSec(hours * 3600 + minutes * 60 + seconds);
  }

  return text;
}

export function parseTimeInputSec(raw: string): number | null {
  const normalized = normalizeTimeInput(raw);
  if (!normalized) return null;
  const parts = normalized.split(':').map(Number);
  if (parts.some((part) => Number.isNaN(part))) return null;
  if (parts.length === 2) {
    return parts[0] * 60 + parts[1];
  }
  if (parts.length === 3) {
    return parts[0] * 3600 + parts[1] * 60 + parts[2];
  }
  return null;
}

export function validateCutRange(
  durationSec: number | null | undefined,
  startRaw: string,
  endRaw: string,
): string | null {
  const duration = Math.floor(Number(durationSec) || 0);
  if (duration <= 0) {
    return null;
  }

  const startText = startRaw.trim();
  const endText = endRaw.trim();
  const start = startText ? parseTimeInputSec(startText) : 0;
  if (startText && start === null) {
    return 'Invalid start time';
  }
  if ((start ?? 0) >= duration) {
    return `Start exceeds video length (${formatDurationSec(duration)})`;
  }

  if (!endText) {
    return null;
  }
  const end = parseTimeInputSec(endText);
  if (end === null) {
    return 'Invalid end time';
  }
  if (end > duration) {
    return `End exceeds video length (${formatDurationSec(duration)})`;
  }
  if (end <= (start ?? 0)) {
    return 'End must be after start';
  }
  return null;
}

export function clampTimeInput(raw: string, maxSec: number | null | undefined): string {
  const parsed = parseTimeInputSec(raw);
  if (parsed === null) return raw.trim();
  const max = Math.max(0, Math.floor(Number(maxSec) || 0));
  if (max > 0 && parsed > max) {
    return formatDurationSec(max);
  }
  return normalizeTimeInput(raw);
}

export function formatDurationSec(totalSec: number | null | undefined): string {
  const sec = Math.max(0, Math.floor(Number(totalSec) || 0));
  const hours = Math.floor(sec / 3600);
  const minutes = Math.floor((sec % 3600) / 60);
  const seconds = sec % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

export function looksLikeSupportedUrl(value: string): boolean {
  const text = value.trim();
  if (!/^https?:\/\//i.test(text)) return false;
  try {
    const host = new URL(text).hostname.toLowerCase();
    return (
      host.includes('jable') ||
      host.includes('missav') ||
      host.includes('supjav') ||
      host.includes('hanime1') ||
      host.includes('jav.guru') ||
      host.includes('spankbang.com')
    );
  } catch {
    return false;
  }
}
