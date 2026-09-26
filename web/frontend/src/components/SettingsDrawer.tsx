import { createEffect, createSignal, onCleanup, Show } from "solid-js";
import { CloseIcon, SettingsIcon } from "./IconButton";

type Props = {
  hideThumbnails: boolean;
  onHideThumbnailsChange: (value: boolean) => void;
  saving?: boolean;
};

export default function SettingsDrawer(props: Props) {
  const [open, setOpen] = createSignal(false);

  function toggle() {
    setOpen((value) => !value);
  }

  function close() {
    setOpen(false);
  }

  function onDocClick(event: MouseEvent) {
    const target = event.target as Node | null;
    if (!target?.isConnected) return;
    const root = document.getElementById("settings-menu-root");
    if (root && !root.contains(target)) {
      close();
    }
  }

  function onDocKeyDown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
    }
  }

  createEffect(() => {
    if (!open()) return;
    document.addEventListener("click", onDocClick);
    document.addEventListener("keydown", onDocKeyDown);
    onCleanup(() => {
      document.removeEventListener("click", onDocClick);
      document.removeEventListener("keydown", onDocKeyDown);
    });
  });

  return (
    <div id="settings-menu-root" class="settings-menu">
      <button
        type="button"
        class="settings-menu-btn header-icon-btn"
        classList={{ active: open() }}
        aria-label="Settings"
        aria-expanded={open()}
        title="Settings"
        onClick={toggle}
      >
        <SettingsIcon />
      </button>
      <Show when={open()}>
        <div class="drawer-backdrop" aria-hidden="true" onClick={close} />
        <div class="settings-drawer" role="dialog" aria-label="Settings">
          <div class="settings-drawer-head">
            <p class="settings-drawer-title">Settings</p>
            <button
              type="button"
              class="settings-drawer-close"
              aria-label="Close settings"
              title="Close"
              onClick={close}
            >
              <CloseIcon />
            </button>
          </div>
          <div class="settings-drawer-body">
            <label class="settings-row">
              <input
                type="checkbox"
                checked={props.hideThumbnails}
                disabled={props.saving}
                onChange={(event) =>
                  props.onHideThumbnailsChange(event.currentTarget.checked)
                }
              />
              <span>Don&apos;t show thumbnail after metadata parse</span>
            </label>
          </div>
        </div>
      </Show>
    </div>
  );
}
