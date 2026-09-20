export function pad2(n: number): string {
  return String(Math.floor(n)).padStart(2, "0");
}

/** Parse canonical or colon-separated time string to total seconds. */
export function parseHmsToSec(raw: string): number | null {
  return parseTimeInputSec(raw);
}

/** Parse user time input into canonical m:ss or h:mm:ss. */
export function normalizeTimeInput(raw: string): string {
  const text = raw.trim();
  if (!text) return "";

  if (/^\d+$/.test(text)) {
    return formatDurationSec(Number(text));
  }

  const parts = text.split(":").map((part) => part.trim());
  if (parts.some((part) => part === "" || Number.isNaN(Number(part)))) {
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
  const parts = normalized.split(":").map(Number);
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
  const startText = startRaw.trim();
  const endText = endRaw.trim();
  if (!startText && !endText) return null;
  const start = startText ? parseTimeInputSec(startText) : 0;
  if (startText && start === null) {
    return "Invalid start time";
  }
  if (duration > 0 && (start ?? 0) >= duration) {
    return `Start exceeds video length (${formatDurationSec(duration)})`;
  }

  if (!endText) {
    return null;
  }
  const end = parseTimeInputSec(endText);
  if (end === null) {
    return "Invalid end time";
  }
  if (duration > 0 && end > duration) {
    return `End exceeds video length (${formatDurationSec(duration)})`;
  }
  if (end <= (start ?? 0)) {
    return "End must be after start";
  }
  return null;
}

export type CutRangeInput = { start: string; end: string };

export function hasActiveCut(cut: CutRangeInput): boolean {
  return Boolean(cut.start.trim() || cut.end.trim());
}

export function validateCutRanges(
  durationSec: number | null | undefined,
  cuts: CutRangeInput[],
): string | null {
  for (let i = 0; i < cuts.length; i += 1) {
    const cut = cuts[i]!;
    if (!hasActiveCut(cut)) continue;
    const err = validateCutRange(durationSec, cut.start, cut.end);
    if (err) {
      return cuts.length > 1 ? `Cut ${i + 1}: ${err}` : err;
    }
  }
  return null;
}

export function splitCutFieldError(error: string): { start: string; end: string } {
  if (!error) return { start: "", end: "" };
  if (
    error.startsWith("Start") ||
    error === "Invalid start time" ||
    error.toLowerCase().includes("invalid time format")
  ) {
    return { start: error, end: "" };
  }
  if (error.startsWith("End") || error === "Invalid end time") {
    return { start: "", end: error };
  }
  if (error === "End must be after start") {
    return { start: error, end: error };
  }
  if (error.toLowerCase().includes("cut end must be after")) {
    return { start: error, end: error };
  }
  return { start: "", end: "" };
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
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/** Human-readable duration; omits zero-valued units (e.g. 90 → "1 min 30 sec"). */
export function formatDurationHuman(totalSec: number | null | undefined): string {
  const sec = Math.max(0, Math.floor(Number(totalSec) || 0));
  const hours = Math.floor(sec / 3600);
  const minutes = Math.floor((sec % 3600) / 60);
  const seconds = sec % 60;
  const parts: string[] = [];
  if (hours > 0) parts.push(`${hours} hr`);
  if (minutes > 0) parts.push(`${minutes} min`);
  if (seconds > 0 || parts.length === 0) parts.push(`${seconds} sec`);
  return parts.join(" ");
}

/** Clip length from cut range; null when unset, invalid, or not computable. */
export function cutClipDurationSec(
  durationSec: number | null | undefined,
  startRaw: string,
  endRaw: string,
): number | null {
  const startText = startRaw.trim();
  const endText = endRaw.trim();
  if (!startText && !endText) return null;
  if (validateCutRange(durationSec, startRaw, endRaw)) return null;

  const start = startText ? parseTimeInputSec(startText) : 0;
  if (start === null) return null;

  if (endText) {
    const end = parseTimeInputSec(endText);
    if (end === null || end <= start) return null;
    return end - start;
  }

  const duration = Math.floor(Number(durationSec) || 0);
  if (duration <= 0 || start >= duration) return null;
  return duration - start;
}

export function looksLikeSupportedUrl(value: string): boolean {
  const text = value.trim();
  if (!/^https?:\/\//i.test(text)) return false;
  try {
    const host = new URL(text).hostname.toLowerCase();
    return (
      host.includes("jable") ||
      host.includes("missav") ||
      host.includes("supjav") ||
      host.includes("hanime1") ||
      host.includes("jav.guru") ||
      host.includes("spankbang.com")
    );
  } catch {
    return false;
  }
}
