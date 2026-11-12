import Link from "next/link";
import { cn } from "@/lib/utils";

export function Logo({ className, compact = false }: { className?: string; compact?: boolean }) {
  return (
    <Link href="/" className={cn("inline-flex items-center gap-2.5 text-[16.5px] font-semibold tracking-[-0.025em]", className)} aria-label="LastFit home">
      <svg viewBox="0 0 32 32" className="size-[26px]" aria-hidden="true">
        <rect width="32" height="32" rx="8" className="fill-foreground" />
        <path d="M9 8v16h14" fill="none" stroke="var(--volt)" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className={cn(compact && "max-sm:sr-only")}>LastFit</span>
    </Link>
  );
}
