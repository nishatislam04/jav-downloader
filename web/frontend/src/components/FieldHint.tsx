import { createEffect, createSignal, type JSX, onCleanup, Show } from "solid-js";
import { InfoIcon } from "./IconButton";

type Props = {
  label: string;
  children: JSX.Element;
};

function supportsHover() {
  return (
    typeof window !== "undefined" && window.matchMedia("(hover: hover) and (pointer: fine)").matches
  );
}

export default function FieldHint(props: Props) {
  const [open, setOpen] = createSignal(false);
  let root: HTMLDivElement | undefined;
  let trigger: HTMLButtonElement | undefined;
  let popover: HTMLDivElement | undefined;

  function close() {
    setOpen(false);
  }

  function toggle() {
    setOpen((value) => !value);
  }

  createEffect(() => {
    if (!open()) return;

    function onPointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (!root?.contains(target)) {
        close();
        return;
      }
      // On mobile the full-screen backdrop sits inside root, and touch
      // taps can cancel click events — so key dismissal off pointerdown
      // for any tap that is neither the popover nor the trigger.
      if (!popover?.contains(target) && !trigger?.contains(target)) {
        close();
      }
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") close();
    }

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    onCleanup(() => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    });
  });

  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: hover-only wrapper; all interaction is on the trigger button
    <div
      class="field-hint"
      classList={{ "field-hint-open": open() }}
      ref={root}
      onMouseEnter={() => {
        if (supportsHover()) setOpen(true);
      }}
      onMouseLeave={() => {
        if (supportsHover()) setOpen(false);
      }}
    >
      <button
        type="button"
        class="field-hint-trigger"
        ref={trigger}
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
        <div class="field-hint-backdrop" aria-hidden="true" onClick={close} />
        <div
          class="field-hint-popover"
          ref={popover}
          role="tooltip"
          id={`field-hint-${props.label.replace(/\s+/g, "-").toLowerCase()}`}
        >
          <p class="field-hint-title">{props.label}</p>
          <div class="field-hint-body">{props.children}</div>
        </div>
      </Show>
    </div>
  );
}
