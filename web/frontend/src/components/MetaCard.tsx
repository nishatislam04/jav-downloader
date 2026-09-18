import type { ResolveResult } from '../api';
import { formatDurationSec } from '../lib/time';

type Props = {
  meta: ResolveResult;
};

export default function MetaCard(props: Props) {
  const duration = () => {
    const sec = props.meta.duration_sec;
    return sec && sec > 0 ? formatDurationSec(sec) : '—';
  };

  return (
    <section class="card meta">
      <div class="meta-row">
        {props.meta.thumbnail ? (
          <img src={props.meta.thumbnail} alt="" class="thumb" />
        ) : null}
        <div>
          <p class="label">Site</p>
          <p>{props.meta.site || '—'}</p>
          <p class="label">Title</p>
          <p>{props.meta.title || '—'}</p>
          <p class="label">Duration</p>
          <p>{duration()}</p>
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
          <p class="label">Save folder</p>
          <p class="mono">{props.meta.dest_folder || '—'}</p>
        </div>
      </div>
    </section>
  );
}
