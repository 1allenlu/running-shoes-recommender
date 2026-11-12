"use client";

import { api } from "./api";
import { useSession } from "./store";

/** The runner's user id, creating an anonymous user on first use. */
export async function ensureUser(): Promise<string> {
  const { userId, set } = useSession.getState();
  if (userId) return userId;
  const user = await api.createUser();
  set({ userId: user.id });
  return user.id;
}

/** Save preferences + history and start ranking; returns the task id. */
export async function startRecommendation(): Promise<string> {
  const userId = await ensureUser();
  const { prefs, history, set } = useSession.getState();
  await api.putPreferences(userId, { ...prefs, budget_usd: prefs.budget_usd ?? null });
  await api.putHistory(
    userId,
    history.map((h) => ({ raw_name: h.raw_name, rating: h.rating, issues: h.issues })),
  );
  const task = await api.recommend(userId);
  set({ taskId: task.task_id });
  return task.task_id;
}
