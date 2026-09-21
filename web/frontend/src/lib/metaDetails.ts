import type { ResolveResult } from "../api";

export type MetaDetail = { k: string; v: string };

export function movieInformationDetails(meta: ResolveResult): MetaDetail[] {
  const rows: MetaDetail[] = [];
  if (meta.code?.trim()) rows.push({ k: "code", v: meta.code.trim() });
  if (meta.release_date?.trim()) rows.push({ k: "released", v: meta.release_date.trim() });
  if (meta.studio?.trim()) rows.push({ k: "studio", v: meta.studio.trim() });
  if (meta.label?.trim()) rows.push({ k: "label", v: meta.label.trim() });
  if (meta.actresses?.length) rows.push({ k: "actress", v: meta.actresses.join(", ") });
  if (meta.tags?.length) rows.push({ k: "tags", v: meta.tags.join(", ") });
  return rows;
}

export function onlineStreamDetails(meta: ResolveResult): MetaDetail[] {
  const rows: MetaDetail[] = [];
  if (meta.views?.trim()) rows.push({ k: "views", v: meta.views.trim() });
  if (meta.posted?.trim()) rows.push({ k: "posted", v: meta.posted.trim() });
  if (meta.stream_mirrors?.length) {
    rows.push({ k: "mirrors", v: meta.stream_mirrors.join(", ") });
  }
  return rows;
}

export function featuredMovieDetails(meta: ResolveResult): MetaDetail[] {
  const rows: MetaDetail[] = [];
  if (meta.release_date?.trim()) rows.push({ k: "released", v: meta.release_date.trim() });
  if (meta.actresses?.length) rows.push({ k: "actress", v: meta.actresses.join(", ") });
  return rows;
}
