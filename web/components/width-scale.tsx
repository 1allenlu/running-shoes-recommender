"use client";

import type { Foot } from "@/lib/api";
import { WIDTHS } from "@/lib/foot";
import { ScaleTrack } from "./scale-track";

const STOPS = WIDTHS.map((_, i) => i / (WIDTHS.length - 1));

/** Width letter (3A…3E) for both feet, snapped to letters. */
export function WidthScale({
  left,
  right,
  onChange,
}: {
  left: Foot["width"];
  right: Foot["width"];
  onChange: (side: "left" | "right", width: Foot["width"]) => void;
}) {
  const pos = (w: Foot["width"]) => STOPS[WIDTHS.indexOf(w)];
  return (
    <div className="grid gap-2 py-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold">Width</p>
          <p className="text-[13px] text-muted-foreground">Forefoot width letter from your report</p>
        </div>
        <div className="flex shrink-0 gap-3 text-[13px]">
          <span><span className="text-muted-foreground">L</span> {left}</span>
          <span><span className="text-muted-foreground">R</span> {right}</span>
        </div>
      </div>
      <ScaleTrack
        name="Width"
        labels={[...WIDTHS]}
        snap={STOPS}
        values={{ left: pos(left), right: pos(right) }}
        format={(v) => WIDTHS[STOPS.indexOf(v)] ?? ""}
        onChange={(side, v) => onChange(side, WIDTHS[STOPS.indexOf(v)] ?? WIDTHS[0])}
      />
    </div>
  );
}
