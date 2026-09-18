import type { Job } from '../api';
import { formatProgress } from '../lib/format';

type Props = {
  job: Job;
};

export default function ProgressCard(props: Props) {
  const pct = () => props.job.progress_pct || 0;

  const progressText = () => {
    const job = props.job;
    if (job.status === 'completed') {
      return job.output_file ? `Done: ${job.output_file}` : 'Download completed';
    }
    if (job.status === 'failed') {
      return job.error || 'Download failed';
    }
    return formatProgress(job);
  };

  return (
    <section class="card">
      <p class="label">Progress</p>
      <div class="bar-track" aria-hidden="true">
        <div class="bar-fill" style={{ width: `${pct()}%` }} />
      </div>
      <p class="mono progress-text">{progressText()}</p>
    </section>
  );
}
