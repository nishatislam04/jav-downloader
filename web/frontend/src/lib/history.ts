export type HistoryEntry = {
  id: string;
  url: string;
  title: string;
  thumbnail: string;
  downloadedAt: number;
};

const STORAGE_KEY = "jav-downloader-history";
const MAX_ENTRIES = 40;

export function loadHistory(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as HistoryEntry[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveHistory(entries: HistoryEntry[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.slice(0, MAX_ENTRIES)));
}

export function appendHistory(entry: Omit<HistoryEntry, "id">): HistoryEntry[] {
  const next: HistoryEntry = { ...entry, id: randomId() };
  const merged = [next, ...loadHistory().filter((item) => item.url !== entry.url)].slice(
    0,
    MAX_ENTRIES,
  );
  saveHistory(merged);
  return merged;
}

export function deleteHistory(id: string): HistoryEntry[] {
  const merged = loadHistory().filter((item) => item.id !== id);
  saveHistory(merged);
  return merged;
}

export function clearHistory(): HistoryEntry[] {
  saveHistory([]);
  return [];
}

export function formatHistoryWhen(ms: number): string {
  return new Date(ms).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function cropHistoryTitle(title: string, max = 72): string {
  const text = title.trim() || "Untitled";
  return text.length <= max ? text : `${text.slice(0, max - 1)}…`;
}

// crypto.randomUUID is unavailable on insecure origins (e.g. http://<lan-ip>).
function randomId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}
