import type { ResolveResult } from '../api';

type Props = {
  meta: ResolveResult;
};

export default function MetaCard(props: Props) {
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
          <p class="label">Save folder</p>
          <p class="mono">{props.meta.dest_folder || '—'}</p>
        </div>
      </div>
    </section>
  );
}
