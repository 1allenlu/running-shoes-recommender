"use client";

import type { Foot } from "@/lib/api";
import { bandAt, cap, type ScaleKey } from "@/lib/foot";
import { ScaleTrack } from "./scale-track";

type Band = { band: string; position: number } | null | undefined;

/** One band scale (arch, instep, heel...) for both feet: LEFT arrow above, RIGHT below. */
export function BandScale({
  label,
  hint,
  bands,
  optional,
  scaleKey,
  left,
  right,
  onChange,
}: {
  label: string;
  hint: string;
  bands: [string, string, string];
  optional?: boolean;
  scaleKey: ScaleKey;
  left: Foot;
  right: Foot;
  onChange: (side: "left" | "right", value: Band) => void;
}) {
  const l = left[scaleKey] as Band;
  const r = right[scaleKey] as Band;
  const measured = Boolean(l || r);
  const summary = (b: Band) => (b ? cap(b.band) : "—");

  return (
    <div className="grid gap-2 py-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold">{label}</p>
          <p className="text-[13px] text-muted-foreground">{hint}</p>
        </div>
        <div className="flex shrink-0 items-center gap-3 text-[13px]">
          {measured ? (
            <>
              <span><span className="text-muted-foreground">L</span> {summary(l)}</span>
              <span><span className="text-muted-foreground">R</span> {summary(r)}</span>
            </>
          ) : null}
          {optional && (
            <button
              type="button"
              className="rounded-md px-1.5 py-0.5 text-[12px] font-medium text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
              onClick={() => {
                const next = measured ? null : { band: bands[1], position: 0.5 };
                onChange("left", next);
                onChange("right", next);
              }}
            >
              {measured ? "Not on my report" : "Add"}
            </button>
          )}
        </div>
      </div>
      {measured ? (
        <ScaleTrack
          name={label}
          labels={bands.map(cap)}
          values={{ left: l?.position ?? null, right: r?.position ?? null }}
          format={(v) => cap(bandAt(bands, v))}
          onChange={(side, v) => onChange(side, { band: bandAt(bands, v), position: v })}
        />
      ) : (
        <p className="rounded-lg border border-dashed px-3 py-2.5 text-[13px] text-muted-foreground">Not measured</p>
      )}
    </div>
  );
}
