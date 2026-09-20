export type LogLevel = "error" | "warn" | "success" | "info";

const STAMP_RE = /^\[([^\]]+)\]\s*(.*)$/s;

/** Split a job log line into its `[stamp]` prefix and the message text. */
export function splitLogStamp(line: string): { stamp: string; message: string } {
  const match = STAMP_RE.exec(line ?? "");
  if (!match) return { stamp: "", message: line ?? "" };
  return { stamp: `[${match[1]}]`, message: match[2] ?? "" };
}

/**
 * Severity for a log message (stamp already stripped is fine either way).
 *
 * Ordered rules; the first match wins. Patterns mirror the messages the
 * backend actually emits (service.py + site crawlers).
 */
export function classifyLogLine(line: string): LogLevel {
  const text = splitLogStamp(line ?? "")
    .message.trim()
    .toLowerCase();
  if (!text) return "info";

  // User-initiated states first, so "Error: Download cancelled" stays amber.
  if (text.includes("cancelled") || text.includes("canceled")) return "warn";
  if (text === "download paused" || text.startsWith("download paused")) return "warn";

  // Mirror fallbacks are recoverable, not failures.
  if (text.startsWith("trying next")) return "warn";
  if (text.startsWith("resolving next mirror")) return "warn";
  if (text.startsWith("no remaining stream")) return "warn";

  // Cleanup sweep events.
  if (text.startsWith("cleanup complete")) return "success";
  if (text.startsWith("cleanup failed") || text.startsWith("scan failed")) return "error";
  if (text.startsWith("skipped") || text.startsWith("could not")) return "warn";

  if (/\berror\b|\bfailed\b|\bfatal\b|not found/.test(text)) return "error";

  if (text.startsWith("complete:")) return "success";

  return "info";
}
