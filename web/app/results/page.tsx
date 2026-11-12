"use client";

import { Check, Loader2, Pencil, RefreshCw } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { toast } from "sonner";
import { ChatPanel } from "@/components/chat-panel";
import { FeedbackDialog } from "@/components/feedback-dialog";
import { FlowShell } from "@/components/flow-shell";
import { ShoeCard } from "@/components/shoe-card";
import { Button, buttonVariants } from "@/components/ui/button";
import { startRecommendation } from "@/lib/actions";
import { api, type Pick, type Recommendation } from "@/lib/api";
import { useHydrated, useSession } from "@/lib/store";
import { cn } from "@/lib/utils";

const WORKING = [
  "Reading your measurements",
  "Filtering shoes that can't fit",
  "Scoring toe box, volume and heel",
  "Choosing your size in each brand",
  "Checking stock for your size",
];

function Working() {
  const [i, setI] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setI((n) => Math.min(n + 1, WORKING.length - 1)), 380);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="grid justify-items-center gap-6 py-20 text-center" role="status" aria-live="polite">
      <Loader2 className="size-9 animate-spin" />
      <h1 className="text-[28px] font-semibold tracking-[-0.03em]">Ranking shoes for your feet</h1>
      <ol className="grid gap-2.5 text-left">
        {WORKING.map((t, j) => (
          <li key={t} className={cn("flex items-center gap-2.5 text-[14px] transition-colors", j <= i ? "text-foreground" : "text-muted-foreground")}>
            <span className={cn("grid size-4 place-items-center rounded-full border", j < i && "border-good bg-good text-white", j === i && "border-foreground border-t-transparent animate-spin")}>
              {j < i && <Check className="size-2.5" strokeWidth={4} />}
            </span>
            {t}
          </li>
        ))}
      </ol>
    </div>
  );
}

function Results() {
  const router = useRouter();
  const params = useSearchParams();
  const hydrated = useHydrated();
  const { userId, taskId: savedTask, set } = useSession();
  const taskId = params.get("task") ?? savedTask;
  const [rec, setRec] = useState<Recommendation | null>(null);
  const [feedback, setFeedback] = useState<Pick | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    if (!hydrated) return;
    if (!taskId || !userId) return router.replace("/");
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const started = Date.now();
    setRec(null);
    const poll = async () => {
      try {
        const task = await api.task(taskId);
        if (stop) return;
        if (task.status === "done" && task.result) {
          // Let the progress list play briefly even when ranking is instant.
          const wait = Math.max(0, 1400 - (Date.now() - started));
          timer = setTimeout(() => !stop && (setRec(task.result!), set({ taskId })), wait);
          return;
        }
        if (task.status === "failed") {
          console.warn("Recommendation failed:", task.error);
          toast.error("We couldn't finish your recommendation. Please try again.");
          return router.replace("/history/");
        }
      } catch (e) {
        if ((e as { status?: number }).status === 404) return router.replace("/");
      }
      timer = setTimeout(poll, 900);
    };
    poll();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, [hydrated, taskId, userId, router, set]);

  async function refresh() {
    setRefreshing(true);
    try {
      const task = await startRecommendation();
      router.replace(`/results/?task=${task}`);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setRefreshing(false);
    }
  }

  if (!rec) {
    return (
      <FlowShell step="Results" progress={0.92}>
        <Working />
      </FlowShell>
    );
  }

  return (
    <FlowShell step="Results" progress={1} width="full">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-6">
        <div className="grid gap-2.5">
          <p className="eyebrow">Your fit list</p>
          <h1 className="text-[clamp(28px,3.6vw,38px)] leading-tight font-semibold tracking-[-0.035em]">
            {rec.picks.length === 1 ? "Your top pick" : `Your top ${rec.picks.length} picks`}
          </h1>
          <p className="max-w-[60ch] text-[15.5px] text-muted-foreground">{rec.summary} Ordered by fit score, highest first.</p>
        </div>
        <div className="flex gap-2">
          <Link href="/preferences/" className={buttonVariants({ variant: "outline", size: "sm", className: "h-9 px-3" })}>
            <Pencil /> Edit answers
          </Link>
          <Button variant="outline" size="sm" className="h-9 px-3" onClick={refresh} disabled={refreshing}>
            <RefreshCw className={cn(refreshing && "animate-spin")} /> Refresh
          </Button>
        </div>
      </div>

      {rec.picks.length ? (
        <div className="grid gap-5">
          {rec.picks.map((p, i) => <ShoeCard key={p.shoe_id} pick={p} index={i} onFeedback={setFeedback} />)}
        </div>
      ) : (
        <p className="rounded-2xl border border-dashed px-6 py-12 text-center text-muted-foreground">
          No shoes in our catalog fit these answers yet. Try a wider budget or a different feel.
        </p>
      )}

      {(rec.flags.length > 0 || rec.disclosure) && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3 }} className="mt-6 grid gap-3 rounded-xl bg-secondary px-5 py-4 text-[13.5px] text-muted-foreground">
          {rec.flags.length > 0 && (
            <div>
              <p className="mb-1 font-semibold text-foreground">About these results</p>
              <ul className="grid list-disc gap-1 pl-5">
                {rec.flags.map((f) => <li key={f}>{f}</li>)}
              </ul>
            </div>
          )}
          {rec.disclosure && <p className="text-[12.5px]">{rec.disclosure}</p>}
        </motion.div>
      )}

      <div className="mt-10">
        <ChatPanel userId={userId!} picksLabel={`ranker ${rec.ranker_version}`} />
      </div>

      <FeedbackDialog pick={feedback} userId={userId!} taskId={taskId!} onClose={() => setFeedback(null)} />
    </FlowShell>
  );
}

export default function ResultsPage() {
  return (
    <Suspense>
      <Results />
    </Suspense>
  );
}
