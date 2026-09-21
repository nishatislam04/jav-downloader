import { createEffect, createMemo, createSignal, Index, Show } from "solid-js";
import type { EncodingCapabilities, ResolveResult } from "../api";
import { validateFolder } from "../api";
import type {
  AudioBitrate,
  AudioSettings,
  EncodeCodec,
  EncodeEngine,
  EncodeMaxHeight,
  EncodeOutputMode,
  EncodePreset,
  EncodeSettings,
  HardwareBitrateMode,
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
  WrenchIcon,
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
  encodingCapabilities?: EncodingCapabilities | null;
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
      <button
        type="button"
        class="edit-tools-head"
        aria-expanded={!collapsed()}
        aria-label={collapsed() ? "Expand video tools" : "Collapse video tools"}
        title={collapsed() ? "Expand" : "Collapse"}
        onClick={() => setCollapsed((value) => !value)}
      >
        <span class="card-head-icon" aria-hidden="true">
          <WrenchIcon />
        </span>
        <p class="edit-tools-heading">Video tools</p>
        <span class="edit-tools-collapse-btn" aria-hidden="true">
          <Show when={collapsed()} fallback={<ChevronUpIcon />}>
            <ChevronDownIcon />
          </Show>
        </span>
      </button>
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
                              How much data is used for sound when the app needs to process audio
                              (for example after fade, loudness fix, or video re-encode). Higher
                              numbers usually sound clearer but make the file slightly larger.
                            </p>
                            <ul class="field-hint-list">
                              <li>
                                <strong>96k</strong> — Smallest audio size. Good for voice-only
                                clips or when you care more about saving space than perfect sound.
                              </li>
                              <li>
                                <strong>128k</strong> — Balanced everyday choice. Clear enough for
                                most videos; this is the default and what most people should use.
                              </li>
                              <li>
                                <strong>192k</strong> — Richer sound for music, ambience, or when
                                you notice muffled audio at 128k. Makes the file a bit bigger.
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
                              Makes quiet videos louder before saving. Useful when the original
                              sounds too soft even at full phone/TV volume.
                            </p>
                            <ul class="field-hint-list">
                              <li>
                                <strong>1.0× (left end)</strong> — No boost. Normal volume; choose
                                this unless the source is genuinely too quiet.
                              </li>
                              <li>
                                <strong>1.5×–2.0×</strong> — Moderate boost for slightly quiet
                                clips. A safe range to try first.
                              </li>
                              <li>
                                <strong>2.5×–3.0×</strong> — Strong boost for very quiet sources.
                                May distort if the original was already loud — listen after
                                download.
                              </li>
                            </ul>
                            <p>
                              If you also turn on “Normalize loudness”, that step runs after boost
                              and tries to keep a consistent overall level.
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
                          <FieldHint label="Video format (codec)">
                            <p>
                              The type of video compression used in the saved file. Pick based on
                              where you will watch it and how much storage you want to use.
                            </p>
                            <ul class="field-hint-list">
                              <li>
                                <strong>H.264</strong> — Works on almost every phone, TV, browser,
                                and media app. Slightly larger files. Choose this if you share files
                                widely or are unsure what your player supports. Best default for
                                most people.
                              </li>
                              <li>
                                <strong>H.265 / HEVC</strong> — Often produces noticeably smaller
                                files at similar picture quality. Takes longer to encode and some
                                older TVs, browsers, or apps cannot play it. Choose this when saving
                                space matters and you know your device supports HEVC.
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
                          <span>Max height</span>
                          <FieldHint label="Max height (resolution)">
                            <p>
                              Caps how tall the video can be in pixels. Lower resolution = smaller
                              file and faster processing. If the source is already smaller than your
                              choice, the app leaves it unchanged.
                            </p>
                            <ul class="field-hint-list">
                              <li>
                                <strong>Original</strong> — Keeps the same sharpness as the
                                downloaded stream. Choose when quality matters most or the source is
                                already low resolution. Default for most people.
                              </li>
                              <li>
                                <strong>480p</strong> — DVD-style size; fine on a phone screen and
                                very good for saving space. A popular choice for long videos.
                              </li>
                              <li>
                                <strong>720p</strong> — HD-ish balance: sharper than 480p but still
                                much smaller than full 1080p sources.
                              </li>
                              <li>
                                <strong>1080p</strong> — Full HD cap. Use when you want high
                                sharpness but the source might be 4K or very high bitrate.
                              </li>
                            </ul>
                          </FieldHint>
                        </div>
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
                          <span>Output</span>
                          <FieldHint label="Output file choice">
                            <p>
                              What happens to the original downloaded file after re-encoding
                              finishes.
                            </p>
                            <ul class="field-hint-list">
                              <li>
                                <strong>Replace original</strong> — The new compressed file takes
                                over; the first download version is removed. Keeps one clean
                                filename. Best default for most people.
                              </li>
                              <li>
                                <strong>Keep both</strong> — Saves the re-encoded file alongside the
                                original. Uses more disk space but lets you compare quality or keep
                                a backup.
                              </li>
                              <li>
                                <strong>Tagged file only</strong> — Keeps only the new file (with a
                                tag in the name) and deletes the original. Similar to “keep both”
                                but you end up with just the processed copy.
                              </li>
                            </ul>
                          </FieldHint>
                        </div>
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
                    </div>
                    <label class="toggle-row">
                      <input
                        type="checkbox"
                        checked={props.encodeSettings.advancedEnabled}
                        disabled={!props.encodeSettings.enabled}
                        onChange={(event) =>
                          props.onEncodeSettingsChange({
                            ...props.encodeSettings,
                            advancedEnabled: event.currentTarget.checked,
                          })
                        }
                      />
                      <span>Enable advanced encoding settings</span>
                    </label>
                    <Show
                      when={props.encodeSettings.advancedEnabled && props.encodeSettings.enabled}
                    >
                      <div class="encode-grid encode-grid-advanced">
                        <label class="encode-field encode-field-wide">
                          <div class="encode-field-head">
                            <span>Encoding engine</span>
                            <FieldHint label="Encoding engine">
                              <p>
                                How the app converts video after download — speed vs flexibility.
                                Only matters when re-encode is turned on.
                              </p>
                              <ul class="field-hint-list">
                                <li>
                                  <strong>Auto</strong> — Lets the app decide: skip work when
                                  nothing needs changing; use fast phone/GPU encoding when
                                  available; otherwise use standard software encoding. Recommended
                                  for almost everyone.
                                </li>
                                <li>
                                  <strong>Direct / Remux</strong> — Fastest path: copies video as-is
                                  when possible. Will not shrink resolution or change format. Choose
                                  only if you enabled re-encode but do not actually want visual
                                  changes.
                                </li>
                                <li>
                                  <strong>Hardware</strong> — Uses your device’s built-in video
                                  encoder (phone chip or PC graphics). Usually much faster and uses
                                  less battery/CPU. Falls back to software if unsupported.
                                </li>
                                <li>
                                  <strong>Software</strong> — Encodes on the main processor. Slower
                                  but predictable and works everywhere. Choose for maximum
                                  compatibility or if hardware results look bad on your device.
                                </li>
                              </ul>
                            </FieldHint>
                          </div>
                          <select
                            value={props.encodeSettings.engine}
                            onChange={(event) =>
                              props.onEncodeSettingsChange({
                                ...props.encodeSettings,
                                engine: event.currentTarget.value as EncodeEngine,
                              })
                            }
                          >
                            <option value="auto">Auto</option>
                            <option value="direct">Direct / Remux</option>
                            <option value="hardware">Hardware</option>
                            <option value="software">Software</option>
                          </select>
                        </label>
                        <label class="encode-field">
                          <div class="encode-field-head">
                            <span>Hardware codec</span>
                            <FieldHint label="Hardware video format">
                              <p>
                                Mirrors the main “Codec” choice above, but shows whether your
                                device’s fast hardware encoder supports each format. If an option
                                says “unavailable”, hardware mode cannot use it on this device.
                              </p>
                              <ul class="field-hint-list">
                                <li>
                                  <strong>H.264</strong> — Most compatible hardware path. Choose
                                  when you want speed and broad playback support.
                                </li>
                                <li>
                                  <strong>HEVC</strong> — Can save more space at similar quality
                                  when hardware supports it. Pick only if HEVC shows as available
                                  and your players handle HEVC files.
                                </li>
                              </ul>
                            </FieldHint>
                          </div>
                          <select value={props.encodeSettings.codec} disabled>
                            <option value="h264">
                              H.264
                              {props.encodingCapabilities?.hardware_codecs?.h264?.available
                                ? ""
                                : " (unavailable)"}
                            </option>
                            <option value="hevc">
                              HEVC
                              {props.encodingCapabilities?.hardware_codecs?.hevc?.available
                                ? ""
                                : " (unavailable)"}
                            </option>
                          </select>
                        </label>
                        <label class="encode-field">
                          <div class="encode-field-head">
                            <span>Hardware bitrate mode</span>
                            <FieldHint label="Hardware bitrate mode">
                              <p>
                                How strictly the hardware encoder sticks to a target data rate
                                (affects size and sometimes quality in busy scenes).
                              </p>
                              <ul class="field-hint-list">
                                <li>
                                  <strong>Auto (VBR)</strong> — Smart variable rate: spends more
                                  data on complex moments and less on simple ones. Best default for
                                  most people.
                                </li>
                                <li>
                                  <strong>VBR</strong> — Same idea as Auto: quality-first variable
                                  bitrate. Use if you want to force variable mode explicitly.
                                </li>
                                <li>
                                  <strong>CBR</strong> — Steady bitrate throughout. Predictable file
                                  size and streaming behavior; quality may dip in fast motion.
                                  Rarely needed unless you know you want constant rate.
                                </li>
                              </ul>
                            </FieldHint>
                          </div>
                          <select
                            value={props.encodeSettings.hardwareBitrateMode}
                            onChange={(event) =>
                              props.onEncodeSettingsChange({
                                ...props.encodeSettings,
                                hardwareBitrateMode: event.currentTarget
                                  .value as HardwareBitrateMode,
                              })
                            }
                          >
                            <option value="auto">Auto (VBR)</option>
                            <option value="vbr">VBR</option>
                            <option value="cbr">CBR</option>
                          </select>
                        </label>
                        <label class="encode-field">
                          <div class="encode-field-head">
                            <span>Hardware bitrate (kbps)</span>
                            <FieldHint label="Hardware bitrate (kbps)">
                              <p>
                                Target video data rate for hardware encoding. Think of it as a
                                “quality budget” — higher numbers look better but make larger files.
                              </p>
                              <ul class="field-hint-list">
                                <li>
                                  <strong>0 (Auto)</strong> — App picks a sensible rate from your
                                  resolution (for example ~1000k at 480p). Leave at 0 unless you
                                  know what you are doing. Default for most people.
                                </li>
                                <li>
                                  <strong>500–1000</strong> — Smaller files; okay for 480p or when
                                  space is tight.
                                </li>
                                <li>
                                  <strong>1500–3000</strong> — Mid range for 720p–1080p when you
                                  want cleaner picture without going huge.
                                </li>
                                <li>
                                  <strong>4000+</strong> — High quality / large files. Only if you
                                  have storage to spare and notice blockiness at lower values.
                                </li>
                              </ul>
                            </FieldHint>
                          </div>
                          <input
                            type="number"
                            min={0}
                            max={50000}
                            step={100}
                            class="mono"
                            value={props.encodeSettings.hardwareBitrateKbps}
                            onInput={(event) =>
                              props.onEncodeSettingsChange({
                                ...props.encodeSettings,
                                hardwareBitrateKbps: Math.max(
                                  0,
                                  Number(event.currentTarget.value) || 0,
                                ),
                              })
                            }
                          />
                        </label>
                        <label class="encode-field">
                          <div class="encode-field-head">
                            <span>GOP / keyframe interval</span>
                            <FieldHint label="Keyframe interval (GOP)">
                              <p>
                                How often the encoder saves a full picture frame (not just changes
                                from the previous frame). Affects scrubbing/seeking in players and
                                slightly affects file size.
                              </p>
                              <ul class="field-hint-list">
                                <li>
                                  <strong>0 (Auto)</strong> — App uses a safe default (~2 seconds
                                  between full frames). Leave this unless you have a specific reason
                                  to change it. Best for almost everyone.
                                </li>
                                <li>
                                  <strong>Lower values (e.g. 30)</strong> — More frequent full
                                  frames; smoother seeking, slightly larger files.
                                </li>
                                <li>
                                  <strong>Higher values (e.g. 120+)</strong> — Fewer full frames;
                                  may hitch when jumping through the timeline. Slightly smaller
                                  files. Uncommon for casual use.
                                </li>
                              </ul>
                            </FieldHint>
                          </div>
                          <input
                            type="number"
                            min={0}
                            max={600}
                            step={1}
                            class="mono"
                            value={props.encodeSettings.hardwareGop}
                            onInput={(event) =>
                              props.onEncodeSettingsChange({
                                ...props.encodeSettings,
                                hardwareGop: Math.max(0, Number(event.currentTarget.value) || 0),
                              })
                            }
                          />
                        </label>
                        <label class="encode-field">
                          <div class="encode-field-head">
                            <span>CRF {props.encodeSettings.crf}</span>
                            <FieldHint label="Software quality (CRF)">
                              <p>
                                Fine-tunes picture quality when using software encoding (not
                                hardware). Lower number = sharper picture and bigger file; higher
                                number = smaller file and more visible compression.
                              </p>
                              <ul class="field-hint-list">
                                <li>
                                  <strong>18–20</strong> — Very high quality; large files. For
                                  archiving or when you see banding at 23.
                                </li>
                                <li>
                                  <strong>21–23</strong> — Sweet spot for most downloads. 23 is the
                                  default — balanced size and clarity.
                                </li>
                                <li>
                                  <strong>24–26</strong> — Smaller files with acceptable quality on
                                  small screens.
                                </li>
                                <li>
                                  <strong>27–28</strong> — Aggressive space saving; may look soft or
                                  blocky on a big TV. Use when file size matters most.
                                </li>
                              </ul>
                            </FieldHint>
                          </div>
                          <input
                            type="range"
                            min={18}
                            max={28}
                            step={1}
                            value={props.encodeSettings.crf}
                            onInput={(event) =>
                              props.onEncodeSettingsChange({
                                ...props.encodeSettings,
                                crf: Number(event.currentTarget.value),
                              })
                            }
                          />
                        </label>
                        <label class="encode-field encode-field-wide">
                          <div class="encode-field-head">
                            <span>Software preset</span>
                            <FieldHint label="Software encoding speed">
                              <p>
                                Trade-off between how long software encoding takes and how tightly
                                the file is packed at the same quality setting above. Does not
                                change hardware encoding.
                              </p>
                              <ul class="field-hint-list">
                                <li>
                                  <strong>Auto</strong> — Picks a sensible speed for your device
                                  (faster on phones, balanced on desktop). Default — use this unless
                                  you have a reason to change.
                                </li>
                                <li>
                                  <strong>Ultrafast</strong> — Fastest; biggest files. Good for
                                  quick tests or very long videos when you are in a hurry.
                                </li>
                                <li>
                                  <strong>Superfast / Veryfast</strong> — Still quick; reasonable
                                  choice on slower phones or laptops.
                                </li>
                                <li>
                                  <strong>Faster / Fast</strong> — Middle ground: not too slow,
                                  slightly better compression than the fastest options.
                                </li>
                                <li>
                                  <strong>Medium</strong> — Balanced desktop encoding; good everyday
                                  choice if Auto feels too slow or too fast.
                                </li>
                                <li>
                                  <strong>Slow</strong> — Best compression for a given quality level
                                  but can take a long time. Only when you want smallest
                                  software-encoded files and can wait.
                                </li>
                              </ul>
                            </FieldHint>
                          </div>
                          <select
                            value={props.encodeSettings.preset}
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
                          <div class="encode-field-head">
                            <span>Threads</span>
                            <FieldHint label="CPU threads">
                              <p>
                                How many processor cores software encoding may use. Only affects
                                software mode — hardware encoding ignores this.
                              </p>
                              <ul class="field-hint-list">
                                <li>
                                  <strong>0 (Auto)</strong> — Uses all available cores for fastest
                                  software encode. Default and best for most people.
                                </li>
                                <li>
                                  <strong>1–2</strong> — Leaves headroom so your phone or PC stays
                                  responsive for other apps while encoding runs in the background.
                                </li>
                                <li>
                                  <strong>4+</strong> — Manual cap on multi-core use. Rarely needed;
                                  try only if Auto makes the device uncomfortably hot or sluggish.
                                </li>
                              </ul>
                            </FieldHint>
                          </div>
                          <input
                            type="number"
                            min={0}
                            max={128}
                            step={1}
                            class="mono"
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
                    </Show>
                    <p class="hint encode-hint">
                      Auto skips re-encoding when the source already matches your settings. Enable
                      advanced options for hardware, CRF, and preset control.
                    </p>
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
                      ref={(el) => queueMicrotask(() => el.focus())}
                      onInput={(event) => props.onCustomTitleChange(event.currentTarget.value)}
                    />
                  </Show>

                  <Show when={toolId() === "save"}>
                    <div class="save-path-field">
                      <FolderIcon />
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
