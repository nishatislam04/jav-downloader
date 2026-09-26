import {
  createEffect,
  createMemo,
  createSignal,
  onCleanup,
  onMount,
  Show,
  untrack,
} from "solid-js";
import {
  cancelJob,
  cleanupJob,
  type EncodingCapabilities,
  fetchEncodingCapabilities,
  fetchHealth,
  fetchJob,
  type Job,
  pauseJob,
  type ResolveResult,
  resolveUrl,
  resumeJob,
  revealFile,
  startDownload,
  validateFolder,
} from "./api";
import ConfirmDialog from "./components/ConfirmDialog";
import EditToolsCard, { type CutRange, newCutRange, type ToolId } from "./components/EditToolsCard";
import HistoryMenu from "./components/HistoryMenu";
import {
  BrushIcon,
  CloseIcon,
  DownloadIcon,
  PlayIcon,
  SettingsIcon,
  SuccessIcon,
} from "./components/IconButton";
import MetaCard from "./components/MetaCard";
import ProgressCard from "./components/ProgressCard";
import ProgressRing from "./components/ProgressRing";
import SummaryCard from "./components/SummaryCard";
import SupportedSites from "./components/SupportedSites";
import { importLocalHistoryOnce } from "./lib/history";
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
  persistAudioSettings,
  persistEncodeSettings,
  persistSavePath,
} from "./lib/persist";
import { siteFaviconSrc, siteFromLabel } from "./lib/sites";
import {
  cutOutputSuffix,
  hasActiveCut,
  looksLikeSupportedUrl,
  stripCutOutputSuffix,
  validateCutRanges,
} from "./lib/time";

type ResolvePhase = "" | "metadata" | "updating";

function isCutRelatedError(message: string): boolean {
  const text = message.toLowerCase();
  return (
    text.includes("cut ") ||
    text.includes("time format") ||
    text.includes("invalid start") ||
    text.includes("invalid end") ||
    text.includes("exceeds video length")
  );
}

