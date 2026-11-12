"use client";

import { useRef } from "react";
import { cn } from "@/lib/utils";

type Side = "left" | "right";

/**
 * A horizontal scale with the left foot's arrow above and the right foot's below, like the
 * scan report. Arrows drag (pointer) or step (arrow keys); `snap` limits them to tick stops.
 */
export function ScaleTrack({
  labels,
  values,
  onChange,
  snap,
  step = 0.02,
  name,
  format,
}: {
  labels: string[]; // shown under the track, evenly spaced
  values: Record<Side, number | null>; // 0-1, null = not measured
  onChange: (side: Side, value: number) => void;
  snap?: number[]; // allowed positions (0-1)
  step?: number;
  name: string;
  format: (value: number) => string;
}) {
  const track = useRef<HTMLDivElement>(null);
  const fit = (v: number) => {
    const c = Math.min(1, Math.max(0, v));
    return snap ? snap.reduce((a, b) => (Math.abs(b - c) < Math.abs(a - c) ? b : a)) : Math.round(c * 100) / 100;
  };
  const at = (clientX: number) => {
    const r = track.current!.getBoundingClientRect();
    return fit((clientX - r.left) / r.width);
  };

  const arrow = (side: Side) => {
    const v = values[side];
    if (v == null) return null;
    const above = side === "left";
    return (
      <button
        type="button"
        role="slider"
        aria-label={`${name}, ${side} foot`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(v * 100)}
        aria-valuetext={format(v)}
        className={cn(
          "group absolute z-10 flex -translate-x-1/2 cursor-grab touch-none flex-col items-center outline-none active:cursor-grabbing",
          above ? "bottom-[calc(50%+3px)]" : "top-[calc(50%+3px)] flex-col-reverse",
        )}
        style={{ left: `${v * 100}%` }}
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId);
          e.currentTarget.focus();
        }}
        onPointerMove={(e) => {
          if (e.currentTarget.hasPointerCapture(e.pointerId)) onChange(side, at(e.clientX));
        }}
        onKeyDown={(e) => {
          const dir = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1 }[e.key];
          if (!dir) return;
          e.preventDefault();
          if (snap) {
            const i = snap.indexOf(fit(v));
            onChange(side, snap[Math.min(snap.length - 1, Math.max(0, i + dir))]);
          } else onChange(side, fit(v + dir * step));
        }}
      >
        <span
          className={cn(
            "mb-0.5 rounded px-1 font-mono text-[10px] leading-4 font-medium transition-colors",
            above ? "bg-foreground text-background" : "bg-volt text-volt-foreground",
            "group-focus-visible:ring-2 group-focus-visible:ring-ring group-focus-visible:ring-offset-1",
          )}
        >
          {above ? "L" : "R"}
        </span>
        <svg viewBox="0 0 12 8" className={cn("h-2 w-3", above ? "fill-foreground" : "rotate-180 fill-volt")}>
          <path d="M0 0h12L6 8z" />
        </svg>
      </button>
    );
  };

  return (
    <div className="select-none">
      <div className="relative h-16">
        <div
          ref={track}
          className="absolute inset-x-0 top-1/2 h-1.5 -translate-y-1/2 cursor-pointer rounded-full bg-muted"
          onPointerDown={(e) => {
            // Click the track: move whichever arrow is closer.
            const v = at(e.clientX);
            const l = values.left ?? Infinity;
            const r = values.right ?? Infinity;
            if (l === Infinity && r === Infinity) return;
            onChange(Math.abs(l - v) <= Math.abs(r - v) ? "left" : "right", v);
          }}
        >
          {labels.length === 3 && (
            <>
              <span className="absolute inset-y-0 left-1/3 w-0.5 bg-background" />
              <span className="absolute inset-y-0 left-2/3 w-0.5 bg-background" />
            </>
          )}
          {snap?.map((s) => (
            <span key={s} className="absolute top-1/2 size-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-input" style={{ left: `${s * 100}%` }} />
          ))}
        </div>
        {arrow("left")}
        {arrow("right")}
      </div>
      <div className="relative h-4 text-[12px] text-muted-foreground">
        {labels.map((l, i) => {
          // Letters sit under their stops; band names sit under the middle of their third.
          const x = snap ? snap[i] : (i + 0.5) / labels.length;
          const shift = snap ? (i === 0 ? "0%" : i === labels.length - 1 ? "-100%" : "-50%") : "-50%";
          return (
            <span key={l} className="absolute top-0 whitespace-nowrap" style={{ left: `${x * 100}%`, transform: `translateX(${shift})` }}>
              {l}
            </span>
          );
        })}
      </div>
    </div>
  );
}
