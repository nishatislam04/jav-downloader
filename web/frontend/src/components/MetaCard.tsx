import { createMemo, For, Show } from "solid-js";
import type { ResolveResult } from "../api";
import { formatBytes } from "../lib/format";
import { featuredMovieDetails, onlineStreamDetails } from "../lib/metaDetails";
import { formatDurationSec } from "../lib/time";
import { ExternalLinkIcon } from "./IconButton";
import ThumbnailPreview, { thumbnailSrc } from "./ThumbnailPreview";

type Props = {
  meta: ResolveResult;
  showThumbnail?: boolean;
};

export default function MetaCard(props: Props) {
  const hasDuration = () => {
    const sec = props.meta.duration_sec;
    return !!sec && sec > 0;
  };

  const duration = () => formatDurationSec(props.meta.duration_sec ?? 0);
  const thumb = () => thumbnailSrc(props.meta.thumbnail || "");
  const hasSize = () => {
    const bytes = props.meta.output_size_bytes;
    return typeof bytes === "number" && bytes > 0;
  };
  const sizeLabel = () => (props.meta.output_size_exact ? "Size" : "Est. size");
  const sizeText = () => formatBytes(props.meta.output_size_bytes ?? 0);
  const movieLine = createMemo(() => featuredMovieDetails(props.meta));
  const onlineLine = createMemo(() => onlineStreamDetails(props.meta));

  return (
    <section class="card meta">
      <div class="meta-row">
        <Show when={props.showThumbnail !== false && thumb()}>
          <ThumbnailPreview src={thumb()} alt={props.meta.title || "Video thumbnail"} />
        </Show>
        <div class="meta-info">
          <p class="mono meta-title">
            {props.meta.title || "—"}
            <Show when={props.meta.url}>
              <a
                class="meta-title-link"
                href={props.meta.url}
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Open video page in new tab"
                title="Open video page in new tab"
              >
                <ExternalLinkIcon />
              </a>
            </Show>
          </p>
          <Show when={movieLine().length}>
            <div class="meta-details-group">
              <For each={movieLine()}>
                {(row) => (
                  <div class="meta-detail-row">
                    <span class="meta-detail-key">{row.k}</span>
                    <span class="meta-detail-val">{row.v}</span>
                  </div>
                )}
              </For>
            </div>
          </Show>
          <Show when={onlineLine().length}>
            <div class="meta-details-group meta-details-group--online">
              <For each={onlineLine()}>
                {(row) => (
                  <div class="meta-detail-row">
                    <span class="meta-detail-key">{row.k}</span>
                    <span class="meta-detail-val">{row.v}</span>
                  </div>
                )}
              </For>
            </div>
          </Show>
          <Show when={hasDuration()}>
            <p class="label">Duration</p>
            <p class="mono meta-duration">{duration()}</p>
          </Show>
          <Show when={hasSize()}>
            <p class="label">{sizeLabel()}</p>
            <p class="mono">{sizeText()}</p>
          </Show>
          {props.meta.quality ? (
            <>
              <p class="label">Quality</p>
              <p>{props.meta.quality}</p>
            </>
          ) : null}
          {props.meta.uploader ? (
            <>
              <p class="label">Uploader</p>
              <p>{props.meta.uploader}</p>
            </>
          ) : null}
        </div>
      </div>
    </section>
  );
}