export default function App() {
  const [url, setUrl] = createSignal("");
  const [cuts, setCuts] = createSignal<CutRange[]>([newCutRange()]);
  const [defaultDownloadDir, setDefaultDownloadDir] = createSignal("");
  const [revealMode, setRevealMode] = createSignal<"open_file" | "show_in_folder">(
    "show_in_folder",
  );
  const [savePath, setSavePath] = createSignal("");
  const [savePathCustom, setSavePathCustom] = createSignal(false);
  const [rememberSavePath, setRememberSavePath] = createSignal(loadRememberSavePath());
  const [customTitle, setCustomTitle] = createSignal("");
  const [audioSettings, setAudioSettings] = createSignal<AudioSettings>(
    loadRememberAudio() ? loadAudioSettings() : { ...DEFAULT_AUDIO_SETTINGS },
  );
  const [rememberAudio, setRememberAudio] = createSignal(loadRememberAudio());
  const [encodeSettings, setEncodeSettings] = createSignal<EncodeSettings>(
    loadRememberEncode() ? loadEncodeSettings() : { ...DEFAULT_ENCODE_SETTINGS },
  );
  const [rememberEncode, setRememberEncode] = createSignal(loadRememberEncode());
  const [encodingCapabilities, setEncodingCapabilities] = createSignal<EncodingCapabilities | null>(
    null,
  );
  const [activeTool, setActiveTool] = createSignal<ToolId | null>(null);
  const [status, setStatus] = createSignal("");
  const [statusKind, setStatusKind] = createSignal<"ok" | "error" | "">("");
  const [resolvePhase, setResolvePhase] = createSignal<ResolvePhase>("");
  const [resolved, setResolved] = createSignal<ResolveResult | null>(null);
  const [job, setJob] = createSignal<Job | null>(null);
  const [busy, setBusy] = createSignal(false);
  const [resolving, setResolving] = createSignal(false);
  const [parseCancelled, setParseCancelled] = createSignal(false);
  const [actionBusy, setActionBusy] = createSignal(false);
  const [hasResolvedOnce, setHasResolvedOnce] = createSignal(false);
  const [downloadComplete, setDownloadComplete] = createSignal(false);
  const [completedRename, setCompletedRename] = createSignal("");
  const [serverCutError, setServerCutError] = createSignal("");
  const [pendingClear, setPendingClear] = createSignal(false);
  const [cleanupJobId, setCleanupJobId] = createSignal<string | null>(null);
  const [historyRefreshKey, setHistoryRefreshKey] = createSignal(0);
  const [historyDbWarning, setHistoryDbWarning] = createSignal("");

  let urlInput: HTMLInputElement | undefined;
  let pollTimer: ReturnType<typeof setInterval> | undefined;
  let resolveTimer: ReturnType<typeof setTimeout> | undefined;
  let editResolveTimer: ReturnType<typeof setTimeout> | undefined;
  let resolveRequest = 0;
  let resolveAbort: AbortController | undefined;

  onCleanup(() => {
    if (pollTimer) clearInterval(pollTimer);
    if (resolveTimer) clearTimeout(resolveTimer);
    if (editResolveTimer) clearTimeout(editResolveTimer);
  });

  onMount(async () => {
    urlInput?.focus();
    void importLocalHistoryOnce();
    const [health, caps] = await Promise.all([
      fetchHealth(),
      fetchEncodingCapabilities().catch(() => null),
    ]);
    if (caps?.ok) setEncodingCapabilities(caps);
    const downloadDir = health.download_dir || "";
    setDefaultDownloadDir(downloadDir);
    if (health.reveal_mode === "open_file" || health.reveal_mode === "show_in_folder") {
      setRevealMode(health.reveal_mode);
    }
    if (health.history_last_error) {
      setHistoryDbWarning(health.history_last_error);
    }

    if (rememberSavePath()) {
      const stored = loadSavedPath().trim();
      if (stored) {
        const result = await validateFolder(stored);
        if (result.ok && result.path) {
          setSavePath(result.path);
          setSavePathCustom(true);
          return;
        }
        persistSavePath("", false);
        setRememberSavePath(false);
      }
    }

    if (!savePathCustom()) {
      setSavePath(downloadDir);
    }
  });

  function resetEditTools() {
    setActiveTool(null);
    setCustomTitle("");
    setCuts([newCutRange()]);
    if (!rememberAudio()) {
      setAudioSettings({ ...DEFAULT_AUDIO_SETTINGS });
    }
    if (!rememberEncode()) {
      setEncodeSettings({ ...DEFAULT_ENCODE_SETTINGS });
    }
    if (!rememberSavePath()) {
      setSavePathCustom(false);
      setSavePath(defaultDownloadDir());
    }
    setHasResolvedOnce(false);
    setServerCutError("");
  }

  function clearTransientState() {
    setCuts([newCutRange()]);
    if (!rememberAudio()) {
      setAudioSettings({ ...DEFAULT_AUDIO_SETTINGS });
    }
    if (!rememberEncode()) {
      setEncodeSettings({ ...DEFAULT_ENCODE_SETTINGS });
    }
    setServerCutError("");
    setJob(null);
    setDownloadComplete(false);
    setCompletedRename("");
    setBusy(false);
    setStatusMessage("", "");
  }

  function setStatusMessage(text: string, kind: "ok" | "error" | "" = "") {
    setStatus(text);
    setStatusKind(kind);
  }

  const durationSec = () => resolved()?.duration_sec ?? null;

  const renameDisplayTitle = createMemo(() => {
    const suffix = cutOutputSuffix(cuts(), durationSec());
    const base = customTitle().trim() || resolved()?.title?.trim() || "";
    if (!suffix) {
      return customTitle();
    }
    return `${base}${suffix}`;
  });

  const cutValidation = createMemo(() => {
    const local = validateCutRanges(durationSec(), cuts());
    return local || serverCutError();
  });

  function activeCutsPayload() {
    return cuts()
      .filter(hasActiveCut)
      .map((cut) => ({
        start: cut.start.trim() || undefined,
        end: cut.end.trim() || undefined,
      }));
  }

  function resolvePayload(includeCuts = true) {
    const payload: {
      cuts?: Array<{ start?: string; end?: string }>;
      dest_folder?: string;
      output_title?: string;
      audio_fade?: boolean;
      audio_loudnorm?: boolean;
      audio_mute?: boolean;
      audio_bitrate?: number;
      audio_volume?: number;
      encode?: boolean;
      encode_codec?: string;
      encode_crf?: number;
      encode_max_height?: number;
      encode_output_mode?: string;
      encode_preset?: string;
      encode_threads?: number;
      encode_engine?: string;
      encode_hardware_bitrate_kbps?: number;
      encode_hardware_gop?: number;
      encode_hardware_bitrate_mode?: string;
      encode_small_file?: boolean;
    } = {};

    if (includeCuts && !validateCutRanges(durationSec(), cuts())) {
      const active = activeCutsPayload();
      if (active.length) payload.cuts = active;
    }

    const dest = savePath().trim();
    if (dest) payload.dest_folder = dest;

    const title = customTitle().trim();
    if (title) payload.output_title = title;

    const audio = audioSettings();
    if (audio.fade) payload.audio_fade = true;
    if (audio.loudnorm) payload.audio_loudnorm = true;
    if (audio.mute) payload.audio_mute = true;
    if (audio.bitrate !== 128) payload.audio_bitrate = audio.bitrate;
    if (audio.volume > 1) payload.audio_volume = audio.volume;
    const encode = encodeSettings();
    if (encode.enabled) {
      payload.encode = true;
      payload.encode_codec = encode.codec;
      payload.encode_max_height = encode.maxHeight;
      payload.encode_output_mode = encode.outputMode;
      if (encode.advancedEnabled) {
        payload.encode_crf = encode.crf;
        payload.encode_preset = encode.preset;
        payload.encode_threads = encode.threads;
        payload.encode_engine = encode.engine;
        if (encode.hardwareBitrateKbps > 0) {
          payload.encode_hardware_bitrate_kbps = encode.hardwareBitrateKbps;
        }
        if (encode.hardwareGop > 0) {
          payload.encode_hardware_gop = encode.hardwareGop;
        }
        if (encode.hardwareBitrateMode !== "auto") {
          payload.encode_hardware_bitrate_mode = encode.hardwareBitrateMode;
        }
        if (encode.smallFile) {
          payload.encode_small_file = true;
        }
      }
    }

    return payload;
  }

  async function runResolve(trigger: "url" | "cut" | "edit" = "url") {
    const value = url().trim();
    if (!looksLikeSupportedUrl(value)) {
      setResolved(null);
      setResolvePhase("");
      setResolving(false);
      if (!value) {
        resetEditTools();
        setStatusMessage("");
      }
      return;
    }

    const localCutError = validateCutRanges(durationSec(), cuts());
    if (localCutError && trigger === "cut") {
      setServerCutError("");
      setStatusMessage("", "");
      return;
    }

    const includeCuts = trigger === "cut" && !localCutError;
    const silent = trigger !== "url" && hasResolvedOnce();
    const requestId = ++resolveRequest;
    setParseCancelled(false);
    resolveAbort?.abort();
    const abort = new AbortController();
    resolveAbort = abort;
    if (!silent) {
      setResolving(true);
      setResolvePhase("metadata");
    }
    let data: ResolveResult;
    try {
      data = await resolveUrl(value, resolvePayload(includeCuts), abort.signal);
    } catch (error) {
      if (requestId !== resolveRequest) return;
      if (error instanceof DOMException && error.name === "AbortError") return;
      throw error;
    }
    if (requestId !== resolveRequest) return;
    if (!silent) {
      setResolving(false);
      setResolvePhase("");
    }

    if (!data.ok) {
      const message = data.error || "Resolve failed";
      if (hasResolvedOnce() && isCutRelatedError(message)) {
        setServerCutError(message);
        setStatusMessage("", "");
        return;
      }
      setResolved(null);
      setHasResolvedOnce(false);
      setStatusMessage(message, "error");
      return;
    }

    setResolved(data);
    setHasResolvedOnce(true);
    setServerCutError("");

    if (trigger === "url") {
      setActiveTool(null);
      setCustomTitle("");
      setCuts([newCutRange()]);
      if (!rememberAudio()) {
        setAudioSettings({ ...DEFAULT_AUDIO_SETTINGS });
      }
      if (!rememberEncode()) {
        setEncodeSettings({ ...DEFAULT_ENCODE_SETTINGS });
      }
      if (!rememberSavePath() && !savePathCustom()) {
        if (data.dest_folder) {
          setSavePath(data.dest_folder);
        }
      }
    }

    if (data.exists) {
      setStatusMessage("File already exists in the download folder.", "ok");
    } else {
      setStatusMessage("", "");
    }
  }

  function cancelResolve() {
    if (resolveTimer) clearTimeout(resolveTimer);
    if (editResolveTimer) clearTimeout(editResolveTimer);
    resolveRequest += 1;
    resolveAbort?.abort();
    setResolving(false);
    setResolvePhase("");
    setParseCancelled(true);
  }

  function startParse() {
    setParseCancelled(false);
    if (resolveTimer) clearTimeout(resolveTimer);
    if (editResolveTimer) clearTimeout(editResolveTimer);
    void runResolve("url");
  }

  function confirmClear() {
    setPendingClear(false);
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = undefined;
    setUrl("");
    setResolved(null);
    setResolving(false);
    setResolvePhase("");
    setParseCancelled(false);
    clearTransientState();
    resetEditTools();
    urlInput?.focus();
  }

  function scheduleResolve(trigger: "url" | "cut" | "edit" = "url") {
    if (resolveTimer) clearTimeout(resolveTimer);
    const delay = trigger === "url" ? 650 : 450;
    resolveTimer = setTimeout(() => {
      void runResolve(trigger);
    }, delay);
  }

  function scheduleEditResolve() {
    if (!hasResolvedOnce()) return;
    if (editResolveTimer) clearTimeout(editResolveTimer);
    editResolveTimer = setTimeout(() => {
      void runResolve("edit");
    }, 450);
  }

  createEffect(() => {
    const value = url();
    // Only url() should be tracked here. The helpers below read the
    // remember*() signals; tracking them would re-run this effect (and wipe
    // resolved state back to "Parse metadata") whenever a Remember toggle
    // changes.
    untrack(() => {
      if (!value.trim()) {
        setResolved(null);
        setResolving(false);
        setResolvePhase("");
        setParseCancelled(false);
        resetEditTools();
        return;
      }
      if (looksLikeSupportedUrl(value)) {
        setResolved(null);
        setResolving(true);
        setResolvePhase("metadata");
      }
      clearTransientState();
      setHasResolvedOnce(false);
      scheduleResolve("url");
    });
  });

  createEffect(() => {
    const rows = cuts();
    untrack(() => {
      setServerCutError("");
      if (rows.some(hasActiveCut)) {
        setDownloadComplete(false);
      }
      if (!rows.some(hasActiveCut)) return;
      if (validateCutRanges(durationSec(), rows)) return;
      if (!looksLikeSupportedUrl(url()) || !hasResolvedOnce()) return;
      scheduleResolve("cut");
    });
  });

  function handleCutChange(id: string, field: "start" | "end", value: string) {
    setCuts((prev) => prev.map((cut) => (cut.id === id ? { ...cut, [field]: value } : cut)));
  }

  function handleAddCut() {
    setCuts((prev) => [...prev, newCutRange()]);
  }

  function handleRemoveCut(id: string) {
    setCuts((prev) => {
      const next = prev.filter((cut) => cut.id !== id);
      return next.length ? next : [newCutRange()];
    });
  }

  function handleAudioSettingsChange(value: AudioSettings) {
    setAudioSettings(value);
    if (rememberAudio()) {
      persistAudioSettings(value, true);
    }
  }

  function handleRememberAudioChange(checked: boolean) {
    setRememberAudio(checked);
    if (checked) {
      persistAudioSettings(audioSettings(), true);
    } else {
      persistAudioSettings(audioSettings(), false);
    }
  }

  function handleEncodeSettingsChange(value: EncodeSettings) {
    setEncodeSettings(value);
    if (rememberEncode()) {
      persistEncodeSettings(value, true);
    }
  }

  function handleRememberEncodeChange(checked: boolean) {
    setRememberEncode(checked);
    if (checked) {
      persistEncodeSettings(encodeSettings(), true);
    } else {
      persistEncodeSettings(encodeSettings(), false);
    }
  }

  async function pollJob(jobId: string) {
    if (pollTimer) clearInterval(pollTimer);

    const tick = async () => {
      const data = await fetchJob(jobId);
      if (!data.ok || !data.job) return;
      setJob(data.job);
      if (data.job.status === "completed") {
        setDownloadComplete(true);
        setCompletedRename(customTitle().trim());
        setStatusMessage("", "");
        setBusy(false);
        setHistoryRefreshKey((n) => n + 1);
        if (pollTimer) clearInterval(pollTimer);
      } else if (data.job.status === "failed") {
        setStatusMessage(data.job.error || "Download failed", "error");
        setBusy(false);
        setDownloadComplete(false);
        setHistoryRefreshKey((n) => n + 1);
        if (pollTimer) clearInterval(pollTimer);
      } else if (data.job.status === "paused") {
        setBusy(false);
        setStatusMessage("Download paused.", "");
        setHistoryRefreshKey((n) => n + 1);
        if (pollTimer) clearInterval(pollTimer);
      }
    };

    await tick();
    pollTimer = setInterval(tick, 800);
  }

  async function handlePause(jobId: string) {
    setActionBusy(true);
    if (pollTimer) clearInterval(pollTimer);
    const data = await pauseJob(jobId);
    setActionBusy(false);
    if (!data.ok || !data.job) {
      setStatusMessage(data.error || "Could not pause download", "error");
      return;
    }
    setJob(data.job);
    setBusy(false);
    setStatusMessage("Download paused.", "");
  }

  async function handleResume(jobId: string) {
    setActionBusy(true);
    const data = await resumeJob(jobId);
    setActionBusy(false);
    if (!data.ok || !data.job) {
      setStatusMessage(data.error || "Could not resume download", "error");
      return;
    }
    setJob(data.job);
    setBusy(true);
    setDownloadComplete(false);
    setStatusMessage("Resuming download…");
    await pollJob(jobId);
  }

  async function handleCancel(jobId: string) {
    setCleanupJobId(jobId);
  }

  async function confirmCancelCleanup() {
    const jobId = cleanupJobId();
    setCleanupJobId(null);
    if (!jobId) return;
    setActionBusy(true);
    // Stop polling so ticks can't overwrite the cleanup status/log mid-sweep.
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = undefined;
    const data = await cancelJob(jobId);
    if (data.ok && data.job) {
      setJob(data.job);
    }
    setStatusMessage("Cleaning up partial files…", "");
    const sweep = await cleanupJob(jobId);
    // Pull the job again so the sweep's log lines show in the progress log.
    const refreshed = await fetchJob(jobId);
    if (refreshed.ok && refreshed.job) {
      setJob(refreshed.job);
    }
    setActionBusy(false);
    setBusy(false);
    setDownloadComplete(false);
    setJob(null);
    if (!sweep.ok) {
      setStatusMessage(sweep.error || "Download cancelled. Cleanup failed.", "error");
      return;
    }
    if (sweep.removed_dirs) {
      const label = sweep.removed_dirs === 1 ? "folder" : "folders";
      setStatusMessage(`Download cancelled. Removed ${sweep.removed_dirs} ${label}.`, "");
    } else {
      setStatusMessage("Download cancelled.", "");
    }
  }

  async function startDownloadJob() {
    const meta = resolved();
    const value = meta?.url || url().trim();
    if (!value) {
      setStatusMessage("Paste a supported URL first.", "error");
      return;
    }
    if (cutValidation()) {
      setActiveTool("cut");
      return;
    }
    if (!meta?.ok) {
      setStatusMessage("Waiting for metadata…", "error");
      return;
    }

    setBusy(true);
    setDownloadComplete(false);
    setStatusMessage("", "");
    const data = await startDownload(value, resolvePayload(true));
    if (!data.ok || !data.job) {
      const message = data.error || "Could not start download";
      if (isCutRelatedError(message)) {
        setServerCutError(message);
        setActiveTool("cut");
        setStatusMessage("", "");
      } else {
        setStatusMessage(message, "error");
      }
      setBusy(false);
      return;
    }

    setJob(data.job);
    await pollJob(data.job.id);
  }

  async function handleDownload() {
    const paused = job();
    if (paused?.status === "paused") {
      await handleResume(paused.id);
      return;
    }
    await startDownloadJob();
  }

  async function handleRetry() {
    await startDownloadJob();
  }

  async function handleReveal(path: string) {
    const result = await revealFile(path);
    if (!result.ok) {
      const detail = result.error || "Could not open file";
      setStatusMessage(
        `${detail} (Browser cannot open local files; Termux must launch a player.)`,
        "error",
      );
      return;
    }
    setStatusMessage(
      revealMode() === "open_file"
        ? "Launched opener — check app switcher for MX Player / chooser"
        : "Opening folder…",
      "ok",
    );
  }

  function selectTool(tool: ToolId) {
    setActiveTool(tool);
    if (tool === "rename" && !customTitle().trim()) {
      setCustomTitle(stripCutOutputSuffix(resolved()?.title || ""));
    }
  }

  function handleCustomTitleChange(value: string) {
    const base = stripCutOutputSuffix(value);
    setCustomTitle(base);
    setResolved((prev) => {
      if (!prev?.ok) return prev;
      return { ...prev, title: base || prev.title };
    });
    scheduleEditResolve();
  }

  function handleSavePathChange(path: string) {
    setSavePathCustom(true);
    setSavePath(path);
    if (rememberSavePath()) {
      persistSavePath(path, true);
    }
    scheduleEditResolve();
  }

  function handleRememberSavePathChange(checked: boolean) {
    setRememberSavePath(checked);
    if (checked) {
      const path = savePath().trim();
      if (path) {
        setSavePathCustom(true);
        persistSavePath(path, true);
      }
    } else {
      persistSavePath("", false);
    }
  }

  const urlUnsupported = createMemo(() => {
    const value = url().trim();
    return value.length > 0 && !looksLikeSupportedUrl(value);
  });

  const canDownload = createMemo(
    () =>
      !!resolved()?.ok && !cutValidation() && !busy() && !resolving() && job()?.status !== "paused",
  );

  // After completion, editing the title means the on-disk file no longer
  // matches the form — drop the success badge back to the download button.
  const showSuccess = createMemo(
    () => downloadComplete() && completedRename() === customTitle().trim(),
  );

  const showStartParse = createMemo(() => {
    const value = url().trim();
    return (
      parseCancelled() &&
      !resolving() &&
      !hasResolvedOnce() &&
      value.length > 0 &&
      looksLikeSupportedUrl(value)
    );
  });

  const progressPct = createMemo(() => {
    const current = job();
    if (!busy() || !current) return 0;
    return Math.max(0, Math.min(100, current.progress_pct ?? 0));
  });

  const progressTitle = createMemo(() => {
    const current = job();
    if (!current?.progress_phase) {
      return `Downloading ${progressPct().toFixed(0)}%`;
    }
    const detail = current.progress_detail?.trim();
    return detail ? `${current.progress_phase} · ${detail}` : current.progress_phase;
  });

  const resolveBadgeLabel = createMemo(() => {
    if (resolvePhase() === "metadata") return "Parse metadata";
    if (resolvePhase() === "updating") return "Update metadata";
    return "";
  });

  // Modification count per tool, shown as a badge on its sidebar icon.
  const toolBadges = createMemo(() => {
    const badges: Partial<Record<ToolId, number>> = {};
    const activeCuts = cuts().filter(hasActiveCut).length;
    if (activeCuts) badges.cut = activeCuts;
    const audio = audioSettings();
    const audioCount =
      (audio.fade ? 1 : 0) +
      (audio.loudnorm ? 1 : 0) +
      (audio.mute ? 1 : 0) +
      (audio.bitrate !== 128 ? 1 : 0) +
      (audio.volume > 1 ? 1 : 0);
    if (audioCount) badges.audio = audioCount;
    if (customTitle().trim()) badges.rename = 1;
    if (savePathCustom()) badges.save = 1;
    if (encodeSettings().enabled) badges.encode = 1;
    return badges;
  });

  const resolvedMeta = createMemo(() => {
    if (resolving()) return undefined;
    const meta = resolved();
    return meta?.ok ? meta : undefined;
  });

  const resolvedSite = createMemo(() => siteFromLabel(resolvedMeta()?.site));

  return (
    <main class="shell">
      <header class="app-header">
        <div class="app-title">
          <Show
            when={resolvedSite()}
            fallback={
              <img
                class="app-logo"
                src="/favicon.svg"
                alt="JAV Downloader"
                title="JAV Downloader"
              />
            }
          >
            {(site) => (
              <img
                class="app-logo"
                src={siteFaviconSrc(site().domain)}
                alt={site().name}
                title={site().name}
              />
            )}
          </Show>
          <h1>JAV Downloader</h1>
        </div>
        <div class="header-actions">
          <SupportedSites />
          <HistoryMenu
            refreshKey={historyRefreshKey()}
            onSelect={(entry) => setUrl(entry.url)}
          />
          <Show when={historyDbWarning()}>
            <p class="history-db-warning" title={historyDbWarning()}>
              History save issue — check server log
            </p>
          </Show>
          <button
            type="button"
            class="header-icon-btn"
            aria-label="Settings"
            title="Settings"
            onClick={() => {}}
          >
            <SettingsIcon />
          </button>
        </div>
      </header>

      <section class="card url-dashboard sticky-dashboard">
        <label for="url" class="url-label">
          <span>Video URL</span>
          <Show when={urlUnsupported()}>
            <span class="badge-unsupported">Unsupported</span>
          </Show>
          <Show when={resolving() && resolveBadgeLabel()}>
            <span class="badge-loading">
              <span class="spinner" aria-hidden="true" />
              {resolveBadgeLabel()}
              <button
                type="button"
                class="badge-cancel"
                aria-label="Cancel metadata parse"
                title="Cancel"
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  cancelResolve();
                }}
              >
                <CloseIcon />
              </button>
            </span>
          </Show>
          <Show when={showStartParse()}>
            <button
              type="button"
              class="badge-start"
              aria-label="Parse metadata"
              title="Parse metadata"
              onClick={(event) => {
                event.preventDefault();
                event.stopPropagation();
                startParse();
              }}
            >
              <PlayIcon />
              Parse metadata
            </button>
          </Show>
          <Show when={resolvedMeta()}>
            <div class="url-actions">
              <button
                type="button"
                class="url-action-btn"
                aria-label="Clear video URL"
                title="Clear URL"
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  setPendingClear(true);
                }}
              >
                <BrushIcon />
              </button>
            </div>
          </Show>
        </label>
        <div class="url-input-row">
          <input
            ref={urlInput}
            id="url"
            type="url"
            placeholder="Provide supported link to download video"
            autocomplete="off"
            spellcheck={false}
            value={url()}
            onInput={(event) => setUrl(event.currentTarget.value)}
            onFocus={(event) => {
              if (event.currentTarget.value) event.currentTarget.select();
            }}
          />
          <Show
            when={showSuccess()}
            fallback={
              <Show
                when={busy()}
                fallback={
                  <Show when={canDownload()}>
                    <button
                      type="button"
                      class="download-circle"
                      aria-label="Download"
                      title="Download"
                      onClick={handleDownload}
                    >
                      <DownloadIcon />
                    </button>
                  </Show>
                }
              >
                <ProgressRing progress={progressPct()} title={progressTitle()}>
                  <span class="progress-ring-label">{progressPct().toFixed(0)}%</span>
                </ProgressRing>
              </Show>
            }
          >
            <div
              class="success-circle"
              role="img"
              aria-label="Download complete"
              title="Download complete"
            >
              <SuccessIcon />
            </div>
          </Show>
        </div>

        <Show when={status() && !cutValidation()}>
          <p class={`status ${statusKind()}`} aria-live="polite">
            {status()}
          </p>
        </Show>
      </section>

      <Show when={resolvedMeta()}>
        {(meta) => (
          <>
            <MetaCard meta={meta()} />
            <EditToolsCard
              meta={meta()}
              durationSec={durationSec()}
              cuts={cuts()}
              customTitle={customTitle()}
              cutFilenameSuffix={cutOutputSuffix(cuts(), durationSec())}
              savePath={savePath()}
              rememberSavePath={rememberSavePath()}
              activeTool={activeTool()}
              audioSettings={audioSettings()}
              rememberAudio={rememberAudio()}
              encodeSettings={encodeSettings()}
              rememberEncode={rememberEncode()}
              encodingCapabilities={encodingCapabilities()}
              onCutChange={handleCutChange}
              onAddCut={handleAddCut}
              onRemoveCut={handleRemoveCut}
              onAudioSettingsChange={handleAudioSettingsChange}
              onRememberAudioChange={handleRememberAudioChange}
              onEncodeSettingsChange={handleEncodeSettingsChange}
              onRememberEncodeChange={handleRememberEncodeChange}
              onCustomTitleChange={handleCustomTitleChange}
              onSavePathChange={handleSavePathChange}
              onRememberSavePathChange={handleRememberSavePathChange}
              onSelectTool={selectTool}
              toolBadges={toolBadges()}
            />
            <SummaryCard
              meta={meta()}
              displayTitle={renameDisplayTitle()}
              destFolder={meta().dest_folder || defaultDownloadDir()}
              cuts={cuts()}
              customTitle={customTitle()}
              audioSettings={audioSettings()}
              encodeSettings={encodeSettings()}
            />
          </>
        )}
      </Show>

      <Show when={job()}>
        {(current) => (
          <ProgressCard
            job={current()}
            onPause={handlePause}
            onResume={handleResume}
            onCancel={handleCancel}
            onRetry={handleRetry}
            onReveal={handleReveal}
            revealMode={revealMode()}
            actionBusy={actionBusy()}
          />
        )}
      </Show>

      <Show when={pendingClear()}>
        <ConfirmDialog
          title="Clear video URL?"
          message="The link will be removed from the form."
          confirmLabel="Clear"
          onConfirm={confirmClear}
          onCancel={() => setPendingClear(false)}
        />
      </Show>

      <Show when={cleanupJobId()}>
        <ConfirmDialog
          title="Cancel download?"
          message="Partial files from this download will be removed from the save folder."
          confirmLabel="Cancel & clean up"
          onConfirm={confirmCancelCleanup}
          onCancel={() => setCleanupJobId(null)}
        />
      </Show>
    </main>
  );
}
