import { createEffect, createSignal, For, onCleanup, Show } from "solid-js";
import {
	clearHistory,
	cropHistoryTitle,
	deleteHistory,
	formatHistoryWhen,
	type HistoryEntry,
	loadHistory,
} from "../lib/history";
import { HistoryIcon, TrashIcon } from "./IconButton";
import { thumbnailSrc } from "./ThumbnailPreview";

type Props = {
	onSelect: (entry: HistoryEntry) => void;
};

export default function HistoryMenu(props: Props) {
	const [open, setOpen] = createSignal(false);
	const [entries, setEntries] = createSignal<HistoryEntry[]>(loadHistory());

	function refresh() {
		setEntries(loadHistory());
	}

	function toggle() {
		refresh();
		setOpen((value) => !value);
	}

	function close() {
		setOpen(false);
	}

	function onDocClick(event: MouseEvent) {
		const target = event.target as Node | null;
		const root = document.getElementById("history-menu-root");
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

	function removeEntry(id: string) {
		setEntries(deleteHistory(id));
	}

	function onClearAll() {
		setEntries(clearHistory());
	}

	return (
		<div id="history-menu-root" class="history-menu">
			<button
				type="button"
				class="history-menu-btn"
				classList={{ active: open() }}
				aria-label="History"
				aria-expanded={open()}
				title="History"
				onClick={toggle}
			>
				<HistoryIcon />
			</button>
			<Show when={open()}>
				<div class="history-dropdown" role="menu">
					<Show
						when={entries().length}
						fallback={<p class="history-empty">No downloads yet</p>}
					>
						<For each={entries()}>
							{(entry) => (
								<div class="history-item">
									<button
										type="button"
										class="history-item-main"
										role="menuitem"
										onClick={() => {
											props.onSelect(entry);
											close();
										}}
									>
										<Show when={entry.thumbnail}>
											<img
												src={thumbnailSrc(entry.thumbnail)}
												alt=""
												class="history-item-thumb"
												loading="lazy"
											/>
										</Show>
										<span class="history-item-body">
											<span class="history-item-title">
												{cropHistoryTitle(entry.title)}
											</span>
											<span class="history-item-when">
												{formatHistoryWhen(entry.downloadedAt)}
											</span>
										</span>
									</button>
									<button
										type="button"
										class="history-item-del"
										aria-label="Delete entry"
										title="Delete"
										onClick={() => removeEntry(entry.id)}
									>
										<TrashIcon />
									</button>
								</div>
							)}
						</For>
					</Show>
					<Show when={entries().length}>
						<div class="history-footer">
							<button
								type="button"
								class="history-clear-btn"
								onClick={onClearAll}
							>
								<TrashIcon />
								Clear all
							</button>
						</div>
					</Show>
				</div>
			</Show>
		</div>
	);
}
