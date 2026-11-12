"use client";

import { useEffect, useState } from "react";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { FootProfile, IssueTag, Rating } from "./api";

export type PrefsDraft = {
  weekly_km: number;
  goals: string[];
  surface: "road" | "trail" | "mixed";
  feel: "soft" | "balanced" | "firm";
  budget_usd: number | null;
};

export type HistoryDraft = { raw_name: string; rating: Rating; issues: IssueTag[] };

type Session = {
  userId: string | null;
  scanId: number | null;
  taskId: string | null;
  profile: FootProfile | null; // parsed or typed; confirmed on the server when the runner confirms
  prefs: PrefsDraft;
  history: HistoryDraft[];
  set: (patch: Partial<Omit<Session, "set" | "reset">>) => void;
  reset: () => void;
};

export const defaultPrefs = (): PrefsDraft => ({
  weekly_km: 30,
  goals: [],
  surface: "road",
  feel: "balanced",
  budget_usd: 160,
});

const empty = () => ({ userId: null, scanId: null, taskId: null, profile: null, prefs: defaultPrefs(), history: [] });

export const useSession = create<Session>()(
  persist(
    (set) => ({
      ...empty(),
      set: (patch) => set(patch),
      reset: () => set(empty()),
    }),
    { name: "lastfit.session", storage: createJSONStorage(() => localStorage), version: 1 },
  ),
);

/** True once the persisted session has loaded (avoids a flash of empty state). */
export function useHydrated() {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (useSession.persist.hasHydrated()) setReady(true);
    return useSession.persist.onFinishHydration(() => setReady(true));
  }, []);
  return ready;
}
