import type { JSX } from "solid-js";

type Props = {
  progress: number;
  children: JSX.Element;
  title?: string;
};

export default function ProgressRing(props: Props) {
  const pct = () => Math.max(0, Math.min(100, props.progress || 0));
  const radius = 19;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = () => circumference - (pct() / 100) * circumference;

  return (
    <div class="progress-ring" title={props.title || `${pct().toFixed(0)}%`}>
      <svg class="progress-ring-svg" viewBox="0 0 44 44" aria-hidden="true">
        <circle class="progress-ring-track" cx="22" cy="22" r={radius} />
        <circle
          class="progress-ring-fill"
          cx="22"
          cy="22"
          r={radius}
          stroke-dasharray={`${circumference} ${circumference}`}
          stroke-dashoffset={dashOffset()}
        />
      </svg>
      <div class="progress-ring-content">{props.children}</div>
    </div>
  );
}
