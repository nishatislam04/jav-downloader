import { Show } from 'solid-js';
import type { Job } from '../api';
import { formatProgress } from '../lib/format';

type Props = {
  job: Job;
  onCancel?: (jobId: string) => void;
  cancelling?: boolean;
};

function progressText(job: Job): string {
  if (job.status === 'completed') {
    return job.output_file ? `Done: ${job.output_file}` : 'Download completed';
  }
  if (job.status === 'failed') {
    return job.error || 'Download failed';
  }
  return formatProgress(job);
}

export default function ProgressCard(props: Props) {
  const pct = () => props.job.progress_pct || 0;
  const barWidth = () => {
    const value = pct();
    if (value <= 0) return 0;
    return Math.max(value, 1.5);
  };
  const isActive = () =>
    props.job.status === 'pending' || props.job.status === 'downloading';

  return (
    <section class="card progress-card">
      <div class="progress-head">
        <p class="label">Progress</p>
        <Show when={isActive() && props.onCancel}>
          <button
            type="button"
            class="cancel-btn"
            disabled={props.cancelling}
            onClick={() => props.onCancel?.(props.job.id)}
          >
            Cancel
          </button>
        </Show>
      </div>
      <div class="progress-body">
        <div class="bar-track" aria-hidden="true">
          <div class="bar-fill" style={{ width: `${barWidth()}%` }} />
        </div>
        <p class="mono progress-text">{progressText(props.job)}</p>
      </div>
    </section>
  );
}
