"use client";

import { CircleAlert } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { FlowActions, FlowHeading, FlowShell } from "@/components/flow-shell";
import { ScanDropzone } from "@/components/scan-dropzone";
import { Button, buttonVariants } from "@/components/ui/button";
import { ensureUser } from "@/lib/actions";
import { api, ApiError } from "@/lib/api";
import { useSession } from "@/lib/store";

export default function ScanPage() {
  const router = useRouter();
  const set = useSession((s) => s.set);
  const [files, setFiles] = useState<File[]>([]);
  const [progress, setProgress] = useState<number | null>(null);
  const [readerReady, setReaderReady] = useState(true);

  useEffect(() => {
    api.status().then((s) => setReaderReady(s.llm_ready), () => {});
  }, []);

  async function read() {
    setProgress(0);
    try {
      const userId = await ensureUser();
      const scan = await api.uploadScan(userId, files, setProgress);
      set({ scanId: scan.scan_id, profile: scan.parsed_profile });
      router.push("/confirm/");
    } catch (e) {
      const unavailable = e instanceof ApiError && (e.status === 502 || e.status === 503);
      toast.error(unavailable ? "We couldn't read that scan automatically. Enter your measurements by hand instead." : (e as Error).message);
      setProgress(null);
    }
  }

  return (
    <FlowShell step="Scan">
      <FlowHeading overline="Step 1 of 4" title="Add your foot scan">
        Upload screenshots or the PDF of your in-store 3D scan. We&apos;ll read both feet, and you can check every value next.
      </FlowHeading>

      {!readerReady && (
        <div className="mb-5 grid grid-cols-[20px_1fr] gap-3 rounded-xl bg-warn-soft px-4 py-3.5 text-[14px]">
          <CircleAlert className="size-5 text-warn" />
          <div>
            <p><strong>Automatic scan reading is unavailable right now.</strong> You can still type your measurements in. It takes about a minute.</p>
            <Link href="/confirm/?manual=1" className="mt-1.5 inline-block font-medium underline underline-offset-4">Enter measurements by hand →</Link>
          </div>
        </div>
      )}

      <ScanDropzone files={files} onChange={setFiles} progress={progress} disabled={progress != null} />

      <div className="mt-6 grid gap-2.5 rounded-xl bg-secondary px-5 py-4">
        <p className="eyebrow">For the best read</p>
        <ul className="grid list-disc gap-1 pl-5 text-[14px] text-muted-foreground marker:text-input">
          <li>Include the pages with length, width, arch and instep for both feet.</li>
          <li>Screenshots work. Crop out anything personal you don&apos;t want to share.</li>
        </ul>
      </div>

      <FlowActions>
        <Link href="/" className={buttonVariants({ variant: "ghost" })}>Back</Link>
        <div className="flex gap-2">
          <Link href="/confirm/?manual=1" className={buttonVariants({ variant: "outline", className: "max-sm:hidden" })}>Enter by hand</Link>
          <Button onClick={read} disabled={!files.length || progress != null}>
            {progress != null ? "Reading…" : "Read my scan"}
          </Button>
        </div>
      </FlowActions>
    </FlowShell>
  );
}
