import { Show } from 'solid-js';
import type { Job } from '../api';
import { formatProgress } from '../lib/format';
import IconButton, {
  CloseIcon,
  PauseIcon,
  PlayIcon,
  RetryIcon,
} from './IconButton';

type Props = {
  job: Job;
  onPause?: (jobId: string) => void;
  onResume?: (jobId: string) => void;
  onCancel?: (jobId: string) => void;
  onRetry?: () => void;
  actionBusy?: boolean;
};

function progressText(job: Job): string {
  if (job.status === 'completed') {
    return job.output_file ? `Done: ${job.output_file}` : 'Download completed';
  }
  if (job.status === 'paused') {
    return `Paused · ${formatProgress(job)}`;
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
  const isDownloading = () => props.job.status === 'downloading';
  const isPaused = () => props.job.status === 'paused';
  const isFailed = () => props.job.status === 'failed';
  const canRetry = () =>
    isFailed() && props.job.error !== 'Download cancelled';
  const showControls = () => isDownloading() || isPaused() || canRetry();

  return (
    <section class="card progress-card">
      <div class="progress-head">
        <p class="label">Progress</p>
        <Show when={showControls()}>
          <div class="progress-actions">
            <Show when={isDownloading() && props.onPause}>
              <IconButton
                label="Pause download"
                title="Pause"
                disabled={props.actionBusy}
                onClick={() => props.onPause?.(props.job.id)}
              >
                <PauseIcon />
              </IconButton>
            </Show>
            <Show when={isPaused() && props.onResume}>
              <IconButton
                label="Resume download"
                title="Resume"
                disabled={props.actionBusy}
                onClick={() => props.onResume?.(props.job.id)}
              >
                <PlayIcon />
              </IconButton>
            </Show>
            <Show when={canRetry() && props.onRetry}>
              <IconButton
                label="Retry download"
                title="Retry"
                disabled={props.actionBusy}
                onClick={() => props.onRetry?.()}
              >
                <RetryIcon />
              </IconButton>
            </Show>
            <Show when={(isDownloading() || isPaused()) && props.onCancel}>
              <IconButton
                label="Cancel download"
                title="Cancel"
                variant="danger"
                disabled={props.actionBusy}
                onClick={() => props.onCancel?.(props.job.id)}
              >
                <CloseIcon />
              </IconButton>
            </Show>
          </div>
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
