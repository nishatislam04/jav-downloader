import type { JSX } from 'solid-js';

type Props = {
  label: string;
  title: string;
  disabled?: boolean;
  variant?: 'default' | 'danger';
  onClick?: () => void;
  children: JSX.Element;
};

export default function IconButton(props: Props) {
  return (
    <button
      type="button"
      class={`icon-btn ${props.variant === 'danger' ? 'icon-btn-danger' : ''}`}
      aria-label={props.label}
      title={props.title}
      disabled={props.disabled}
      onClick={() => props.onClick?.()}
    >
      {props.children}
    </button>
  );
}

export function PauseIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <rect x="6" y="5" width="4" height="14" rx="1" fill="currentColor" />
      <rect x="14" y="5" width="4" height="14" rx="1" fill="currentColor" />
    </svg>
  );
}

export function PlayIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <path d="M8 5v14l11-7z" fill="currentColor" />
    </svg>
  );
}

export function DownloadIcon() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
      <path
        d="M12 4v10m0 0l-4-4m4 4l4-4M5 20h14"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
  );
}

export function RetryIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <path
        d="M4 7V3m0 0h4M4 3l4 4m12-4v4m0-4h-4m4 4-4 4M4 17v4m0 0h4m-4 0 4-4m8 4v-4m0 4h-4m4 0-4-4"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
  );
}

export function CloseIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <path
        d="M6 6l12 12M18 6L6 18"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
      />
    </svg>
  );
}
