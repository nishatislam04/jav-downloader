import { createEffect, createMemo, createSignal, Index, Show } from "solid-js";
import type { ResolveResult } from "../api";
import { validateFolder } from "../api";
import type {
  AudioBitrate,
  AudioSettings,
  EncodeCodec,
  EncodeMaxHeight,
  EncodeOutputMode,
  EncodePreset,
  EncodeSettings,
} from "../lib/persist";
import {
  cutClipDurationSec,
  formatDurationHuman,
  hasActiveCut,
  splitCutFieldError,
  validateCutRange,
} from "../lib/time";
import FieldHint from "./FieldHint";
import {
  AudioIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  CutIcon,
  EncodeIcon,
  FolderIcon,
  RenameIcon,
} from "./IconButton";
import TimeField from "./TimeField";

export type ToolId = "cut" | "audio" | "encode" | "rename" | "save";

export type CutRange = {
  id: string;
  start: string;
  end: string;
};

export function newCutRange(): CutRange {
  return {
    id: randomId(),
    start: "",
    end: "",
  };
}

// crypto.randomUUID is unavailable on insecure origins (e.g. http://<lan-ip>)
// in some browsers, which blanked the app on Android/Termux.
function randomId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

type Props = {
  meta: ResolveResult;
  durationSec: number | null;
  cuts: CutRange[];
  customTitle: string;
  savePath: string;
  rememberSavePath: boolean;
  activeTool: ToolId | null;
  audioSettings: AudioSettings;
  rememberAudio: boolean;
  encodeSettings: EncodeSettings;
  rememberEncode: boolean;
  onCutChange: (id: string, field: "start" | "end", value: string) => void;
  onAddCut: () => void;
  onRemoveCut: (id: string) => void;
  onAudioSettingsChange: (value: AudioSettings) => void;
  onRememberAudioChange: (value: boolean) => void;
  onEncodeSettingsChange: (value: EncodeSettings) => void;
  onRememberEncodeChange: (value: boolean) => void;
  onCustomTitleChange: (value: string) => void;
  onSavePathChange: (path: string) => void;
  onRememberSavePathChange: (value: boolean) => void;
  onSelectTool: (tool: ToolId) => void;
  /** Per-tool modification counts rendered as badges; 0/undefined hides. */
  toolBadges?: Partial<Record<ToolId, number>>;
};

const BASE_TOOLS: Array<{
  id: ToolId;
  label: string;
  Icon: typeof CutIcon;
}> = [
  { id: "cut", label: "Cut", Icon: CutIcon },
  { id: "audio", label: "Audio", Icon: AudioIcon },
  { id: "encode", label: "Encode", Icon: EncodeIcon },
  { id: "rename", label: "Rename title", Icon: RenameIcon },
  { id: "save", label: "Save location", Icon: FolderIcon },
];

function rowDurationLabel(durationSec: number | null | undefined, cut: CutRange): string {
  const sec = cutClipDurationSec(durationSec, cut.start, cut.end);
  return sec === null ? "" : formatDurationHuman(sec);
}

function estimateAudioSizeMb(durationSec: number | null | undefined, bitrateKbps: number): string {
  if (!durationSec || durationSec <= 0) return "";
  const mb = (durationSec * bitrateKbps * 1000) / 8 / (1024 * 1024);
  return `~${mb.toFixed(0)} MB stereo`;
}

function rowFieldErrors(cut: CutRange, durationSec: number | null | undefined) {
  const err = hasActiveCut(cut) ? validateCutRange(durationSec, cut.start, cut.end) : null;
  if (!err) return { start: "", end: "" };
  return splitCutFieldError(err);
}

