const REMEMBER_SAVE_PATH_KEY = "jav-downloader-remember-save-path";
const SAVE_PATH_KEY = "jav-downloader-save-path";
const REMEMBER_ENCODE_KEY = "jav-downloader-remember-encode";
const ENCODE_SETTINGS_KEY = "jav-downloader-encode-settings";
const REMEMBER_AUDIO_KEY = "jav-downloader-remember-audio";
const AUDIO_SETTINGS_KEY = "jav-downloader-audio-settings";

export type EncodeCodec = "h264" | "hevc";
export type EncodeMaxHeight = 0 | 480 | 720 | 1080;
export type EncodeOutputMode = "replace" | "keep_both" | "suffix";
export type EncodePreset =
  | "auto"
  | "ultrafast"
  | "superfast"
  | "veryfast"
  | "faster"
  | "fast"
  | "medium"
  | "slow";
export type EncodeEngine = "auto" | "direct" | "hardware" | "software";
export type HardwareBitrateMode = "auto" | "vbr" | "cbr";

export type EncodeSettings = {
  enabled: boolean;
  codec: EncodeCodec;
  crf: number;
  maxHeight: EncodeMaxHeight;
  outputMode: EncodeOutputMode;
  preset: EncodePreset;
  threads: number;
  advancedEnabled: boolean;
  engine: EncodeEngine;
  hardwareBitrateMode: HardwareBitrateMode;
  hardwareBitrateKbps: number;
  hardwareGop: number;
  smallFile: boolean;
};

export type AudioBitrate = 96 | 128 | 192;

export type AudioSettings = {
  fade: boolean;
  loudnorm: boolean;
  mute: boolean;
  bitrate: AudioBitrate;
  volume: number;
};

export const DEFAULT_AUDIO_SETTINGS: AudioSettings = {
  fade: false,
  loudnorm: false,
  mute: false,
  bitrate: 128,
  volume: 1,
};

export const DEFAULT_ENCODE_SETTINGS: EncodeSettings = {
  enabled: false,
  codec: "h264",
  crf: 23,
  maxHeight: 0,
  outputMode: "replace",
  preset: "auto",
  threads: 0,
  advancedEnabled: false,
  engine: "auto",
  hardwareBitrateMode: "auto",
  hardwareBitrateKbps: 0,
  hardwareGop: 0,
  smallFile: false,
};

export function normalizeEncodeSettings(raw: Partial<EncodeSettings> | null): EncodeSettings {
  const base = { ...DEFAULT_ENCODE_SETTINGS };
  if (!raw) return base;
  const codec = raw.codec === "hevc" ? "hevc" : "h264";
  const heights: EncodeMaxHeight[] = [0, 480, 720, 1080];
  const maxHeight = heights.includes(raw.maxHeight as EncodeMaxHeight)
    ? (raw.maxHeight as EncodeMaxHeight)
    : 0;
  const modes: EncodeOutputMode[] = ["replace", "keep_both", "suffix"];
  const outputMode = modes.includes(raw.outputMode as EncodeOutputMode)
    ? (raw.outputMode as EncodeOutputMode)
    : "replace";
  const presets: EncodePreset[] = [
    "auto",
    "ultrafast",
    "superfast",
    "veryfast",
    "faster",
    "fast",
    "medium",
    "slow",
  ];
  const preset = presets.includes(raw.preset as EncodePreset)
    ? (raw.preset as EncodePreset)
    : "auto";
  let crf = Number(raw.crf);
  if (!Number.isFinite(crf)) crf = base.crf;
  crf = Math.max(18, Math.min(28, Math.round(crf)));
  let threads = Number(raw.threads);
  if (!Number.isFinite(threads) || threads < 0) threads = 0;
  threads = Math.round(threads);
  const engines: EncodeEngine[] = ["auto", "direct", "hardware", "software"];
  const engine = engines.includes(raw.engine as EncodeEngine)
    ? (raw.engine as EncodeEngine)
    : "auto";
  const hwModes: HardwareBitrateMode[] = ["auto", "vbr", "cbr"];
  const hardwareBitrateMode = hwModes.includes(raw.hardwareBitrateMode as HardwareBitrateMode)
    ? (raw.hardwareBitrateMode as HardwareBitrateMode)
    : "auto";
  let hardwareBitrateKbps = Number(raw.hardwareBitrateKbps);
  if (!Number.isFinite(hardwareBitrateKbps) || hardwareBitrateKbps < 0) hardwareBitrateKbps = 0;
  hardwareBitrateKbps = Math.round(hardwareBitrateKbps);
  let hardwareGop = Number(raw.hardwareGop);
  if (!Number.isFinite(hardwareGop) || hardwareGop < 0) hardwareGop = 0;
  hardwareGop = Math.round(hardwareGop);
  return {
    enabled: Boolean(raw.enabled),
    codec,
    crf,
    maxHeight,
    outputMode,
    preset,
    threads,
    advancedEnabled: Boolean(raw.advancedEnabled),
    engine,
    hardwareBitrateMode,
    hardwareBitrateKbps,
    hardwareGop,
    smallFile: Boolean(raw.smallFile),
  };
}

