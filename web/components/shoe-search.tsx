"use client";

import { Plus, Search } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { api, type ShoeHit } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Catalog autocomplete (GET /shoes/search) that also accepts any free-text name. */
export function ShoeSearch({ onPick, exclude }: { onPick: (name: string) => void; exclude: string[] }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<ShoeHit[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) return setHits([]);
    const t = setTimeout(() => {
      api.searchShoes(term).then((r) => setHits(r.slice(0, 6)), () => setHits([]));
    }, 140);
    return () => clearTimeout(t);
  }, [q]);

  const taken = new Set(exclude.map((e) => e.toLowerCase()));
  const options = [
    ...hits.filter((h) => !taken.has(h.name.toLowerCase())).map((h) => ({ label: h.name, catalog: true })),
    ...(q.trim() && !hits.some((h) => h.name.toLowerCase() === q.trim().toLowerCase()) && !taken.has(q.trim().toLowerCase())
      ? [{ label: q.trim(), catalog: false }]
      : []),
  ];

  const choose = (name: string) => {
    onPick(name);
    setQ("");
    setHits([]);
    setActive(0);
    input.current?.focus();
  };

  return (
    <div className="relative">
      <div className="flex h-12 items-center gap-2.5 rounded-xl border bg-card px-3.5 focus-within:border-foreground focus-within:ring-3 focus-within:ring-ring/10">
        <Search className="size-4 text-muted-foreground" />
        <input
          ref={input}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
            setActive(0);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive((a) => Math.min(a + 1, options.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            } else if (e.key === "Enter" && options[active]) {
              e.preventDefault();
              choose(options[active].label);
            } else if (e.key === "Escape") setOpen(false);
          }}
          role="combobox"
          aria-expanded={open && options.length > 0}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-label="Add a shoe you've run in"
          placeholder="Search a shoe, e.g. Ghost 17"
          className="h-full flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted-foreground"
        />
      </div>
      {open && options.length > 0 && (
        <ul id={listId} role="listbox" className="absolute inset-x-0 top-[calc(100%+6px)] z-20 overflow-hidden rounded-xl border bg-popover p-1 shadow-lg">
          {options.map((o, i) => (
            <li
              key={`${o.label}-${o.catalog}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(o.label)}
              onMouseEnter={() => setActive(i)}
              className={cn("flex cursor-pointer items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-[14px]", i === active && "bg-secondary")}
            >
              <span className="flex items-center gap-2">
                {!o.catalog && <Plus className="size-3.5 text-muted-foreground" />}
                {o.catalog ? o.label : <>Add “{o.label}”</>}
              </span>
              <span className="text-[12px] text-muted-foreground">{o.catalog ? "In catalog" : "Not in catalog"}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