export default function EditToolsCard(props: Props) {
  const [pathError, setPathError] = createSignal("");
  const [draftPath, setDraftPath] = createSignal(props.savePath);
  const [collapsed, setCollapsed] = createSignal(false);

  createEffect(() => {
    setDraftPath(props.savePath);
  });

  async function applyPath() {
    const path = draftPath().trim();
    if (!path) return;

    setPathError("");
    const result = await validateFolder(path);
    if (!result.ok || !result.path) {
      setPathError(result.error || "Folder is not writable or does not exist");
      return;
    }
    setDraftPath(result.path);
    props.onSavePathChange(result.path);
    if (props.rememberSavePath) {
      props.onRememberSavePathChange(true);
    }
  }

  const activeMeta = () => visibleTools().find((tool) => tool.id === props.activeTool);
  const multiCut = () => props.cuts.length > 1;

  // Apply is only enabled while the draft differs from the applied path.
  const pathDirty = createMemo(() => draftPath().trim() !== props.savePath);

  const visibleTools = createMemo(() => [...BASE_TOOLS]);

  const totalDurationLabel = createMemo(() => {
    let total = 0;
    for (const cut of props.cuts) {
      const sec = cutClipDurationSec(props.durationSec, cut.start, cut.end);
      if (sec !== null) total += sec;
    }
    return total > 0 ? formatDurationHuman(total) : "";
  });

  return (
    <section class="card edit-tools">
      <div class="edit-tools-head">
        <p class="edit-tools-heading">Video tools</p>
        <button
          type="button"
          class="edit-tools-collapse-btn"
          aria-expanded={!collapsed()}
          aria-label={collapsed() ? "Expand video tools" : "Collapse video tools"}
          title={collapsed() ? "Expand" : "Collapse"}
          onClick={() => setCollapsed((value) => !value)}
        >
          <Show when={collapsed()} fallback={<ChevronUpIcon />}>
            <ChevronDownIcon />
          </Show>
        </button>
      </div>
      <Show when={!collapsed()}>
        <div class="edit-tools-layout">
          <nav class="edit-tools-sidebar" aria-label="Video tools">
            {visibleTools().map((tool) => (
              <button
                type="button"
                class={`tool-sidebar-btn ${props.activeTool === tool.id ? "active" : ""}`}
                aria-pressed={props.activeTool === tool.id}
                aria-label={
                  (props.toolBadges?.[tool.id] ?? 0) > 0
                    ? `${tool.label} (${props.toolBadges?.[tool.id]})`
                    : tool.label
                }
                title={tool.label}
                onClick={() => props.onSelectTool(tool.id)}
              >
                <tool.Icon />
                <span class="tool-label">{tool.label}</span>
                <Show when={(props.toolBadges?.[tool.id] ?? 0) > 0}>
                  <span class="tool-badge" aria-hidden="true">
                    {props.toolBadges?.[tool.id]}
                  </span>
                </Show>
              </button>
            ))}
          </nav>

          <div class="edit-tools-panel">
            <Show
              when={props.activeTool}
              fallback={
                <div class="tool-panel-empty">
                  <p class="tool-panel-title">Select a tool</p>
                  <p class="hint">Pick a tool from the left sidebar to edit download options.</p>
                </div>
              }
            >
              {(toolId) => (
                <>
                  <p class="tool-panel-title">{activeMeta()?.label}</p>

                  <Show when={toolId() === "cut"}>
                    <div class="cut-list">
                      <Index each={props.cuts}>
                        {(cut, index) => {
                          const errors = () => rowFieldErrors(cut(), props.durationSec);
                          const durationLabel = () => rowDurationLabel(props.durationSec, cut());

                          return (
                            <div class="cut-range-row">
                              <div class="cut-range-head">
                                <p class="cut-range-label">Cut {index + 1}</p>
                                <Show when={durationLabel()}>
                                  <span class="cut-duration">{durationLabel()}</span>
                                </Show>
                              </div>
                              <div class="cut-range-fields">
                                <TimeField
                                  id={`cut-${cut().id}-start`}
                                  label="Start"
                                  value={cut().start}
                                  error={errors().start}
                                  onChange={(value) => props.onCutChange(cut().id, "start", value)}
                                />
                                <TimeField
                                  id={`cut-${cut().id}-end`}
                                  label="End"
                                  value={cut().end}
                                  error={errors().end}
                                  onChange={(value) => props.onCutChange(cut().id, "end", value)}
                                />
                              </div>
                              <Show
                                when={multiCut()}
                                fallback={<div class="cut-remove-slot" aria-hidden="true" />}
                              >
                                <button
                                  type="button"
                                  class="cut-remove-btn"
                                  aria-label={`Remove cut ${index + 1}`}
                                  onClick={() => props.onRemoveCut(cut().id)}
                                >
                                  ×
                                </button>
                              </Show>
                            </div>
                          );
                        }}
                      </Index>
                    </div>
                    <div class="cut-actions">
                      <button
                        type="button"
                        class="cut-add-btn"
                        aria-label="Add another cut"
                        onClick={() => props.onAddCut()}
                      >
                        +
                      </button>
                      <Show when={totalDurationLabel() && multiCut()}>
                        <span class="cut-total-duration">Total {totalDurationLabel()}</span>
                      </Show>
                    </div>
                  </Show>

                  <Show when={toolId() === "audio"}>
                    <label class="toggle-row">
                      <input
                        type="checkbox"
                        checked={props.audioSettings.mute}
                        onChange={(event) =>
                          props.onAudioSettingsChange({
                            ...props.audioSettings,
                            mute: event.currentTarget.checked,
                          })
                        }
                      />
                      <span>Remove audio track (no audio in output)</span>
                    </label>
                    <div class="audio-grid" classList={{ disabled: props.audioSettings.mute }}>
                      <label class="encode-field">
                        <div class="encode-field-head">
                          <span>Bitrate</span>
                          <FieldHint label="Audio bitrate">
                            <p>
                              AAC bitrate when audio is re-encoded (fade, loudnorm, volume boost,
                              encode, or non-default bitrate).
                            </p>
                            <ul class="field-hint-list">
                              <li>
                                <strong>96k</strong> — Smallest audio; fine for speech.
                              </li>
                              <li>
                                <strong>128k</strong> — Default balance for most clips.
                              </li>
                              <li>
                                <strong>192k</strong> — Higher fidelity when music matters.
                              </li>
                            </ul>
                          </FieldHint>
                        </div>
                        <select
                          value={String(props.audioSettings.bitrate)}
                          disabled={props.audioSettings.mute}
                          onChange={(event) =>
                            props.onAudioSettingsChange({
                              ...props.audioSettings,
                              bitrate: Number(event.currentTarget.value) as AudioBitrate,
                            })
                          }
                        >
                          <option value="96">96k</option>
                          <option value="128">128k</option>
                          <option value="192">192k</option>
                        </select>
                        <Show
                          when={estimateAudioSizeMb(props.durationSec, props.audioSettings.bitrate)}
                        >
                          {(size) => <span class="audio-size-hint">{size()}</span>}
                        </Show>
                      </label>
                      <label class="encode-field">
                        <div class="encode-field-head">
                          <span>Volume boost {props.audioSettings.volume.toFixed(1)}×</span>
                          <FieldHint label="Volume boost">
                            <p>
                              Multiplies quiet source audio before other filters. Loudnorm afterward
                              still targets standard loudness — use boost only when the source is
                              too quiet.
                            </p>
                          </FieldHint>
                        </div>
                        <input
                          type="range"
                          min={1}
                          max={3}
                          step={0.1}
                          disabled={props.audioSettings.mute}
                          value={props.audioSettings.volume}
                          onInput={(event) =>
                            props.onAudioSettingsChange({
                              ...props.audioSettings,
                              volume: Number(event.currentTarget.value),
                            })
                          }
                        />
                      </label>
                    </div>
                    <label class="toggle-row" classList={{ disabled: props.audioSettings.mute }}>
                      <input
                        type="checkbox"
                        checked={props.audioSettings.fade}
                        disabled={props.audioSettings.mute}
                        onChange={(event) =>
                          props.onAudioSettingsChange({
                            ...props.audioSettings,
                            fade: event.currentTarget.checked,
                          })
                        }
                      />
                      <span>Fade in / out (0.5s at start and end)</span>
                    </label>
                    <label class="toggle-row" classList={{ disabled: props.audioSettings.mute }}>
                      <input
                        type="checkbox"
                        checked={props.audioSettings.loudnorm}
                        disabled={props.audioSettings.mute}
                        onChange={(event) =>
                          props.onAudioSettingsChange({
                            ...props.audioSettings,
                            loudnorm: event.currentTarget.checked,
                          })
                        }
                      />
                      <span>Normalize loudness</span>
                    </label>
                    <label class="remember-path">
                      <input
                        type="checkbox"
                        checked={props.rememberAudio}
                        onChange={(event) =>
                          props.onRememberAudioChange(event.currentTarget.checked)
                        }
                      />
                      <span>Remember choice</span>
                    </label>
                  </Show>

                  <Show when={toolId() === "encode"}>
                    <label class="toggle-row">
                      <input
                        type="checkbox"
                        checked={props.encodeSettings.enabled}
                        onChange={(event) =>
                          props.onEncodeSettingsChange({
                            ...props.encodeSettings,
                            enabled: event.currentTarget.checked,
                          })
                        }
                      />
                      <span>Re-encode after download (ffmpeg)</span>
                    </label>
                    <div class="encode-grid">
                      <label class="encode-field">
                        <div class="encode-field-head">
                          <span>Codec</span>
                          <FieldHint label="Codec">
                            <p>
                              Pick based on where you will play the file and how much space you want
                              to save.
                            </p>
                            <ul class="field-hint-list">
                              <li>
                                <strong>H.264</strong> — Plays on almost everything (phones, TVs,
                                browsers). Best when you share files or need maximum compatibility.
                              </li>
                              <li>
                                <strong>H.265 / HEVC</strong> — Roughly 30–50% smaller at the same
                                visual quality. Slower to encode and some older devices cannot play
                                it. Use when storage matters and your players support it.
                              </li>
                            </ul>
                          </FieldHint>
                        </div>
                        <select
                          value={props.encodeSettings.codec}
                          disabled={!props.encodeSettings.enabled}
                          onChange={(event) =>
                            props.onEncodeSettingsChange({
                              ...props.encodeSettings,
                              codec: event.currentTarget.value as EncodeCodec,
                            })
                          }
                        >
                          <option value="h264">H.264</option>
                          <option value="hevc">H.265 / HEVC</option>
                        </select>
                      </label>
                      <label class="encode-field">
                        <div class="encode-field-head">
                          <span>CRF {props.encodeSettings.crf}</span>
                          <FieldHint label="CRF (quality)">
                            <p>
                              Constant Rate Factor controls quality vs file size. Lower number =
                              higher quality and larger file.
                            </p>
                            <ul class="field-hint-list">
                              <li>
                                <strong>18–20</strong> — Very high quality, large files. Use for
                                archival or when you notice banding at 23.
                              </li>
                              <li>
                                <strong>23</strong> — Default sweet spot. Good balance for most
                                clips.
                              </li>
                              <li>
                                <strong>26–28</strong> — Smaller files with visible compression. Use
                                when size matters more than perfection.
                              </li>
                            </ul>
                          </FieldHint>
                        </div>
                        <input
                          type="range"
                          min={18}
                          max={28}
                          step={1}
                          disabled={!props.encodeSettings.enabled}
                          value={props.encodeSettings.crf}
                          onInput={(event) =>
                            props.onEncodeSettingsChange({
                              ...props.encodeSettings,
                              crf: Number(event.currentTarget.value),
                            })
                          }
                        />
                      </label>
                      <label class="encode-field">
                        <span>Max height</span>
                        <select
                          value={String(props.encodeSettings.maxHeight)}
                          disabled={!props.encodeSettings.enabled}
                          onChange={(event) =>
                            props.onEncodeSettingsChange({
                              ...props.encodeSettings,
                              maxHeight: Number(event.currentTarget.value) as EncodeMaxHeight,
                            })
                          }
                        >
                          <option value="0">Original</option>
                          <option value="480">480p</option>
                          <option value="720">720p</option>
                          <option value="1080">1080p</option>
                        </select>
                      </label>
                      <label class="encode-field encode-field-wide">
                        <div class="encode-field-head">
                          <span>Preset</span>
                          <FieldHint label="Encoding preset">
                            <p>
                              Controls encoder speed vs compression efficiency. Does not change
                              quality target (CRF does that) — it changes how hard ffmpeg works to
                              hit that quality.
                            </p>
                            <ul class="field-hint-list">
                              <li>
                                <strong>Auto</strong> — Veryfast on Termux / Android, medium on
                                desktop.
                              </li>
                              <li>
                                <strong>Ultrafast</strong> — Fastest encode, largest output. Good
                                for quick tests.
                              </li>
                              <li>
                                <strong>Superfast / Veryfast</strong> — Fast encodes when you are in
                                a hurry.
                              </li>
                              <li>
                                <strong>Faster / Fast</strong> — Reasonable speed with better
                                compression than the fastest presets.
                              </li>
                              <li>
                                <strong>Medium</strong> — Balanced default on desktop; good everyday
                                choice.
                              </li>
                              <li>
                                <strong>Slow</strong> — Best compression for a given CRF, but much
                                longer encode time.
                              </li>
                            </ul>
                          </FieldHint>
                        </div>
                        <select
                          value={props.encodeSettings.preset}
                          disabled={!props.encodeSettings.enabled}
                          onChange={(event) =>
                            props.onEncodeSettingsChange({
                              ...props.encodeSettings,
                              preset: event.currentTarget.value as EncodePreset,
                            })
                          }
                        >
                          <option value="auto">Auto</option>
                          <option value="ultrafast">Ultrafast</option>
                          <option value="superfast">Superfast</option>
                          <option value="veryfast">Veryfast</option>
                          <option value="faster">Faster</option>
                          <option value="fast">Fast</option>
                          <option value="medium">Medium</option>
                          <option value="slow">Slow</option>
                        </select>
                      </label>
                      <label class="encode-field">
                        <span>Output</span>
                        <select
                          value={props.encodeSettings.outputMode}
                          disabled={!props.encodeSettings.enabled}
                          onChange={(event) =>
                            props.onEncodeSettingsChange({
                              ...props.encodeSettings,
                              outputMode: event.currentTarget.value as EncodeOutputMode,
                            })
                          }
                        >
                          <option value="replace">Replace original</option>
                          <option value="keep_both">Keep both</option>
                          <option value="suffix">Tagged file only</option>
                        </select>
                      </label>
                      <label class="encode-field">
                        <span>Threads (0 = all cores)</span>
                        <input
                          type="number"
                          min={0}
                          max={128}
                          step={1}
                          class="mono"
                          disabled={!props.encodeSettings.enabled}
                          value={props.encodeSettings.threads}
                          onInput={(event) =>
                            props.onEncodeSettingsChange({
                              ...props.encodeSettings,
                              threads: Math.max(0, Number(event.currentTarget.value) || 0),
                            })
                          }
                        />
                      </label>
                    </div>
                    <p class="hint encode-hint">Software x264/x265 only — no hardware encode.</p>
                    <label class="remember-path">
                      <input
                        type="checkbox"
                        checked={props.rememberEncode}
                        onChange={(event) =>
                          props.onRememberEncodeChange(event.currentTarget.checked)
                        }
                      />
                      <span>Remember encode settings</span>
                    </label>
                  </Show>

                  <Show when={toolId() === "rename"}>
                    <textarea
                      id="output-title"
                      class="title-textarea mono"
                      rows={8}
                      autocomplete="off"
                      spellcheck={false}
                      placeholder={props.meta.title || "Video title"}
                      value={props.customTitle}
                      onInput={(event) => props.onCustomTitleChange(event.currentTarget.value)}
                    />
                  </Show>

                  <Show when={toolId() === "save"}>
                    <div class="save-path-field">
                      <input
                        id="save-path"
                        type="text"
                        class="mono save-path-input"
                        autocomplete="off"
                        spellcheck={false}
                        placeholder="/home/you/Documents/jav"
                        value={draftPath()}
                        onInput={(event) => {
                          setDraftPath(event.currentTarget.value);
                          setPathError("");
                        }}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") {
                            event.preventDefault();
                            void applyPath();
                          }
                        }}
                      />
                    </div>
                    <label class="remember-path">
                      <input
                        type="checkbox"
                        checked={props.rememberSavePath}
                        onChange={(event) =>
                          props.onRememberSavePathChange(event.currentTarget.checked)
                        }
                      />
                      <span>Remember choice</span>
                    </label>
                    <div class="save-path-actions">
                      <button
                        type="button"
                        class="tool-btn subtle save-apply-btn"
                        disabled={!pathDirty() || !draftPath().trim()}
                        onClick={() => void applyPath()}
                      >
                        Apply
                      </button>
                    </div>
                    <Show when={pathError()}>
                      <p class="time-error">{pathError()}</p>
                    </Show>
                  </Show>
                </>
              )}
            </Show>
          </div>
        </div>
      </Show>
    </section>
  );
}
