"use client";

import { ArrowUp, Loader2, Sparkles, Square } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { api, ApiError, type Recommendation } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ShoeMini } from "./shoe-card";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  picks?: Recommendation;
  tools?: string[];
  error?: string;
  pending?: boolean;
};

const SUGGESTIONS = [
  { title: "Compare #1 and #2", prompt: "Compare my #1 and #2 picks. Which fits my feet better and why?" },
  { title: "Something under $130", prompt: "Show me something under $130." },
  { title: "Softer options", prompt: "I'd like something softer. What changes?" },
  { title: "I hated a shoe", prompt: "I hated the Pegasus, please leave it out." },
];

const TOOL_LABELS: Record<string, string> = {
  rerank: "Re-ranking shoes for your feet",
  compare: "Comparing fit factors",
  get_profile: "Reading your foot profile",
  get_fit_notes: "Checking fit notes",
  get_offers: "Checking stock",
  record_feedback: "Saving your feedback",
};

/** Follow-up chat under the results, streamed from POST /users/{id}/chat. */
export function ChatPanel({ userId, picksLabel }: { userId: string; picksLabel?: string }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [available, setAvailable] = useState<boolean | null>(null);
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    api.status().then((s) => setAvailable(s.llm_ready), () => setAvailable(false));
  }, []);

  useEffect(() => {
    if (messages.length) bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages]);

  const patch = (id: string, fn: (m: Message) => Message) =>
    setMessages((all) => all.map((m) => (m.id === id ? fn(m) : m)));

  async function send(text: string) {
    const content = text.trim();
    if (!content || busy) return;
    const user: Message = { id: crypto.randomUUID(), role: "user", content };
    const reply: Message = { id: crypto.randomUUID(), role: "assistant", content: "", pending: true, tools: [] };
    const history = [...messages, user]
      .filter((m) => !m.error && m.content)
      .map(({ role, content }) => ({ role, content }));
    setMessages((all) => [...all, user, reply]);
    setInput("");
    setBusy(true);
    abort.current = new AbortController();
    try {
      for await (const ev of api.chat(userId, history, abort.current.signal)) {
        if (ev.event === "token") patch(reply.id, (m) => ({ ...m, content: m.content + ev.data.text }));
        else if (ev.event === "tool")
          patch(reply.id, (m) => ({ ...m, tools: m.tools?.includes(ev.data.name) ? m.tools : [...(m.tools ?? []), ev.data.name] }));
        else if (ev.event === "picks") patch(reply.id, (m) => ({ ...m, picks: ev.data }));
        else if (ev.event === "error") patch(reply.id, (m) => ({ ...m, error: "Something went wrong answering that. Please try again." }));
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        const msg = e instanceof ApiError && e.status === 503 ? "Chat is unavailable right now." : (e as Error).message;
        patch(reply.id, (m) => ({ ...m, error: msg }));
      }
    } finally {
      patch(reply.id, (m) => ({ ...m, pending: false }));
      setBusy(false);
      abort.current = null;
      box.current?.focus();
    }
  }

  return (
    <section className="overflow-hidden rounded-2xl border bg-card" aria-labelledby="chat-title">
      <header className="flex items-center justify-between gap-3 border-b px-5 py-4">
        <div className="flex items-center gap-3">
          <span className="grid size-8 place-items-center rounded-lg bg-volt text-volt-foreground"><Sparkles className="size-4" /></span>
          <div>
            <h2 id="chat-title" className="text-[15px] font-semibold tracking-[-0.01em]">Ask about your picks</h2>
            <p className="text-[12.5px] text-muted-foreground">
              Answers come from LastFit&apos;s fit model and catalog{picksLabel ? ` · ${picksLabel}` : ""}.
            </p>
          </div>
        </div>
        {messages.length > 0 && (
          <Button variant="ghost" size="sm" onClick={() => setMessages([])} disabled={busy}>Clear</Button>
        )}
      </header>

      <div className="max-h-[560px] min-h-[180px] overflow-y-auto px-5 py-5" aria-live="polite">
        {messages.length === 0 ? (
          <div className="grid gap-4">
            <p className="text-[14px] text-muted-foreground">
              Try a follow-up. We&apos;ll re-run the ranking for you, never guess.
            </p>
            <div className={cn("grid min-w-0 gap-2 sm:grid-cols-2", !available && "pointer-events-none opacity-50")}>
              {SUGGESTIONS.map((s, i) => (
                <motion.button
                  key={s.title}
                  type="button"
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.05 * i }}
                  disabled={!available}
                  onClick={() => send(s.prompt)}
                  className="min-w-0 rounded-xl border px-4 py-3 text-left transition-colors hover:bg-secondary"
                >
                  <span className="block text-[14px] font-medium">{s.title}</span>
                  <span className="block truncate text-[12.5px] text-muted-foreground">{s.prompt}</span>
                </motion.button>
              ))}
            </div>
          </div>
        ) : (
          <div className="grid gap-5">
            <AnimatePresence initial={false}>
              {messages.map((m) => (
                <motion.div
                  key={m.id}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}
                >
                  {m.role === "user" ? (
                    <p className="max-w-[80%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-[14px] whitespace-pre-wrap text-primary-foreground">
                      {m.content}
                    </p>
                  ) : (
                    <div className="grid w-full max-w-[92%] gap-3">
                      {m.tools?.map((t) => (
                        <p key={t} className="flex items-center gap-2 text-[12.5px] text-muted-foreground">
                          {m.pending && !m.content ? <Loader2 className="size-3.5 animate-spin" /> : <span className="size-1.5 rounded-full bg-good" />}
                          {TOOL_LABELS[t] ?? t}
                        </p>
                      ))}
                      {m.picks && (
                        <div className="grid gap-2">
                          {m.picks.picks.map((p) => <ShoeMini key={p.shoe_id} pick={p} />)}
                          {m.picks.disclosure && <p className="text-[11.5px] text-muted-foreground">{m.picks.disclosure}</p>}
                        </div>
                      )}
                      {(m.content || (m.pending && !m.tools?.length)) && (
                        <p className="text-[14.5px] leading-relaxed whitespace-pre-wrap">
                          {m.content}
                          {m.pending && <span className="ml-0.5 inline-block h-4 w-1.5 translate-y-0.5 animate-pulse rounded-sm bg-foreground" />}
                        </p>
                      )}
                      {m.error && <p className="rounded-lg bg-destructive/10 px-3 py-2 text-[13px] text-destructive">{m.error}</p>}
                    </div>
                  )}
                </motion.div>
              ))}
            </AnimatePresence>
            <div ref={bottom} />
          </div>
        )}
      </div>

      <form
        className="border-t p-3"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <div className="flex items-end gap-2 rounded-xl border bg-background p-1.5 pl-3 focus-within:border-foreground focus-within:ring-3 focus-within:ring-ring/10">
          <textarea
            ref={box}
            rows={1}
            value={input}
            disabled={available === false}
            onChange={(e) => {
              setInput(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = `${Math.min(e.target.scrollHeight, 140)}px`;
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                send(input);
              }
            }}
            placeholder={available === false ? "Chat is unavailable right now" : "Ask a follow-up, e.g. something under $130"}
            aria-label="Message"
            className="max-h-[140px] min-h-9 flex-1 resize-none bg-transparent py-2 text-[14.5px] outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed"
          />
          {busy ? (
            <Button type="button" size="icon" variant="outline" onClick={() => abort.current?.abort()} aria-label="Stop">
              <Square className="size-3.5 fill-current" />
            </Button>
          ) : (
            <Button type="submit" size="icon" disabled={!input.trim() || !available} aria-label="Send">
              <ArrowUp />
            </Button>
          )}
        </div>
        {available === false && (
          <p className="px-1 pt-2 text-[12px] text-muted-foreground">The assistant needs an AI model that isn&apos;t configured on this server. Your picks above don&apos;t depend on it.</p>
        )}
      </form>
    </section>
  );
}
