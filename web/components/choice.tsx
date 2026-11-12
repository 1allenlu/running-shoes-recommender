"use client";

import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

/** Single choice as a segmented control (radiogroup). */
export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
  className,
}: {
  value: T | null;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
  className?: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cn("flex gap-0.5 rounded-[10px] border bg-secondary p-[3px]", className)}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "h-8 min-w-0 flex-1 truncate rounded-[7px] px-3 text-[13.5px] font-medium text-muted-foreground transition-all outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring",
            value === o.value && "bg-card text-foreground shadow-[0_1px_2px_rgb(0_0_0/0.08),0_0_0_1px_var(--border)]",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Multiple choice as pill chips (toggle buttons). */
export function Chips<T extends string>({
  value,
  options,
  onChange,
  label,
  size = "md",
}: {
  value: T[];
  options: { value: T; label: string }[];
  onChange: (v: T[]) => void;
  label: string;
  size?: "sm" | "md";
}) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-2">
      {options.map((o) => {
        const on = value.includes(o.value);
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(on ? value.filter((v) => v !== o.value) : [...value, o.value])}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border font-medium transition-all outline-none focus-visible:ring-2 focus-visible:ring-ring",
              size === "md" ? "h-9 px-4 text-[13.5px]" : "h-7 px-3 text-[12.5px]",
              on ? "border-foreground bg-foreground text-background" : "border-input bg-card text-muted-foreground hover:border-muted-foreground hover:text-foreground",
            )}
          >
            {on && <Check className="size-3.5" strokeWidth={2.5} />}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/** Single choice as large option cards with a description. */
export function OptionCards<T extends string>({
  value,
  options,
  onChange,
  label,
  columns = 3,
}: {
  value: T | null;
  options: { value: T; label: string; description: string; icon?: React.ReactNode }[];
  onChange: (v: T) => void;
  label: string;
  columns?: 2 | 3;
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cn("grid gap-3", columns === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2")}>
      {options.map((o) => {
        const on = value === o.value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(o.value)}
            className={cn(
              "relative grid gap-1 rounded-xl border bg-card p-4 text-left transition-all outline-none hover:border-muted-foreground focus-visible:ring-2 focus-visible:ring-ring",
              on && "border-foreground bg-secondary shadow-[inset_0_0_0_1px_var(--foreground)]",
            )}
          >
            {o.icon && <span className="mb-2 text-muted-foreground">{o.icon}</span>}
            <span className="text-[15px] font-semibold">{o.label}</span>
            <span className="text-[13px] leading-snug text-muted-foreground">{o.description}</span>
            {on && (
              <span className="absolute top-3 right-3 grid size-5 place-items-center rounded-full bg-foreground text-background">
                <Check className="size-3" strokeWidth={3} />
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
