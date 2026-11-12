"use client";

import { AlertCircle, ArrowUpRight, Check, MessageSquareText, Ruler } from "lucide-react";
import { motion } from "motion/react";
import { Button } from "@/components/ui/button";
import type { Pick } from "@/lib/api";
import { cn } from "@/lib/utils";
import { FitMeter, FitScore } from "./fit-meter";

const widthLabel = (w: string) => ({ standard: "Standard", wide: "Wide", "extra-wide": "Extra wide" })[w] ?? w;
const money = (v: number | null) =>
  v == null ? "See price" : new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(v);
const sentence = (s: string) => (/[.!?]$/.test(s.trim()) ? s.trim() : `${s.trim()}.`);

export function sizeText(p: Pick) {
  return `US ${Number(p.size.us_size)} · ${widthLabel(p.size.width)}`;
}

/** A results card in the spirit of an ecommerce product card: tile, details, buy box. */
export function ShoeCard({ pick, index, onFeedback }: { pick: Pick; index: number; onFeedback: (p: Pick) => void }) {
  const best = pick.rank === 1;
  return (
    <motion.article
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.08, duration: 0.45, ease: [0.2, 0.7, 0.2, 1] }}
      className={cn(
        "grid overflow-hidden rounded-2xl border bg-card shadow-[0_1px_2px_rgb(0_0_0/0.04),0_8px_24px_-8px_rgb(0_0_0/0.08)] lg:grid-cols-[1fr_330px]",
        best && "border-foreground shadow-[0_0_0_1px_var(--foreground),0_8px_24px_-8px_rgb(0_0_0/0.12)]",
      )}
      aria-labelledby={`pick-${pick.shoe_id}`}
    >
      <div className="grid content-start gap-6 p-5 sm:p-7">
        {/* Product tile */}
        <div className="relative flex items-center justify-between gap-4 overflow-hidden rounded-xl bg-secondary px-5 py-5">
          <div className="pointer-events-none absolute -right-10 -bottom-16 size-48 rounded-full border border-border" aria-hidden />
          <div className="pointer-events-none absolute -right-2 -bottom-8 size-28 rounded-full border border-border" aria-hidden />
          <div className="relative grid gap-1.5">
            <span
              className={cn(
                "w-fit rounded-md px-2 py-1 font-mono text-[11px] leading-none font-medium",
                best ? "bg-volt text-volt-foreground" : "border bg-card text-muted-foreground",
              )}
            >
              {best ? "#1 Best fit" : `#${pick.rank}`}
            </span>
            <p className="eyebrow mt-1">{pick.brand}</p>
            <h2 id={`pick-${pick.shoe_id}`} className="text-[clamp(22px,2.6vw,28px)] leading-tight font-semibold tracking-[-0.03em]">
              {pick.model} {pick.version}
            </h2>
          </div>
          <FitScore score={pick.fit_score} size={78} className="relative" />
        </div>

        <div className="grid gap-7 md:grid-cols-2">
          <div className="grid content-start gap-5">
            <section>
              <h3 className="mb-3 text-sm font-semibold">Why it fits your foot</h3>
              <ul className="grid gap-2.5">
                {pick.why_it_fits.map((t) => (
                  <li key={t} className="grid grid-cols-[18px_1fr] gap-2.5 text-[14px] leading-snug">
                    <span className="mt-px grid size-[18px] place-items-center rounded-full bg-good-soft text-good"><Check className="size-3" strokeWidth={3} /></span>
                    {sentence(t)}
                  </li>
                ))}
              </ul>
            </section>
            {pick.watch_for.length > 0 && (
              <section>
                <h3 className="mb-3 text-sm font-semibold">Watch for</h3>
                <ul className="grid gap-2.5">
                  {pick.watch_for.map((t) => (
                    <li key={t} className="grid grid-cols-[18px_1fr] gap-2.5 text-[14px] leading-snug">
                      <span className="mt-px grid size-[18px] place-items-center rounded-full bg-warn-soft text-warn"><AlertCircle className="size-3" strokeWidth={3} /></span>
                      {sentence(t)}
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
          <section>
            <h3 className="mb-2 text-sm font-semibold">Fit meter</h3>
            <FitMeter factors={pick.breakdown} />
          </section>
        </div>
      </div>

      {/* Buy box */}
      <aside className="flex flex-col gap-4 border-t bg-secondary/60 p-5 sm:p-6 lg:border-t-0 lg:border-l">
        <div className="rounded-xl border bg-card p-4">
          <div className="flex items-center justify-between gap-2">
            <p className="eyebrow flex items-center gap-1.5"><Ruler className="size-3.5" /> Size to order</p>
            <span
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[12px] font-medium",
                pick.size.confident ? "bg-good-soft text-good" : "bg-warn-soft text-warn",
              )}
            >
              <span className="size-1.5 rounded-full bg-current" />
              {pick.size.confident ? "Brand chart" : "Try on first"}
            </span>
          </div>
          <p className="mt-2 text-[22px] font-semibold tracking-[-0.025em] tabular-nums">
            US {Number(pick.size.us_size)} <span className="font-medium text-muted-foreground">· {widthLabel(pick.size.width)}</span>
          </p>
          <p className="mt-1.5 text-[12.5px] leading-relaxed text-muted-foreground">
            {[pick.size.basis, pick.size.sizing_note].filter(Boolean).map((s) => sentence(s as string)).join(" ")}
          </p>
        </div>

        <div className="grid gap-2">
          <p className="eyebrow">Where to buy</p>
          {pick.offers.length ? (
            pick.offers.map((o, i) => (
              <a
                key={o.offer_id}
                href={o.url}
                target="_blank"
                rel="sponsored noopener noreferrer"
                className="group flex items-center justify-between gap-3 rounded-xl border bg-card px-4 py-3 transition-colors hover:border-foreground"
                aria-label={`Buy at ${o.retailer}, ${money(o.price_usd)} (opens in a new tab)`}
              >
                <span>
                  <span className="block text-[14px] font-medium">{o.retailer}</span>
                  <span className="block text-[13px] text-muted-foreground tabular-nums">{money(o.price_usd)}</span>
                </span>
                <span
                  className={cn(
                    "inline-flex h-8 items-center gap-1 rounded-lg px-3 text-[13px] font-medium",
                    i === 0 ? "bg-volt text-volt-foreground" : "bg-primary text-primary-foreground",
                  )}
                >
                  Buy <ArrowUpRight className="size-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                </span>
              </a>
            ))
          ) : (
            <p className="rounded-xl border border-dashed px-4 py-3 text-[13.5px] text-muted-foreground">Not in stock in your size right now.</p>
          )}
        </div>

        <Button variant="ghost" className="mt-auto h-9 justify-start px-2 text-[13.5px]" onClick={() => onFeedback(pick)}>
          <MessageSquareText /> Tried them? Rate the fit
        </Button>
      </aside>
    </motion.article>
  );
}

/** Compact card for picks inside a chat reply. */
export function ShoeMini({ pick }: { pick: Pick }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border bg-card p-3">
      <FitScore score={pick.fit_score} size={44} />
      <div className="min-w-0 flex-1">
        <p className="eyebrow !text-[10px]">#{pick.rank} · {pick.brand}</p>
        <p className="truncate text-[14px] font-semibold">{pick.model} {pick.version}</p>
        <p className="truncate text-[12.5px] text-muted-foreground">{sizeText(pick)}{pick.why_it_fits[0] ? ` · ${pick.why_it_fits[0]}` : ""}</p>
      </div>
      {pick.offers[0] && (
        <a href={pick.offers[0].url} target="_blank" rel="sponsored noopener noreferrer" className="shrink-0 rounded-lg bg-primary px-2.5 py-1.5 text-[12px] font-medium text-primary-foreground">
          {money(pick.offers[0].price_usd)}
        </a>
      )}
    </div>
  );
}
