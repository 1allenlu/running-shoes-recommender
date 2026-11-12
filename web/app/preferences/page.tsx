"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Feather, Gauge, Mountain, Route, Shuffle, Zap } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";
import { Chips, OptionCards } from "@/components/choice";
import { FlowActions, FlowShell } from "@/components/flow-shell";
import { QuizStep } from "@/components/quiz-step";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Slider } from "@/components/ui/slider";
import { GOAL_OPTIONS } from "@/lib/options";
import { useHydrated, useSession } from "@/lib/store";

const schema = z.object({
  weekly_km: z.number().min(0).max(150),
  goals: z.array(z.string()).min(1, "Pick at least one, even if it's just daily training."),
  surface: z.enum(["road", "trail", "mixed"]),
  feel: z.enum(["soft", "balanced", "firm"]),
  budget_usd: z.number().min(60).max(300).nullable(),
});
type Form = z.infer<typeof schema>;

const STEPS: { key: keyof Form; title: string; description: string }[] = [
  { key: "weekly_km", title: "How far do you run in a typical week?", description: "A rough number is fine. Higher mileage favors more durable, cushioned shoes." },
  { key: "goals", title: "What are you training for?", description: "Pick all that apply." },
  { key: "surface", title: "Where do you run most?", description: "We rank road shoes. Trail picks get a note." },
  { key: "feel", title: "How should they feel underfoot?", description: "Fit always comes first; this breaks ties between shoes that fit." },
  { key: "budget_usd", title: "What's your budget?", description: "We allow about 10% over and flag it." },
];

const PRESETS = [10, 25, 40, 60, 80];

export default function PreferencesPage() {
  const router = useRouter();
  const hydrated = useHydrated();
  const { prefs, profile, set } = useSession();
  const [i, setI] = useState(0);
  const [dir, setDir] = useState<1 | -1>(1);

  const form = useForm<Form>({ resolver: zodResolver(schema), defaultValues: prefs, mode: "onChange" });
  useEffect(() => {
    if (!hydrated) return;
    if (!profile) router.replace("/scan/");
    else form.reset(prefs);
    // Load saved answers once the session has hydrated.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrated]);

  const step = STEPS[i];
  const last = i === STEPS.length - 1;

  async function next() {
    if (!(await form.trigger(step.key))) return;
    set({ prefs: form.getValues() });
    if (last) router.push("/history/");
    else {
      setDir(1);
      setI(i + 1);
    }
  }
  function back() {
    if (i === 0) return router.push("/confirm/");
    setDir(-1);
    setI(i - 1);
  }

  const error = form.formState.errors[step.key]?.message;

  return (
    <FlowShell step="Preferences" progress={(2 + (i + 1) / (STEPS.length + 1)) / 5}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          next();
        }}
      >
        <QuizStep stepKey={step.key} direction={dir} index={i} total={STEPS.length} title={step.title} description={step.description}>
          {step.key === "weekly_km" && (
            <Controller
              control={form.control}
              name="weekly_km"
              render={({ field }) => (
                <div className="grid gap-6 rounded-2xl border bg-card p-6">
                  <p className="text-[44px] leading-none font-semibold tracking-[-0.04em] tabular-nums">
                    {field.value >= 150 ? "150+" : field.value}
                    <span className="ml-1.5 text-[18px] font-medium tracking-normal text-muted-foreground">km / week</span>
                  </p>
                  <Slider min={0} max={150} step={5} value={field.value} onValueChange={(v) => field.onChange(v as number)} aria-label="Weekly distance in km" />
                  <div className="flex flex-wrap gap-2">
                    {PRESETS.map((km) => (
                      <button
                        key={km}
                        type="button"
                        onClick={() => field.onChange(km)}
                        className="rounded-full border px-3 py-1 text-[13px] text-muted-foreground transition-colors hover:border-foreground hover:text-foreground aria-pressed:border-foreground aria-pressed:bg-foreground aria-pressed:text-background"
                        aria-pressed={field.value === km}
                      >
                        {km} km
                      </button>
                    ))}
                  </div>
                </div>
              )}
            />
          )}

          {step.key === "goals" && (
            <Controller
              control={form.control}
              name="goals"
              render={({ field }) => <Chips label="Training goals" value={field.value} onChange={field.onChange} options={GOAL_OPTIONS} />}
            />
          )}

          {step.key === "surface" && (
            <Controller
              control={form.control}
              name="surface"
              render={({ field }) => (
                <OptionCards
                  label="Surface"
                  value={field.value}
                  onChange={field.onChange}
                  options={[
                    { value: "road", label: "Road", description: "Pavement, paths and treadmill", icon: <Route className="size-5" /> },
                    { value: "mixed", label: "Mixed", description: "Mostly road, some gravel or park trails", icon: <Shuffle className="size-5" /> },
                    { value: "trail", label: "Trail", description: "Technical or muddy terrain", icon: <Mountain className="size-5" /> },
                  ]}
                />
              )}
            />
          )}

          {step.key === "feel" && (
            <Controller
              control={form.control}
              name="feel"
              render={({ field }) => (
                <OptionCards
                  label="Preferred feel"
                  value={field.value}
                  onChange={field.onChange}
                  options={[
                    { value: "soft", label: "Soft", description: "Plush, cushioned landings", icon: <Feather className="size-5" /> },
                    { value: "balanced", label: "Balanced", description: "Cushioned but stable", icon: <Gauge className="size-5" /> },
                    { value: "firm", label: "Firm", description: "Responsive, close to the ground", icon: <Zap className="size-5" /> },
                  ]}
                />
              )}
            />
          )}

          {step.key === "budget_usd" && (
            <Controller
              control={form.control}
              name="budget_usd"
              render={({ field }) => (
                <div className="grid gap-6 rounded-2xl border bg-card p-6">
                  <p className="text-[44px] leading-none font-semibold tracking-[-0.04em] tabular-nums">
                    {field.value == null ? "No limit" : <>Up to ${field.value}</>}
                  </p>
                  <Slider
                    min={60}
                    max={300}
                    step={10}
                    disabled={field.value == null}
                    value={field.value ?? 160}
                    onValueChange={(v) => field.onChange(v as number)}
                    aria-label="Budget in US dollars"
                  />
                  <label className="flex w-fit cursor-pointer items-center gap-2.5 text-[14px]">
                    <Checkbox checked={field.value == null} onCheckedChange={(c) => field.onChange(c ? null : 160)} />
                    No budget limit
                  </label>
                </div>
              )}
            />
          )}
          {error && <p className="mt-3 text-[13.5px] text-destructive" role="alert">{error}</p>}
        </QuizStep>

        <FlowActions>
          <Button type="button" variant="ghost" onClick={back}>Back</Button>
          <Button type="submit" className="h-10 px-5">{last ? "Continue to shoe history" : "Next"}</Button>
        </FlowActions>
      </form>
    </FlowShell>
  );
}
