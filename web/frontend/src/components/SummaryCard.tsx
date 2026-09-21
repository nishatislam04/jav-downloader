import { createMemo, createSignal, For } from "solid-js";
import type { ResolveResult } from "../api";
import { formatBytes } from "../lib/format";
import { movieInformationDetails, onlineStreamDetails } from "../lib/metaDetails";
import type { AudioSettings, EncodeSettings } from "../lib/persist";
import { siteFromLabel } from "../lib/sites";
import { formatDurationSec } from "../lib/time";
import type { CutRange } from "./EditToolsCard";
import { ChevronDownIcon, ListIcon, WrapIcon } from "./IconButton";

type SummaryRow = { k: string; v: string };
type SummaryGroup = { title: string; rows: SummaryRow[] };

type Props = {
  meta: ResolveResult;
  displayTitle: string;
  destFolder: string;
  cuts: CutRange[];
  customTitle: string;
  audioSettings: AudioSettings;
  encodeSettings: EncodeSettings;
};

export default function SummaryCard(props: Props) {
  // Rows stay on one line (horizontal scroll) until wrap is toggled on
  const [wrapValues, setWrapValues] = createSignal(false);

  const videoRows = createMemo<SummaryRow[]>(() => {
    const m = props.meta;
    const rows: SummaryRow[] = [];
    if (props.displayTitle) rows.push({ k: "title", v: props.displayTitle });
    if (m.duration_sec && m.duration_sec > 0) {
      rows.push({ k: "duration", v: formatDurationSec(m.duration_sec) });
    }
    if (m.quality) rows.push({ k: "quality", v: m.quality });
    if (m.uploader) rows.push({ k: "uploader", v: m.uploader });
    if (typeof m.output_size_bytes === "number" && m.output_size_bytes > 0) {
      const k = m.output_size_exact ? "size" : "est. size";
      rows.push({ k, v: formatBytes(m.output_size_bytes) });
    }
    return rows;
  });

  const sourceRows = createMemo<SummaryRow[]>(() => {
    const m = props.meta;
    const rows: SummaryRow[] = [];
    const site = siteFromLabel(m.site);
    const siteName = site?.name || m.site || "";
    if (siteName) rows.push({ k: "site", v: siteName });
    if (m.url) rows.push({ k: "url", v: m.url });
    if (m.stream_type === "hls") {
      const tiers = m.hls_tiers ?? [];
      const parts = tiers.map((tier) =>
        tier.label === m.quality ? `\u25B8 ${tier.label}` : tier.label,
      );
      rows.push({
        k: "stream",
        v: parts.length ? `HLS ${parts.join("  ")}` : "HLS",
      });
    } else if (m.stream_type === "mp4") {
      rows.push({ k: "stream", v: "MP4 direct" });
    }
    return rows;
  });

  const destRows = createMemo<SummaryRow[]>(() => {
    const rows: SummaryRow[] = [];
    if (props.destFolder) rows.push({ k: "folder", v: props.destFolder });
    if (props.meta.exists) rows.push({ k: "file", v: "already in folder" });
    return rows;
  });

  const toolRows = createMemo<SummaryRow[]>(() => {
    const rows: SummaryRow[] = [];
    const title = props.customTitle.trim();
    if (title) rows.push({ k: "rename", v: title });

    const cuts = props.cuts.filter((cut) => cut.start.trim() || cut.end.trim());
    if (cuts.length) {
      const v = cuts
        .map((cut) => `${cut.start.trim() || "0:00"} \u2192 ${cut.end.trim() || "end"}`)
        .join("  ");
      rows.push({ k: "cuts", v });
    }

    const a = props.audioSettings;
    const audio: string[] = [];
    if (a.mute) audio.push("muted");
    if (a.fade) audio.push("fade");
    if (a.loudnorm) audio.push("loudnorm");
    if (a.bitrate !== 128) audio.push(`${a.bitrate}k`);
    if (a.volume > 1) audio.push(`vol ${a.volume}x`);
    if (audio.length) rows.push({ k: "audio", v: audio.join(", ") });

    const e = props.encodeSettings;
    if (e.enabled) {
      const parts: string[] = [e.codec];
      parts.push(e.maxHeight === 0 ? "full height" : `${e.maxHeight}p`);
      if (e.outputMode !== "replace")
        parts.push(e.outputMode === "keep_both" ? "keep both" : "suffix");
      if (e.advancedEnabled) {
        if (e.engine !== "auto") parts.push(e.engine);
        parts.push(`crf ${e.crf}`);
        if (e.preset !== "auto") parts.push(e.preset);
        if (e.threads > 0) parts.push(`${e.threads} threads`);
        if (e.hardwareBitrateKbps > 0) parts.push(`${e.hardwareBitrateKbps}k bitrate`);
        if (e.hardwareGop > 0) parts.push(`gop ${e.hardwareGop}`);
        if (e.hardwareBitrateMode !== "auto") parts.push(e.hardwareBitrateMode);
      }
      rows.push({ k: "encode", v: parts.join(", ") });
    }

    if (!rows.length) rows.push({ k: "tools", v: "defaults \u2014 nothing changed" });
    return rows;
  });

  const movieInfoRows = createMemo<SummaryRow[]>(() =>
    movieInformationDetails(props.meta).map((row) => ({ k: row.k, v: row.v })),
  );

  const onlineRows = createMemo<SummaryRow[]>(() =>
    onlineStreamDetails(props.meta).map((row) => ({ k: row.k, v: row.v })),
  );

  const groups = createMemo<SummaryGroup[]>(() => {
    const out: SummaryGroup[] = [];
    const video = videoRows();
    if (video.length) out.push({ title: "Video", rows: video });
    const movie = movieInfoRows();
    if (movie.length) out.push({ title: "Movie information", rows: movie });
    const online = onlineRows();
    if (online.length) out.push({ title: "Online stream", rows: online });
    const source = sourceRows();
    if (source.length) out.push({ title: "Source", rows: source });
    const dest = destRows();
    if (dest.length) out.push({ title: "Destination", rows: dest });
    out.push({ title: "Tools", rows: toolRows() });
    return out;
  });

  return (
    <section class="card summary-card">
      <details class="summary-details">
        <summary>
          <span class="card-head-icon" aria-hidden="true">
            <ListIcon />
          </span>
          <span class="summary-heading">Overview</span>
          <span class="summary-caret" aria-hidden="true" style={{ "margin-left": "auto" }}>
            <ChevronDownIcon />
          </span>
        </summary>
        <div class="summary-body">
          <div class="summary-toolbar">
            <button
              type="button"
              class="summary-wrap-btn"
              aria-pressed={wrapValues()}
              title={wrapValues() ? "Don't wrap long values" : "Wrap long values"}
              onClick={() => setWrapValues((value) => !value)}
            >
              <WrapIcon />
              {wrapValues() ? "No wrap" : "Wrap"}
            </button>
          </div>
          <For each={groups()}>
            {(group) => (
              <div class="summary-group">
                <p class="summary-group-title">{group.title}</p>
                <For each={group.rows}>
                  {(row) => (
                    <p class="summary-row">
                      <span class="summary-key">{row.k}</span>
                      <span class="summary-val" classList={{ wrap: wrapValues() }}>
                        {row.v}
                      </span>
                    </p>
                  )}
                </For>
              </div>
            )}
          </For>
        </div>
      </details>
    </section>
  );
}
