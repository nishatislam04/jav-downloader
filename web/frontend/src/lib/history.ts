import { clearHistoryApi, deleteHistoryEntry, fetchHistory, importHistoryEntries } from "../api";

export type HistoryEntry = {
  id: string;
  url: string;
  title: string;
  thumbnail: string;
  downloadedAt: number;
  status?: string;
  updatedAt?: number;
};

const LEGACY_STORAGE_KEY = "jav-downloader-history";

export async function loadHistoryFromServer(
  offset = 0,
  limit = HISTORY_PAGE_SIZE,
): Promise<{ entries: HistoryEntry[]; total: number; hasMore: boolean }> {
  return loadHistoryPage(offset, limit);
}

export async function deleteHistoryOnServer(
  id: string,
): Promise<{ entries: HistoryEntry[]; total: number; hasMore: boolean }> {
  await deleteHistoryEntry(id);
  return loadHistoryFromServer(0);
}

export async function clearHistoryOnServer(): Promise<{
  entries: HistoryEntry[];
  total: number;
  hasMore: boolean;
}> {
  await clearHistoryApi();
  return loadHistoryFromServer(0);
}

export async function importLocalHistoryOnce(): Promise<void> {
  let raw: string | null = null;
  try {
    raw = localStorage.getItem(LEGACY_STORAGE_KEY);
  } catch {
    return;
  }
  if (!raw) return;
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed) || parsed.length === 0) return;
    const result = await importHistoryEntries(parsed as HistoryEntry[]);
    if (result.ok) {
      localStorage.removeItem(LEGACY_STORAGE_KEY);
    }
  } catch {
    // Keep legacy data if import fails.
  }
}

export function formatHistoryWhen(ts: number): string {
  const ms = ts > 1e12 ? ts : ts * 1000;
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

export const HISTORY_PAGE_SIZE = 40;

export type HistoryGroup = {
  url: string;
  latest: HistoryEntry;
  count: number;
  runs: HistoryEntry[];
};

export function groupHistoryEntries(entries: HistoryEntry[]): HistoryGroup[] {
  const order: string[] = [];
  const map = new Map<string, HistoryEntry[]>();
  for (const entry of entries) {
    const key = entry.url.trim() || entry.id;
    if (!map.has(key)) {
      map.set(key, []);
      order.push(key);
    }
    map.get(key)?.push(entry);
  }
  return order.map((url) => {
    const runs = map.get(url) || [];
    const latest = runs[0];
    return { url, latest, count: runs.length, runs };
  });
}

export async function loadHistoryPage(
  offset: number,
  limit = HISTORY_PAGE_SIZE,
): Promise<{ entries: HistoryEntry[]; total: number; hasMore: boolean }> {
  const data = await fetchHistory(limit, offset);
  if (!data.ok || !Array.isArray(data.entries)) {
    return { entries: [], total: 0, hasMore: false };
  }
  return {
    entries: data.entries,
    total: data.total ?? data.entries.length,
    hasMore: Boolean(data.has_more),
  };
}

export function historyStatusLabel(status: string | undefined): string {
  const value = (status || "").trim().toLowerCase();
  if (!value || value === "completed") return "";
  if (value === "failed") return "Failed";
  if (value === "paused") return "Paused";
  if (value === "downloading") return "In progress";
  if (value === "pending") return "Pending";
  return value;
}
