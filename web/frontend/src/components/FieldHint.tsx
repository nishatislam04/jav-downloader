import { createEffect, createSignal, type JSX, onCleanup, Show } from "solid-js";
import { Portal } from "solid-js/web";
import { InfoIcon } from "./IconButton";

type Props = {
  label: string;
  children: JSX.Element;
};

function isTouchUi() {
  if (typeof window === "undefined") return true;
  return !window.matchMedia("(hover: hover) and (pointer: fine)").matches;
}

export default function FieldHint(props: Props) {
  const [open, setOpen] = createSignal(false);
  let popover: HTMLDivElement | undefined;
  let suppressEventsUntil = 0;

  function close() {
    setOpen(false);
  }

  function toggle() {
    setOpen((value) => !value);
  }

  function swallowFollowUpInput() {
    suppressEventsUntil = Date.now() + 450;
  }

  function dismissFromOverlay(event: Event) {
    event.preventDefault();
    event.stopPropagation();
    swallowFollowUpInput();
    close();
  }

  createEffect(() => {
    if (!open()) return;

    function blockGhostInput(event: Event) {
      if (Date.now() >= suppressEventsUntil) return;
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
    }

    document.addEventListener("click", blockGhostInput, true);
    document.addEventListener("pointerup", blockGhostInput, true);
    onCleanup(() => {
      document.removeEventListener("click", blockGhostInput, true);
      document.removeEventListener("pointerup", blockGhostInput, true);
    });
  });

  createEffect(() => {
    if (!open() || isTouchUi()) return;

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") close();
    }

    document.addEventListener("keydown", onKeyDown);
    onCleanup(() => document.removeEventListener("keydown", onKeyDown));
  });

  createEffect(() => {
    if (!open() || !isTouchUi()) return;

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        swallowFollowUpInput();
        close();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    onCleanup(() => document.removeEventListener("keydown", onKeyDown));
  });

  const popoverContent = () => (
    <>
      <p class="field-hint-title">{props.label}</p>
      <div class="field-hint-body">{props.children}</div>
    </>
  );

  return (
    <div class="field-hint" classList={{ "field-hint-open": open() }}>
      <button
        type="button"
        class="field-hint-trigger"
        aria-label={`About ${props.label}`}
        aria-expanded={open()}
        onClick={(event) => {
          event.stopPropagation();
          toggle();
        }}
      >
        <InfoIcon />
      </button>
      <Show when={open()}>
        <Show
          when={isTouchUi()}
          fallback={
            <div
              class="field-hint-popover"
              ref={popover}
              role="tooltip"
              id={`field-hint-${props.label.replace(/\s+/g, "-").toLowerCase()}`}
            >
              {popoverContent()}
            </div>
          }
        >
          <Portal mount={document.body}>
            <div
              class="field-hint-backdrop"
              aria-hidden="true"
              onPointerDown={dismissFromOverlay}
              onClick={dismissFromOverlay}
            />
            <div
              class="field-hint-popover"
              ref={popover}
              role="dialog"
              aria-modal="true"
              aria-label={props.label}
              id={`field-hint-${props.label.replace(/\s+/g, "-").toLowerCase()}`}
              onPointerDown={(event) => event.stopPropagation()}
            >
              {popoverContent()}
            </div>
          </Portal>
        </Show>
      </Show>
    </div>
  );
}
