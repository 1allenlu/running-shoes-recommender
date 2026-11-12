"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { toast } from "sonner";
import { BandScale } from "@/components/band-scale";
import { Segmented } from "@/components/choice";
import { FlowActions, FlowHeading, FlowShell } from "@/components/flow-shell";
import { WidthScale } from "@/components/width-scale";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ensureUser } from "@/lib/actions";
import { api, type Foot, type FootProfile } from "@/lib/api";
import { blankProfile, SCALES } from "@/lib/foot";
import { useHydrated, useSession } from "@/lib/store";
import { cn } from "@/lib/utils";

function Confirm() {
  const router = useRouter();
  const manual = useSearchParams().get("manual") === "1";
  const hydrated = useHydrated();
  const { profile: saved, scanId, set } = useSession();
  const [profile, setProfile] = useState<FootProfile | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!hydrated || profile) return;
    if (saved) setProfile(structuredClone(saved));
    else if (manual) setProfile(blankProfile());
    else router.replace("/scan/");
  }, [hydrated, saved, manual, profile, router]);

  if (!profile) return <FlowShell step="Confirm" width="wide"><div className="h-96" /></FlowShell>;

  const update = (side: "left" | "right", patch: Partial<Foot>) =>
    setProfile((p) => (p ? { ...p, [side]: { ...p[side], ...patch } } : p));
  const longer = Number(profile.left.us_size) >= Number(profile.right.us_size) ? "left" : "right";

  async function save() {
    if (!profile) return;
    for (const side of ["left", "right"] as const) {
      const size = Number(profile[side].us_size);
      if (!(size >= 3 && size <= 18)) {
        toast.error(`Enter a US size between 3 and 18 for your ${side} foot.`);
        return;
      }
    }
    setSaving(true);
    try {
      const userId = await ensureUser();
      if (scanId && !manual) await api.confirmScan(userId, scanId, profile);
      else {
        const scan = await api.manualScan(userId, profile);
        set({ scanId: scan.scan_id });
      }
      set({ profile });
      router.push("/preferences/");
    } catch (e) {
      toast.error((e as Error).message);
      setSaving(false);
    }
  }

  return (
    <FlowShell step="Confirm" width="wide">
      <FlowHeading overline="Step 2 of 4" title={manual && !saved ? "Enter your measurements" : "Check your measurements"}>
        {manual && !saved
          ? "Copy the values from your scan report. Drag the L and R arrows to where your report puts each foot."
          : "Compare each value with your report and fix anything that's off. Drag the L and R arrows, or use arrow keys."}
      </FlowHeading>

      <div className="grid gap-4">
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border bg-card px-5 py-4">
          <div>
            <p className="text-sm font-semibold">Size scale</p>
            <p className="text-[13px] text-muted-foreground">The scale your report&apos;s US sizes use.</p>
          </div>
          <Segmented
            label="Size scale"
            className="w-56"
            value={profile.sex_scale}
            onChange={(v) => setProfile({ ...profile, sex_scale: v })}
            options={[
              { value: "men", label: "Men's" },
              { value: "women", label: "Women's" },
            ]}
          />
        </div>

        <div className="rounded-2xl border bg-card px-5">
          <div className="grid gap-4 py-5 sm:grid-cols-2">
            {(["left", "right"] as const).map((side) => (
              <div key={side} className="grid gap-2">
                <div className="flex items-center justify-between">
                  <Label htmlFor={`${side}-size`}>{side === "left" ? "Left" : "Right"} foot · US size</Label>
                  <span className={cn("rounded-full bg-volt-soft px-2 py-0.5 text-[11.5px] font-medium", longer !== side && "invisible")}>Longer foot</span>
                </div>
                <Input
                  id={`${side}-size`}
                  type="number"
                  inputMode="decimal"
                  min={3}
                  max={18}
                  step={0.5}
                  value={Number.isNaN(profile[side].us_size) ? "" : profile[side].us_size}
                  onChange={(e) => update(side, { us_size: parseFloat(e.target.value) })}
                  className="h-11 text-[16px] tabular-nums"
                />
              </div>
            ))}
          </div>
          <p className="-mt-2 pb-4 text-[12.5px] text-muted-foreground">We size you from your longer foot.</p>
          <div className="divide-y border-t">
            <WidthScale
              left={profile.left.width}
              right={profile.right.width}
              onChange={(side, width) => update(side, { width })}
            />
            {SCALES.map((s) => (
              <BandScale
                key={s.key}
                scaleKey={s.key}
                label={s.label}
                hint={s.hint}
                bands={s.bands}
                optional={s.optional}
                left={profile.left}
                right={profile.right}
                onChange={(side, value) => update(side, { [s.key]: value } as Partial<Foot>)}
              />
            ))}
          </div>
        </div>
      </div>

      <FlowActions>
        <Link href="/scan/" className={buttonVariants({ variant: "ghost" })}>Back</Link>
        <Button onClick={save} disabled={saving}>{saving ? "Saving…" : "Looks right, continue"}</Button>
      </FlowActions>
    </FlowShell>
  );
}

export default function ConfirmPage() {
  return (
    <Suspense>
      <Confirm />
    </Suspense>
  );
}
