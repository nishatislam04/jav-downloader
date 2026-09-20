import { createEffect, createSignal, untrack } from "solid-js";
import { formatDurationSec, pad2, parseHmsToSec } from "../lib/time";

type Segment = "h" | "m" | "s";

type Props = {
  id: string;
  label: string;
  value: string;
  error?: string;
  onChange: (value: string) => void;
};

function parsePaste(text: string): { h: number; m: number; s: number } | null {
  const trimmed = text.trim();
  if (!trimmed || /^\d+$/.test(trimmed) || !trimmed.includes(":")) return null;

  const parts = trimmed.split(":").map((part) => part.trim());
  if (parts.some((part) => part === "" || Number.isNaN(Number(part)))) return null;

  let totalSec: number;
  if (parts.length === 2) {
    const [minutes, seconds] = parts.map(Number);
    if (minutes < 0 || seconds < 0) return null;
    totalSec = minutes * 60 + seconds;
  } else if (parts.length === 3) {
    const [hours, minutes, seconds] = parts.map(Number);
    if (hours < 0 || minutes < 0 || seconds < 0) return null;
    totalSec = hours * 3600 + minutes * 60 + seconds;
  } else {
    return null;
  }

  return {
    h: Math.floor(totalSec / 3600),
    m: Math.floor((totalSec % 3600) / 60),
    s: totalSec % 60,
  };
}

function clampSegmentMax(seg: Segment, n: number): number {
  if (seg === "h") return Math.min(23, Math.max(0, n));
  return Math.min(59, Math.max(0, n));
}

function segmentsToValue(h: string, m: string, s: string): string {
  if (!h && !m && !s) return "";
  const hi = h ? Number(h) : 0;
  const mi = m ? Number(m) : 0;
  const si = s ? Number(s) : 0;
  return formatDurationSec(hi * 3600 + mi * 60 + si);
}

function valueToSegments(value: string): [string, string, string] {
  const text = value.trim();
  if (!text) return ["", "", ""];

  const sec = parseHmsToSec(text);
  if (sec === null) return ["", "", ""];

  return [pad2(Math.floor(sec / 3600)), pad2(Math.floor((sec % 3600) / 60)), pad2(sec % 60)];
}

