import {
	createEffect,
	createMemo,
	createSignal,
	For,
	Index,
	Show,
} from "solid-js";
import type { ResolveResult } from "../api";
import { validateFolder } from "../api";
import {
	cutClipDurationSec,
	formatDurationHuman,
	hasActiveCut,
	splitCutFieldError,
	validateCutRange,
} from "../lib/time";
import {
	AudioIcon,
	CutIcon,
	FolderIcon,
	QualityIcon,
	RenameIcon,
	StreamIcon,
} from "./IconButton";
import TimeField from "./TimeField";

export type ToolId = "cut" | "audio" | "stream" | "quality" | "rename" | "save";

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
	if (
		typeof crypto !== "undefined" &&
		typeof crypto.randomUUID === "function"
	) {
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
	audioFade: boolean;
	audioLoudnorm: boolean;
	streamMirrors: string[];
	activeStream: string;
	hlsTiers: NonNullable<ResolveResult["hls_tiers"]>;
	activeHlsTier: string;
	onCutChange: (id: string, field: "start" | "end", value: string) => void;
	onAddCut: () => void;
	onRemoveCut: (id: string) => void;
	onAudioFadeChange: (value: boolean) => void;
	onAudioLoudnormChange: (value: boolean) => void;
	onStreamPreferenceChange: (label: string) => void;
	onTryNextStream: () => void;
	onHlsTierChange: (tierId: string) => void;
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
	{ id: "rename", label: "Rename title", Icon: RenameIcon },
	{ id: "save", label: "Save location", Icon: FolderIcon },
];

function rowDurationLabel(
	durationSec: number | null | undefined,
	cut: CutRange,
): string {
	const sec = cutClipDurationSec(durationSec, cut.start, cut.end);
	return sec === null ? "" : formatDurationHuman(sec);
}

function rowFieldErrors(cut: CutRange, durationSec: number | null | undefined) {
	const err = hasActiveCut(cut)
		? validateCutRange(durationSec, cut.start, cut.end)
		: null;
	if (!err) return { start: "", end: "" };
	return splitCutFieldError(err);
}

export default function EditToolsCard(props: Props) {
	const [pathError, setPathError] = createSignal("");
	const [draftPath, setDraftPath] = createSignal(props.savePath);

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

	const activeMeta = () =>
		visibleTools().find((tool) => tool.id === props.activeTool);
	const multiCut = () => props.cuts.length > 1;

	// Apply is only enabled while the draft differs from the applied path.
	const pathDirty = createMemo(() => draftPath().trim() !== props.savePath);

	const visibleTools = createMemo(() => {
		const items = [...BASE_TOOLS];
		let insertAt = 2;
		if (props.hlsTiers.length > 0) {
			items.splice(insertAt, 0, {
				id: "quality",
				label: "Quality",
				Icon: QualityIcon,
			});
			insertAt += 1;
		}
		if (props.streamMirrors.length > 0) {
			items.splice(insertAt, 0, {
				id: "stream",
				label: "Stream",
				Icon: StreamIcon,
			});
		}
		return items;
	});

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
			<p class="edit-tools-heading">Video tools</p>
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
							<span>{tool.label}</span>
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
								<p class="hint">
									Pick a tool from the left sidebar to edit download options.
								</p>
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
												const errors = () =>
													rowFieldErrors(cut(), props.durationSec);
												const durationLabel = () =>
													rowDurationLabel(props.durationSec, cut());

												return (
													<div class="cut-range-row">
														<div class="cut-range-head">
															<p class="cut-range-label">Cut {index + 1}</p>
															<Show when={durationLabel()}>
																<span class="cut-duration">
																	{durationLabel()}
																</span>
															</Show>
														</div>
														<div class="cut-range-fields">
															<TimeField
																id={`cut-${cut().id}-start`}
																label="Start"
																value={cut().start}
																error={errors().start}
																onChange={(value) =>
																	props.onCutChange(cut().id, "start", value)
																}
															/>
															<TimeField
																id={`cut-${cut().id}-end`}
																label="End"
																value={cut().end}
																error={errors().end}
																onChange={(value) =>
																	props.onCutChange(cut().id, "end", value)
																}
															/>
														</div>
														<Show
															when={multiCut()}
															fallback={
																<div
																	class="cut-remove-slot"
																	aria-hidden="true"
																/>
															}
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
											<span class="cut-total-duration">
												Total {totalDurationLabel()}
											</span>
										</Show>
									</div>
								</Show>

								<Show when={toolId() === "audio"}>
									<label class="toggle-row">
										<input
											type="checkbox"
											checked={props.audioFade}
											onChange={(event) =>
												props.onAudioFadeChange(event.currentTarget.checked)
											}
										/>
										<span>Fade in / out (0.5s at start and end)</span>
									</label>
									<label class="toggle-row">
										<input
											type="checkbox"
											checked={props.audioLoudnorm}
											onChange={(event) =>
												props.onAudioLoudnormChange(event.currentTarget.checked)
											}
										/>
										<span>Normalize loudness</span>
									</label>
								</Show>

								<Show when={toolId() === "quality"}>
									<p class="stream-active">
										Active tier:{" "}
										<strong>
											{props.hlsTiers.find(
												(tier) => tier.id === props.activeHlsTier,
											)?.label || "—"}
										</strong>
									</p>
									<div class="stream-mirror-list">
										<For each={props.hlsTiers}>
											{(tier) => (
												<button
													type="button"
													class={`stream-mirror-btn ${
														tier.id === props.activeHlsTier ? "active" : ""
													}`}
													onClick={() => props.onHlsTierChange(tier.id)}
												>
													{tier.label}
												</button>
											)}
										</For>
									</div>
								</Show>

								<Show when={toolId() === "stream"}>
									<p class="stream-active">
										Active mirror: <strong>{props.activeStream || "—"}</strong>
									</p>
									<div class="stream-mirror-list">
										<For each={props.streamMirrors}>
											{(label) => (
												<button
													type="button"
													class={`stream-mirror-btn ${
														label === props.activeStream ? "active" : ""
													}`}
													onClick={() => props.onStreamPreferenceChange(label)}
												>
													STREAM {label}
												</button>
											)}
										</For>
									</div>
									<button
										type="button"
										class="tool-btn subtle stream-next-btn"
										onClick={() => props.onTryNextStream()}
									>
										Try next mirror
									</button>
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
										onInput={(event) =>
											props.onCustomTitleChange(event.currentTarget.value)
										}
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
												props.onRememberSavePathChange(
													event.currentTarget.checked,
												)
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
		</section>
	);
}
