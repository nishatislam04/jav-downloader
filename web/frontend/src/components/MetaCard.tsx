import { Show } from 'solid-js';
import type { ResolveResult } from '../api';
import { formatBytes } from '../lib/format';
import { formatDurationSec } from '../lib/time';
import ThumbnailPreview, { thumbnailSrc } from './ThumbnailPreview';

type Props = {
  meta: ResolveResult;
};

export default function MetaCard(props: Props) {
  const hasDuration = () => {
    const sec = props.meta.duration_sec;
    return !!sec && sec > 0;
  };

  const duration = () => formatDurationSec(props.meta.duration_sec ?? 0);
  const thumb = () => thumbnailSrc(props.meta.thumbnail || '');
  const hasSize = () => {
    const bytes = props.meta.output_size_bytes;
    return typeof bytes === 'number' && bytes > 0;
  };
  const sizeLabel = () => (props.meta.output_size_exact ? 'Size' : 'Est. size');
  const sizeText = () => formatBytes(props.meta.output_size_bytes ?? 0);

  return (
    <section class="card meta">
      <div class="meta-row">
        <Show when={thumb()}>
          <ThumbnailPreview src={thumb()} alt={props.meta.title || 'Video thumbnail'} />
        </Show>
        <div>
          <p class="label">Title</p>
          <p class="mono meta-title">{props.meta.title || '—'}</p>
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
          {props.meta.views ? (
            <>
              <p class="label">Views</p>
              <p>{props.meta.views}</p>
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
