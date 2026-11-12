"use client";

import { Frown, Heart, Meh, Trash2 } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Chips } from "@/components/choice";
import { FlowActions, FlowHeading, FlowShell } from "@/components/flow-shell";
import { ShoeSearch } from "@/components/shoe-search";
import { Button } from "@/components/ui/button";
import { startRecommendation } from "@/lib/actions";
import type { Rating } from "@/lib/api";
import { ISSUE_OPTIONS } from "@/lib/options";
import { useHydrated, useSession, type HistoryDraft } from "@/lib/store";
import { cn } from "@/lib/utils";

const RATINGS: { value: Rating; label: string; icon: typeof Heart; on: string }[] = [
  { value: "loved", label: "Loved", icon: Heart, on: "border-good bg-good-soft text-good" },
  { value: "fine", label: "Fine", icon: Meh, on: "border-foreground bg-secondary text-foreground" },
  { value: "hated", label: "Hated", icon: Frown, on: "border-warn bg-warn-soft text-warn" },
];

export default function HistoryPage() {
  const router = useRouter();
  const hydrated = useHydrated();
  const { history, profile, set } = useSession();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (hydrated && !profile) router.replace("/scan/");
  }, [hydrated, profile, router]);

  const update = (i: number, patch: Partial<HistoryDraft>) =>
    set({ history: history.map((h, j) => (j === i ? { ...h, ...patch } : h)) });

  async function go() {
    setBusy(true);
    try {
      const task = await startRecommendation();
      router.push(`/results/?task=${task}`);
    } catch (e) {
      toast.error((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <FlowShell step="History">
      <FlowHeading overline="Step 4 of 4" title="Shoes you've run in">
        Add a few and tell us how they went. Shoes you hated are never recommended; ones you loved pull similar shapes up. It&apos;s optional, but it helps a lot.
      </FlowHeading>

      <ShoeSearch exclude={history.map((h) => h.raw_name)} onPick={(name) => set({ history: [{ raw_name: name, rating: "fine", issues: [] }, ...history] })} />

      <ul className="mt-4 grid gap-3">
        <AnimatePresence initial={false}>
          {history.map((h, i) => (
            <motion.li
              key={h.raw_name}
              layout
              initial={{ opacity: 0, y: -8, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, x: -24 }}
              transition={{ duration: 0.22 }}
              className="rounded-2xl border bg-card p-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-[15px] font-semibold">{h.raw_name}</p>
                <div className="flex items-center gap-1.5">
                  <div role="radiogroup" aria-label={`How did the ${h.raw_name} go?`} className="flex gap-1.5">
                    {RATINGS.map((r) => (
                      <button
                        key={r.value}
                        type="button"
                        role="radio"
                        aria-checked={h.rating === r.value}
                        onClick={() => update(i, { rating: r.value })}
                        className={cn(
                          "inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-[13px] font-medium text-muted-foreground transition-all hover:text-foreground",
                          h.rating === r.value && r.on,
                        )}
                      >
                        <r.icon className="size-3.5" /> {r.label}
                      </button>
                    ))}
                  </div>
                  <Button variant="ghost" size="icon-sm" aria-label={`Remove ${h.raw_name}`} onClick={() => set({ history: history.filter((_, j) => j !== i) })}>
                    <Trash2 />
                  </Button>
                </div>
              </div>
              <div className="mt-3 border-t pt-3">
                <p className="mb-2 text-[12.5px] text-muted-foreground">Any issues? <span className="opacity-70">Optional</span></p>
                <Chips label={`Issues with the ${h.raw_name}`} size="sm" value={h.issues} onChange={(issues) => update(i, { issues })} options={ISSUE_OPTIONS} />
              </div>
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>

      {history.length === 0 && (
        <p className="mt-4 rounded-2xl border border-dashed px-5 py-8 text-center text-[14px] text-muted-foreground">
          No shoes yet. Search above, or skip this step.
        </p>
      )}

      <FlowActions>
        <Button variant="ghost" onClick={() => router.push("/preferences/")}>Back</Button>
        <Button onClick={go} disabled={busy} className="h-10 px-5">
          {busy ? "Ranking…" : history.length ? "See my picks" : "Skip and see my picks"}
        </Button>
      </FlowActions>
    </FlowShell>
  );
}
