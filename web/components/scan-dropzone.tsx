"use client";

import { FileText, Upload, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo } from "react";
import { useDropzone, type FileRejection } from "react-dropzone";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

const ACCEPT = { "image/png": [".png"], "image/jpeg": [".jpg", ".jpeg"], "image/webp": [".webp"], "application/pdf": [".pdf"] };
const MAX_SIZE = 15 * 1024 * 1024;
const MAX_FILES = 8;

/** Drag-and-drop for scan screenshots / PDF, with previews and per-upload progress. */
export function ScanDropzone({
  files,
  onChange,
  progress,
  disabled,
}: {
  files: File[];
  onChange: (files: File[]) => void;
  progress: number | null; // 0-100 while uploading
  disabled?: boolean;
}) {
  const previews = useMemo(
    () => files.map((f) => (f.type.startsWith("image/") ? URL.createObjectURL(f) : null)),
    [files],
  );
  useEffect(() => () => previews.forEach((u) => u && URL.revokeObjectURL(u)), [previews]);

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    accept: ACCEPT,
    maxSize: MAX_SIZE,
    maxFiles: MAX_FILES,
    noClick: true,
    disabled,
    onDrop: (accepted: File[], rejected: FileRejection[]) => {
      rejected.forEach((r) =>
        toast.error(
          r.errors[0]?.code === "file-too-large"
            ? `${r.file.name} is over 15 MB.`
            : r.errors[0]?.code === "too-many-files"
              ? `Add up to ${MAX_FILES} files.`
              : `${r.file.name} isn't a PNG, JPEG, WebP or PDF.`,
        ),
      );
      const fresh = accepted.filter((f) => !files.some((g) => g.name === f.name && g.size === f.size));
      onChange([...files, ...fresh].slice(0, MAX_FILES));
    },
  });

  return (
    <div className="grid gap-3">
      <div
        {...getRootProps({
          onClick: open,
          className: cn(
            "grid cursor-pointer justify-items-center gap-1.5 rounded-2xl border-[1.5px] border-dashed bg-card px-6 py-12 text-center transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/30",
            isDragActive ? "border-foreground bg-secondary" : "border-input hover:border-foreground/60",
            disabled && "pointer-events-none opacity-60",
          ),
        })}
      >
        <input {...getInputProps()} aria-label="Scan files" />
        <motion.span
          animate={isDragActive ? { y: -4, scale: 1.05 } : { y: 0, scale: 1 }}
          className="mb-2 grid size-11 place-items-center rounded-xl border bg-secondary"
        >
          <Upload className="size-5" />
        </motion.span>
        <p className="text-[15.5px] font-semibold">{isDragActive ? "Drop to add" : "Drag your scan report here"}</p>
        <p className="text-[13.5px] text-muted-foreground">
          or <span className="text-foreground underline underline-offset-4">browse files</span> · PNG, JPEG, WebP or PDF, up to 15 MB
        </p>
      </div>

      <ul className="grid gap-2" aria-live="polite">
        <AnimatePresence initial={false}>
          {files.map((f, i) => (
            <motion.li
              key={`${f.name}-${f.size}`}
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden"
            >
              <div className="relative flex items-center gap-3 overflow-hidden rounded-xl border bg-card p-2 pl-2.5">
                {previews[i] ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={previews[i]!} alt="" className="size-10 rounded-lg border object-cover" />
                ) : (
                  <span className="grid size-10 place-items-center rounded-lg border bg-secondary"><FileText className="size-4 text-muted-foreground" /></span>
                )}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[14px] font-medium">{f.name}</p>
                  <p className="text-[12.5px] text-muted-foreground tabular-nums">
                    {progress == null ? `${Math.max(1, Math.round(f.size / 1024))} KB` : progress < 100 ? `Uploading… ${progress}%` : "Reading your scan…"}
                  </p>
                </div>
                {progress == null && (
                  <button
                    type="button"
                    onClick={() => onChange(files.filter((_, j) => j !== i))}
                    className="grid size-8 place-items-center rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground"
                    aria-label={`Remove ${f.name}`}
                  >
                    <X className="size-4" />
                  </button>
                )}
                {progress != null && (
                  <span className="absolute inset-x-0 bottom-0 h-0.5 bg-muted">
                    <motion.span
                      className={cn("block h-full bg-foreground", progress >= 100 && "animate-pulse")}
                      animate={{ width: `${progress}%` }}
                    />
                  </span>
                )}
              </div>
            </motion.li>
          ))}
        </AnimatePresence>
      </ul>
    </div>
  );
}
