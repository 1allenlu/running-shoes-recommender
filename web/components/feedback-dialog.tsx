"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { api, type IssueTag, type Pick, type Rating } from "@/lib/api";
import { ISSUE_OPTIONS } from "@/lib/options";
import { Chips, Segmented } from "./choice";
import { sizeText } from "./shoe-card";

export function FeedbackDialog({
  pick,
  userId,
  taskId,
  onClose,
}: {
  pick: Pick | null;
  userId: string;
  taskId: string;
  onClose: () => void;
}) {
  const [outcome, setOutcome] = useState<Rating | null>(null);
  const [kept, setKept] = useState<"yes" | "no" | null>(null);
  const [issues, setIssues] = useState<IssueTag[]>([]);
  const [notes, setNotes] = useState("");
  const [sending, setSending] = useState(false);

  const close = () => {
    setOutcome(null);
    setKept(null);
    setIssues([]);
    setNotes("");
    onClose();
  };

  async function send() {
    if (!pick || !outcome) return;
    setSending(true);
    try {
      await api.feedback(userId, {
        recommendation_id: taskId,
        shoe_id: pick.shoe_id,
        us_size: pick.size.us_size,
        width: pick.size.width as "standard" | "wide" | "extra-wide",
        outcome,
        kept: kept == null ? null : kept === "yes",
        issues,
        notes: notes.trim() || null,
      });
      toast.success("Thanks. Your next picks will use this.");
      close();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSending(false);
    }
  }

  return (
    <Dialog open={pick != null} onOpenChange={(open) => !open && close()}>
      <DialogContent className="gap-0 p-0 sm:max-w-[520px]">
        <DialogHeader className="p-6 pb-2">
          <DialogTitle className="text-[19px] tracking-[-0.02em]">How did they fit?</DialogTitle>
          <DialogDescription>{pick && `${pick.brand} ${pick.model} ${pick.version} · ${sizeText(pick)}`}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-5 px-6 py-4">
          <div className="grid gap-2">
            <Label>Overall</Label>
            <Segmented
              label="Overall"
              value={outcome}
              onChange={setOutcome}
              options={[
                { value: "loved", label: "Loved them" },
                { value: "fine", label: "They're fine" },
                { value: "hated", label: "Didn't work" },
              ]}
            />
          </div>
          <div className="grid gap-2">
            <Label>Did you keep them?</Label>
            <Segmented
              label="Did you keep them?"
              className="w-fit"
              value={kept}
              onChange={setKept}
              options={[
                { value: "yes", label: "Kept" },
                { value: "no", label: "Returned" },
              ]}
            />
          </div>
          <div className="grid gap-2">
            <Label>Any fit issues?</Label>
            <Chips label="Fit issues" size="sm" value={issues} onChange={setIssues} options={ISSUE_OPTIONS} />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="fb-notes">Notes <span className="font-normal text-muted-foreground">Optional</span></Label>
            <Textarea id="fb-notes" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. Toe box felt tight after 10K, heel stayed put." rows={3} />
          </div>
          <p className="text-[12.5px] text-muted-foreground">Your next picks use this. If a shoe didn&apos;t work, we won&apos;t suggest it again.</p>
        </div>
        <DialogFooter className="m-0 rounded-b-xl border-t bg-secondary/50 px-6 py-4">
          <Button variant="ghost" onClick={close}>Cancel</Button>
          <Button onClick={send} disabled={!outcome || sending}>{sending ? "Sending…" : "Send feedback"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