export default function TimeField(props: Props) {
  const initial = valueToSegments(props.value);
  const [h, setH] = createSignal(initial[0]);
  const [m, setM] = createSignal(initial[1]);
  const [s, setS] = createSignal(initial[2]);

  let hRef: HTMLInputElement | undefined;
  let mRef: HTMLInputElement | undefined;
  let sRef: HTMLInputElement | undefined;
  let lastEmitted = props.value;

  createEffect(() => {
    const external = props.value;
    if (external === lastEmitted) return;
    lastEmitted = external;
    const [nh, nm, ns] = valueToSegments(external);
    untrack(() => {
      setH(nh);
      setM(nm);
      setS(ns);
    });
  });

  function emit(nextH = h(), nextM = m(), nextS = s()) {
    const value = segmentsToValue(nextH, nextM, nextS);
    lastEmitted = value;
    props.onChange(value);
  }

  function segRef(seg: Segment): HTMLInputElement | undefined {
    if (seg === "h") return hRef;
    if (seg === "m") return mRef;
    return sRef;
  }

  function focusSeg(seg: Segment) {
    const el = segRef(seg);
    el?.focus();
    el?.select();
  }

  function focusAdjacent(seg: Segment, dir: -1 | 1) {
    const order: Segment[] = ["h", "m", "s"];
    const idx = order.indexOf(seg) + dir;
    if (idx >= 0 && idx < order.length) focusSeg(order[idx]!);
  }

  function setSeg(seg: Segment, val: string) {
    if (seg === "h") setH(val);
    else if (seg === "m") setM(val);
    else setS(val);
  }

  function getSeg(seg: Segment): string {
    if (seg === "h") return h();
    if (seg === "m") return m();
    return s();
  }

  function applySeg(seg: Segment, val: string) {
    setSeg(seg, val);
    emit(seg === "h" ? val : h(), seg === "m" ? val : m(), seg === "s" ? val : s());
  }

  function stepSeg(seg: Segment, delta: 1 | -1) {
    const current = getSeg(seg);
    const base = current === "" ? 0 : Number(current);
    const max = seg === "h" ? 23 : 59;
    const wrapped = delta === 1 ? (base >= max ? 0 : base + 1) : base <= 0 ? max : base - 1;
    applySeg(seg, pad2(wrapped));
  }

  function commitDigit(seg: Segment, digit: string) {
    const current = getSeg(seg);
    const el = segRef(seg);
    const selected =
      !!el &&
      el.selectionStart !== null &&
      el.selectionEnd !== null &&
      el.selectionStart !== el.selectionEnd;
    const replacing = !current || selected;

    if (replacing) {
      if (seg === "h" && Number(digit) >= 3) {
        applySeg(seg, pad2(Number(digit)));
        focusAdjacent(seg, 1);
        return;
      }
      if ((seg === "m" || seg === "s") && Number(digit) >= 6) {
        applySeg(seg, pad2(Number(digit)));
        focusAdjacent(seg, 1);
        return;
      }
      applySeg(seg, digit);
      return;
    }

    const combined = pad2(clampSegmentMax(seg, Number(`${current}${digit}`)));
    applySeg(seg, combined);
    focusAdjacent(seg, 1);
  }

  function handlePaste(event: ClipboardEvent) {
    const parsed = parsePaste(event.clipboardData?.getData("text") ?? "");
    if (!parsed) return;

    event.preventDefault();
    setH(pad2(parsed.h));
    setM(pad2(parsed.m));
    setS(pad2(parsed.s));
    emit(pad2(parsed.h), pad2(parsed.m), pad2(parsed.s));
  }

  function handleKeyDown(seg: Segment, event: KeyboardEvent) {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      focusAdjacent(seg, -1);
      return;
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      focusAdjacent(seg, 1);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      stepSeg(seg, 1);
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      stepSeg(seg, -1);
      return;
    }
    if (event.key === "Backspace") {
      event.preventDefault();
      if (getSeg(seg)) {
        applySeg(seg, "");
      } else {
        focusAdjacent(seg, -1);
      }
      return;
    }
    if (event.key === "Delete") {
      event.preventDefault();
      applySeg(seg, "");
      return;
    }
    if (event.key === ":" || event.key === ".") {
      event.preventDefault();
      return;
    }
    if (/^\d$/.test(event.key)) {
      event.preventDefault();
      commitDigit(seg, event.key);
    }
  }

  function handleWheel(seg: Segment, event: WheelEvent) {
    event.preventDefault();
    stepSeg(seg, event.deltaY < 0 ? 1 : -1);
  }

  const segLabel = (part: string) => `${props.label} ${part}`;

  return (
    <div class="time-field">
      <label for={`${props.id}-h`}>{props.label}</label>
      <div class={`time-segments ${props.error ? "input-error" : ""}`}>
        <input
          ref={hRef}
          id={`${props.id}-h`}
          class="time-seg"
          type="text"
          inputmode="numeric"
          autocomplete="off"
          spellcheck={false}
          aria-label={segLabel("hours")}
          placeholder="00"
          value={h()}
          onFocus={(event) => event.currentTarget.select()}
          onPaste={handlePaste}
          onKeyDown={(event) => handleKeyDown("h", event)}
          onWheel={(event) => handleWheel("h", event)}
        />
        <span class="time-sep" aria-hidden="true">
          :
        </span>
        <input
          ref={mRef}
          id={`${props.id}-m`}
          class="time-seg"
          type="text"
          inputmode="numeric"
          autocomplete="off"
          spellcheck={false}
          aria-label={segLabel("minutes")}
          placeholder="00"
          value={m()}
          onFocus={(event) => event.currentTarget.select()}
          onPaste={handlePaste}
          onKeyDown={(event) => handleKeyDown("m", event)}
          onWheel={(event) => handleWheel("m", event)}
        />
        <span class="time-sep" aria-hidden="true">
          :
        </span>
        <input
          ref={sRef}
          id={`${props.id}-s`}
          class="time-seg"
          type="text"
          inputmode="numeric"
          autocomplete="off"
          spellcheck={false}
          aria-label={segLabel("seconds")}
          placeholder="00"
          value={s()}
          onFocus={(event) => event.currentTarget.select()}
          onPaste={handlePaste}
          onKeyDown={(event) => handleKeyDown("s", event)}
          onWheel={(event) => handleWheel("s", event)}
        />
      </div>
      {props.error ? <p class="time-error">{props.error}</p> : null}
    </div>
  );
}
