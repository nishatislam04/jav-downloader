import type { AppSettings } from "../api";
import { saveSettings } from "../api";
import {
  type AudioSettings,
  DEFAULT_AUDIO_SETTINGS,
  DEFAULT_ENCODE_SETTINGS,
  type EncodeSettings,
  loadAudioSettings,
  loadEncodeSettings,
  loadRememberAudio,
  loadRememberEncode,
  loadRememberSavePath,
  loadSavedPath,
  normalizeAudioSettings,
  normalizeEncodeSettings,
} from "./persist";

const MIGRATE_KEY = "jav-tool-settings-migrated-v1";

export type AppliedToolSettings = {
  hideThumbnails: boolean;
  historyGroupByUrl: boolean;
  rememberSavePath: boolean;
  savePath: string;
  rememberAudio: boolean;
  audioSettings: AudioSettings;
  rememberEncode: boolean;
  encodeSettings: EncodeSettings;
};

export function applyServerSettings(raw?: AppSettings | null): AppliedToolSettings {
  const out: AppliedToolSettings = {
    hideThumbnails: Boolean(raw?.hide_thumbnails),
    historyGroupByUrl: Boolean(raw?.history_group_by_url),
    rememberSavePath: Boolean(raw?.remember_save_path),
    savePath: String(raw?.save_path || "").trim(),
    rememberAudio: Boolean(raw?.remember_audio),
    audioSettings: raw?.remember_audio
      ? normalizeAudioSettings(raw.audio_settings ?? null)
      : { ...DEFAULT_AUDIO_SETTINGS },
    rememberEncode: Boolean(raw?.remember_encode),
    encodeSettings: raw?.remember_encode
      ? normalizeEncodeSettings(raw.encode_settings ?? null)
      : { ...DEFAULT_ENCODE_SETTINGS },
  };
  return out;
}

export function buildSettingsPatch(partial: {
  hideThumbnails?: boolean;
  historyGroupByUrl?: boolean;
  rememberSavePath?: boolean;
  savePath?: string;
  rememberAudio?: boolean;
  audioSettings?: AudioSettings;
  rememberEncode?: boolean;
  encodeSettings?: EncodeSettings;
}): AppSettings {
  const patch: AppSettings = {};
  if (partial.hideThumbnails !== undefined) {
    patch.hide_thumbnails = partial.hideThumbnails;
  }
  if (partial.historyGroupByUrl !== undefined) {
    patch.history_group_by_url = partial.historyGroupByUrl;
  }
  if (partial.rememberSavePath !== undefined) {
    patch.remember_save_path = partial.rememberSavePath;
  }
  if (partial.savePath !== undefined) {
    patch.save_path = partial.savePath.trim();
  }
  if (partial.rememberAudio !== undefined) {
    patch.remember_audio = partial.rememberAudio;
  }
  if (partial.audioSettings !== undefined) {
    patch.audio_settings = normalizeAudioSettings(partial.audioSettings);
  }
  if (partial.rememberEncode !== undefined) {
    patch.remember_encode = partial.rememberEncode;
  }
  if (partial.encodeSettings !== undefined) {
    patch.encode_settings = normalizeEncodeSettings(partial.encodeSettings);
  }
  return patch;
}

function clearLegacyLocalToolStorage(): void {
  const keys = [
    "jav-downloader-remember-save-path",
    "jav-downloader-save-path",
    "jav-downloader-remember-encode",
    "jav-downloader-encode-settings",
    "jav-downloader-remember-audio",
    "jav-downloader-audio-settings",
  ];
  try {
    for (const key of keys) {
      localStorage.removeItem(key);
    }
  } catch {
    // ignore
  }
}

/** One-time import from localStorage after upgrading to SQLite-backed settings. */
export async function migrateToolSettingsFromLocalStorage(): Promise<AppSettings | null> {
  try {
    if (sessionStorage.getItem(MIGRATE_KEY)) {
      return null;
    }
    sessionStorage.setItem(MIGRATE_KEY, "1");
  } catch {
    return null;
  }

  let hadLegacy = false;
  const patch: AppSettings = {};

  if (loadRememberSavePath()) {
    hadLegacy = true;
    patch.remember_save_path = true;
    patch.save_path = loadSavedPath();
  }
  if (loadRememberAudio()) {
    hadLegacy = true;
    patch.remember_audio = true;
    patch.audio_settings = loadAudioSettings();
  }
  if (loadRememberEncode()) {
    hadLegacy = true;
    patch.remember_encode = true;
    patch.encode_settings = loadEncodeSettings();
  }

  if (!hadLegacy) {
    return null;
  }

  const result = await saveSettings(patch);
  if (result.ok) {
    clearLegacyLocalToolStorage();
  }
  return result.settings ?? patch;
}
