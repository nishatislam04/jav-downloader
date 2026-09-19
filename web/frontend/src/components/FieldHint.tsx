import {
	createEffect,
	createSignal,
	onCleanup,
	Show,
	type JSX,
} from "solid-js";
import { InfoIcon } from "./IconButton";

type Props = {
	label: string;
	children: JSX.Element;
};

function supportsHover() {
	return (
		typeof window !== "undefined" &&
		window.matchMedia("(hover: hover) and (pointer: fine)").matches
	);
}

export default function FieldHint(props: Props) {
	const [open, setOpen] = createSignal(false);
	let root: HTMLDivElement | undefined;

	function close() {
		setOpen(false);
	}

	function toggle() {
		setOpen((value) => !value);
	}

	createEffect(() => {
		if (!open()) return;

		function onPointerDown(event: PointerEvent) {
			if (!root?.contains(event.target as Node)) close();
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
