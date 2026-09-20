import { createEffect, createSignal, For, onCleanup, Show } from "solid-js";
import { SITES, type SiteInfo, siteFaviconSrc } from "../lib/sites";
import { ExternalLinkIcon, GlobeIcon } from "./IconButton";

function SiteFavicon(props: { site: SiteInfo }) {
  const [failed, setFailed] = createSignal(false);
  return (
    <Show
      when={!failed()}
      fallback={<span class="site-favicon site-favicon-fallback">{props.site.name.charAt(0)}</span>}
    >
      <img
        class="site-favicon"
        src={siteFaviconSrc(props.site.domain)}
        alt=""
        loading="lazy"
        onError={() => setFailed(true)}
      />
    </Show>
  );
}

export default function SupportedSites() {
  const [open, setOpen] = createSignal(false);

  function toggle() {
    setOpen((value) => !value);
  }

  function close() {
    setOpen(false);
  }

  function onDocClick(event: MouseEvent) {
    const target = event.target as Node | null;
    const root = document.getElementById("sites-menu-root");
    if (root && target && !root.contains(target)) {
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

  function openSite(site: SiteInfo) {
    window.open(site.url, "_blank", "noopener");
    close();
  }

  return (
    <div id="sites-menu-root" class="sites-menu">
      <button
        type="button"
        class="sites-menu-btn"
        classList={{ active: open() }}
        aria-label="Supported sites"
        aria-expanded={open()}
        title="Supported sites"
        onClick={toggle}
      >
        <GlobeIcon />
      </button>
      <Show when={open()}>
        <div class="sites-dropdown" role="menu">
          <div class="sites-header">
            <span class="sites-title">Supported sites</span>
            <span class="sites-count" title="Total supported sites">
              {SITES.length}
            </span>
          </div>
          <div class="sites-list">
            <For each={SITES}>
              {(site) => (
                <button
                  type="button"
                  class="site-row"
                  classList={{ pinned: site.pinned }}
                  role="menuitem"
                  aria-label={`Open ${site.name} in a new tab`}
                  onClick={() => openSite(site)}
                >
                  <SiteFavicon site={site} />
                  <span class="site-info">
                    <span class="site-name">
                      {site.name}
                      <Show when={site.pinned}>
                        <span class="site-chip">Ours</span>
                      </Show>
                    </span>
                    <span class="site-domain">{site.domain}</span>
                  </span>
                  <span class="site-open">
                    <ExternalLinkIcon />
                  </span>
                </button>
              )}
            </For>
          </div>
        </div>
      </Show>
    </div>
  );
}
