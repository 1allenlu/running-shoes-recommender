"use client";

import { Check } from "lucide-react";
import { motion } from "motion/react";
import { useRouter } from "next/navigation";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useSession } from "@/lib/store";

const STEPS = ["Scan", "Confirm", "Preferences", "History", "Results"] as const;
export type Step = (typeof STEPS)[number];

/** Header with step indicator + thin progress bar, and an animated content column. */
export function FlowShell({
  step,
  progress,
  width = "narrow",
  children,
}: {
  step: Step;
  progress?: number; // 0-1 within the whole flow; defaults to the step's position
  width?: "narrow" | "wide" | "full";
  children: React.ReactNode;
}) {
  const router = useRouter();
  const reset = useSession((s) => s.reset);
  const index = STEPS.indexOf(step);
  const pct = progress ?? (index + 0.5) / STEPS.length;

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur-xl backdrop-saturate-150">
        <div className="mx-auto flex h-15 w-[min(1160px,100%-2rem)] items-center gap-4">
          <Logo compact />
          <ol className="mx-auto flex items-center gap-1.5" aria-label="Progress">
            {STEPS.map((label, i) => (
              <li key={label} className="flex items-center gap-1.5" aria-current={i === index ? "step" : undefined}>
                {i > 0 && <span className="h-px w-3 bg-input sm:w-6" aria-hidden />}
                <span
                  className={cn(
                    "grid size-[22px] place-items-center rounded-full border font-mono text-[11px] transition-colors",
                    i < index && "border-volt bg-volt text-volt-foreground",
                    i === index && "border-foreground bg-foreground text-background",
                    i > index && "border-input bg-card text-muted-foreground",
                  )}
                >
                  {i < index ? <Check className="size-3" strokeWidth={3} /> : i + 1}
                </span>
                <span
                  className={cn(
                    "hidden text-[13px] font-medium lg:inline",
                    i === index ? "text-foreground" : "text-muted-foreground",
                  )}
                >
                  {label}
                </span>
              </li>
            ))}
          </ol>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              reset();
              router.push("/");
            }}
          >
            Start over
          </Button>
        </div>
        <div className="h-0.5 bg-transparent" aria-hidden>
          <motion.div
            className="h-full bg-foreground"
            initial={false}
            animate={{ width: `${Math.round(pct * 100)}%` }}
            transition={{ type: "spring", stiffness: 120, damping: 24 }}
          />
        </div>
      </header>
      <motion.main
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35, ease: [0.2, 0.7, 0.2, 1] }}
        className={cn(
          "mx-auto pt-10 pb-24 sm:pt-14",
          width === "narrow" && "w-[min(680px,100%-2rem)]",
          width === "wide" && "w-[min(960px,100%-2rem)]",
          width === "full" && "w-[min(1120px,100%-2rem)]",
        )}
      >
        {children}
      </motion.main>
    </div>
  );
}

export function FlowHeading({ overline, title, children }: { overline: string; title: string; children?: React.ReactNode }) {
  return (
    <div className="mb-8 grid gap-2.5">
      <p className="eyebrow">{overline}</p>
      <h1 className="text-[clamp(26px,3.4vw,34px)] leading-tight font-semibold tracking-[-0.03em] text-balance">{title}</h1>
      {children && <p className="text-[15.5px] text-pretty text-muted-foreground">{children}</p>}
    </div>
  );
}

export function FlowActions({ children }: { children: React.ReactNode }) {
  return <div className="mt-8 flex items-center justify-between gap-3 border-t pt-6">{children}</div>;
}
