import { formatDurationSec, normalizeTimeInput } from '../lib/time';

type Props = {
  id: string;
  label: string;
  value: string;
  placeholder?: string;
  hint?: string;
  error?: string;
  onChange: (value: string) => void;
  onBlurNormalize?: (value: string) => void;
};

export default function TimeField(props: Props) {
  return (
    <div class="time-field">
      <label for={props.id}>{props.label}</label>
      <input
        id={props.id}
        class={props.error ? 'input-error' : undefined}
        type="text"
        inputmode="numeric"
        autocomplete="off"
        spellcheck={false}
        placeholder={props.placeholder || '0:00'}
        value={props.value}
        onInput={(event) => props.onChange(event.currentTarget.value)}
        onBlur={(event) => {
          const normalized = normalizeTimeInput(event.currentTarget.value);
          props.onChange(normalized);
          props.onBlurNormalize?.(normalized);
        }}
      />
      {props.error ? <p class="time-error">{props.error}</p> : null}
      {props.hint ? <p class="time-hint">{props.hint}</p> : null}
    </div>
  );
}

export function durationHint(durationSec?: number | null): string {
  if (!durationSec || durationSec <= 0) return 'mm:ss or seconds';
  return `Full video ${formatDurationSec(durationSec)}`;
}
