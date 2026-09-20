import { onCleanup, onMount } from "solid-js";

type Props = {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  confirmClass?: string;
  onConfirm: () => void;
  onCancel: () => void;
};

export default function ConfirmDialog(props: Props) {
  let confirmButton: HTMLButtonElement | undefined;

  function onKeyDown(event: KeyboardEvent) {
    if (event.key !== "Escape") return;
    // Capture phase so the history menu's own Escape handler stays out.
    event.preventDefault();
    event.stopPropagation();
    props.onCancel();
  }

  onMount(() => {
    confirmButton?.focus();
    document.addEventListener("keydown", onKeyDown, true);
    onCleanup(() => document.removeEventListener("keydown", onKeyDown, true));
  });

  return (
    <div
      class="confirm-overlay"
      role="dialog"
      aria-modal="true"
      aria-label={props.title}
      onClick={(event) => {
        if (event.target === event.currentTarget) props.onCancel();
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape") props.onCancel();
      }}
    >
      <div class="confirm-dialog">
        <p class="confirm-title">{props.title}</p>
        <p class="confirm-message">{props.message}</p>
        <div class="confirm-actions">
          <button type="button" class="confirm-cancel" onClick={() => props.onCancel()}>
            {props.cancelLabel ?? "Cancel"}
          </button>
          <button
            type="button"
            class={props.confirmClass ?? "confirm-danger"}
            ref={confirmButton}
            onClick={() => props.onConfirm()}
          >
            {props.confirmLabel ?? "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}