export function loadRememberSavePath(): boolean {
  try {
    return localStorage.getItem(REMEMBER_SAVE_PATH_KEY) === "1";
  } catch {
    return false;
  }
}

export function loadSavedPath(): string {
  try {
    return localStorage.getItem(SAVE_PATH_KEY) || "";
  } catch {
    return "";
  }
}

/** Legacy localStorage hook; tool prefs persist via POST /api/settings. */
export function persistSavePath(_path: string, _remember: boolean): void {}

export function clearSavedPath(): void {
  persistSavePath("", false);
}

export function normalizeAudioSettings(raw: Partial<AudioSettings> | null): AudioSettings {
  if (!raw) return { ...DEFAULT_AUDIO_SETTINGS };
  const bitrates: AudioBitrate[] = [96, 128, 192];
  const bitrate = bitrates.includes(raw.bitrate as AudioBitrate)
    ? (raw.bitrate as AudioBitrate)
    : 128;
  let volume = Number(raw.volume ?? 1);
  if (!Number.isFinite(volume)) volume = 1;
  volume = Math.max(1, Math.min(3, Math.round(volume * 10) / 10));
  return {
    fade: Boolean(raw.fade),
    loudnorm: Boolean(raw.loudnorm),
    mute: Boolean(raw.mute),
    bitrate,
    volume,
  };
}

export function loadRememberAudio(): boolean {
  try {
    return localStorage.getItem(REMEMBER_AUDIO_KEY) === "1";
  } catch {
    return false;
  }
}

export function loadAudioSettings(): AudioSettings {
  try {
    const raw = localStorage.getItem(AUDIO_SETTINGS_KEY);
    if (!raw) return { ...DEFAULT_AUDIO_SETTINGS };
    return normalizeAudioSettings(JSON.parse(raw) as Partial<AudioSettings>);
  } catch {
    return { ...DEFAULT_AUDIO_SETTINGS };
  }
}

/** Legacy localStorage hook; tool prefs persist via POST /api/settings. */
export function persistAudioSettings(_settings: AudioSettings, _remember: boolean): void {}

export function loadRememberEncode(): boolean {
  try {
    return localStorage.getItem(REMEMBER_ENCODE_KEY) === "1";
  } catch {
    return false;
  }
}

export function loadEncodeSettings(): EncodeSettings {
  try {
    const raw = localStorage.getItem(ENCODE_SETTINGS_KEY);
    if (!raw) return { ...DEFAULT_ENCODE_SETTINGS };
    return normalizeEncodeSettings(JSON.parse(raw) as Partial<EncodeSettings>);
  } catch {
    return { ...DEFAULT_ENCODE_SETTINGS };
  }
}

/** Legacy localStorage hook; tool prefs persist via POST /api/settings. */
export function persistEncodeSettings(_settings: EncodeSettings, _remember: boolean): void {}
