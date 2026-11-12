"use client";

import { Bar, BarChart, Cell, LabelList, PolarAngleAxis, RadialBar, RadialBarChart, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart";
import type { FitFactor } from "@/lib/api";
import { cn } from "@/lib/utils";

export const FACTOR_LABELS: Record<string, string> = {
  width_fit: "Toe box width",
  volume_fit: "Upper volume",
  heel_fit: "Heel hold",
  combo_fit: "Forefoot vs. instep",
  ride_fit: "Ride feel",
  history_fit: "Past shoes",
  budget_fit: "Budget",
};

const config = {
  score: { label: "Match", color: "var(--foreground)" },
} satisfies ChartConfig;

/** Fit score (0-100) as a radial gauge. */
export function FitScore({ score, size = 72, className }: { score: number; size?: number; className?: string }) {
  return (
    <div className={cn("relative shrink-0", className)} style={{ width: size, height: size }} role="img" aria-label={`Fit score ${score} out of 100`}>
      <ChartContainer config={config} className="aspect-square size-full" initialDimension={{ width: size, height: size }}>
        <RadialBarChart data={[{ score }]} startAngle={90} endAngle={-270} innerRadius="78%" outerRadius="100%" barSize={size / 12}>
          <PolarAngleAxis type="number" domain={[0, 100]} tick={false} axisLine={false} />
          <RadialBar dataKey="score" background cornerRadius={99} fill="var(--color-score)" isAnimationActive animationDuration={900} />
        </RadialBarChart>
      </ChartContainer>
      <span className="absolute inset-0 grid place-items-center text-center leading-none">
        <span>
          <span className="block font-semibold tracking-[-0.04em] tabular-nums" style={{ fontSize: size * 0.3 }}>{score}</span>
        </span>
      </span>
    </div>
  );
}

type Row = { label: string; value: number; shown: string; unknown: boolean; low: boolean; note: string };

/**
 * Per-factor match for one shoe (the ranker's sub-scores), heaviest factor first.
 * Unverified specs are striped: they count as neutral (50) in the score.
 */
export function FitMeter({ factors }: { factors: FitFactor[] }) {
  const rows: Row[] = factors.map((f) => ({
    label: FACTOR_LABELS[f.factor] ?? f.factor,
    value: f.score == null ? 100 : Math.max(2, Math.round(f.score * 100)),
    shown: f.score == null ? "–" : `${Math.round(f.score * 100)}`,
    unknown: f.score == null,
    low: f.score != null && f.score <= 0.6,
    note: f.note,
  }));
  const anyUnknown = rows.some((r) => r.unknown);

  return (
    <div>
      <ChartContainer config={config} className="aspect-auto w-full" style={{ height: rows.length * 30 + 4 }} initialDimension={{ width: 320, height: rows.length * 30 }}>
        <BarChart data={rows} layout="vertical" margin={{ left: 2, right: 34, top: 2, bottom: 2 }} barCategoryGap={9}>
          <defs>
            <pattern id="unverified" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="6" height="6" fill="var(--muted)" />
              <line x1="0" y1="0" x2="0" y2="6" stroke="var(--input)" strokeWidth="3" />
            </pattern>
          </defs>
          <XAxis type="number" domain={[0, 100]} hide />
          <YAxis
            type="category"
            dataKey="label"
            width={124}
            tickLine={false}
            axisLine={false}
            tick={({ x, y, payload }) => (
              <text x={Number(x) - 112} y={Number(y)} dy={4} textAnchor="start" fontSize={12.5} className="fill-muted-foreground">
                {payload.value}
              </text>
            )}
          />
          <ChartTooltip
            cursor={false}
            content={({ active, payload }) => {
              const row = active && (payload?.[0]?.payload as Row | undefined);
              if (!row) return null;
              return (
                <div className="max-w-60 rounded-lg border bg-popover px-3 py-2 text-[12.5px] shadow-md">
                  <p className="font-medium">{row.label} · {row.unknown ? "not verified" : row.shown}</p>
                  <p className="text-muted-foreground">{row.note}</p>
                </div>
              );
            }}
          />
          <Bar dataKey="value" radius={99} background={{ fill: "var(--muted)", radius: 99 }} isAnimationActive animationDuration={800}>
            {rows.map((r) => (
              <Cell key={r.label} fill={r.unknown ? "url(#unverified)" : r.low ? "var(--warn)" : "var(--color-score)"} />
            ))}
            <LabelList dataKey="shown" position="right" offset={10} className="fill-foreground font-semibold tabular-nums" fontSize={12.5} />
          </Bar>
        </BarChart>
      </ChartContainer>
      {anyUnknown && (
        <p className="mt-2 flex items-center gap-2 text-[12px] text-muted-foreground">
          <span className="stripes h-1.5 w-5 rounded-full" aria-hidden />
          Not verified yet: counted as neutral
        </p>
      )}
    </div>
  );
}
