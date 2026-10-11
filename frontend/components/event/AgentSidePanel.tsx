"use client";

import { useState, useRef, useEffect } from "react";
import {
  Sparkles, X, ArrowUp, PanelRightClose, PanelRightOpen, AlertCircle, Check,
} from "lucide-react";
import { api } from "@/lib/api";
import { Button, Note, cx } from "@/components/ui";
import AgentActivity, { useAgentSteps } from "@/components/AgentActivity";

const SUGGESTIONS = [
  "Make the menu cheaper",
  "Add a non-alcoholic option",
  "Use only 3 cocktails",
  "Replace the gin cocktail",
];

const AGENT_STEPS = [
  "Reading the event",
  "Working out the change",
  "Recalculating quantities",
  "Updating costs",
];

type Turn = { role: "user" | "assistant"; content: string };

/**
 * The agent, as a panel beside the work rather than a page you go to.
 *
 * It shows the agent's operational steps while it works, then its answer. When
 * a turn changes the event, the workspace behind it reloads — the result the
 * person cares about is the updated numbers, not the message.
 */
export default function AgentSidePanel({
  eventId, currentTab, open, onOpenChange, onChanged,
}: {
  eventId: string;
  currentTab?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onChanged: () => void;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const step = useAgentSteps(busy, AGENT_STEPS);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const params = new URLSearchParams(window.location.search);

    if (params.get("agent") !== "1") return;

    onOpenChange(true);

    params.delete("agent");

    const remaining = params.toString();

    const cleanUrl =
      window.location.pathname +
      (remaining ? `?${remaining}` : "") +
      window.location.hash;

    window.history.replaceState({}, "", cleanUrl);
  }, [onOpenChange]);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [turns, busy]);

  // This event's conversation, restored. Held only in component state before,
  // so closing the tab lost everything that had been discussed about the event
  // — and the next person to open it had no idea why the menu looked like that.
  useEffect(() => {
    let alive = true;
    api.getEventMessages(eventId)
      .then((r) => {
        if (!alive || r.messages.length === 0) return;
        setTurns(r.messages.map((m) => ({ role: m.role, content: m.content })));
      })
      .catch(() => { /* a missing transcript must not break the panel */ });
    return () => { alive = false; };
  }, [eventId]);

  async function send(message?: string) {
    const content = (message ?? text).trim();
    if (!content || busy) return;
    const next: Turn[] = [...turns, { role: "user", content }];
    setTurns(next);
    setText("");
    setBusy(true);
    setError(null);
    try {
      const res = await api.chat(eventId, next, currentTab);
      setTurns([...next, { role: "assistant", content: res.response }]);
      // The agent's tools write to the event, so refresh what's on screen.
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "The agent could not respond");
      setTurns(next);
    } finally {
      setBusy(false);
    }
  }

  const body = (
    <div className="flex flex-col h-full">
      <header className="flex items-center justify-between gap-2 px-4 h-14 border-b border-line shrink-0">
        <div className="flex items-center gap-2">
          <Sparkles size={15} strokeWidth={1.75} className="text-accent" />
          <span className="text-[13.5px] font-medium">Happy Hour AI</span>
        </div>
        <button
          onClick={() => onOpenChange(false)}
          aria-label="Close agent panel"
          className="w-8 h-8 grid place-items-center rounded-lg text-ink-3 hover:bg-sunk transition-colors"
        >
          <span className="lg:hidden"><X size={17} /></span>
          <span className="hidden lg:block"><PanelRightClose size={16} /></span>
        </button>
      </header>

      <div ref={scroller} className="flex-1 overflow-y-auto px-4 py-4 flex flex-col gap-3">
        {turns.length === 0 && !busy && (
          <div className="text-center py-6">
            <p className="text-[13.5px] text-ink-2 mb-1">Continue planning this event.</p>
            <p className="text-[12.5px] text-ink-4 mb-4 leading-relaxed">
              Tell me what you want to change. I will keep working on this same event.
            </p>
            <div className="flex flex-col gap-1.5">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="text-left text-[13px] text-ink-2 bg-surface border border-line rounded-lg px-3 py-2 hover:border-line-2 hover:text-ink transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((t, i) =>
          t.role === "user" ? (
            <div key={i} className="self-end max-w-[85%] bg-ink text-white rounded-xl rounded-br-sm px-3 py-2 text-[13px] leading-relaxed hh-rise" dir="auto">
              {t.content}
            </div>
          ) : (
            <div key={i} className="hh-rise">
              <div className="flex items-center gap-1.5 mb-1.5">
                <Check size={12} strokeWidth={2.5} className="text-good" />
                <span className="text-[11.5px] text-ink-4">Updated the event</span>
              </div>
              <div
                className="text-[13px] text-ink-2 leading-relaxed whitespace-pre-wrap bg-surface border border-line rounded-xl rounded-bl-sm px-3 py-2.5"
                dir="auto"
              >
                {t.content}
              </div>
            </div>
          )
        )}

        {busy && <AgentActivity steps={AGENT_STEPS} activeIndex={step} className="hh-rise" />}

        {error && (
          <Note tone="warn" icon={AlertCircle}>{error}</Note>
        )}
      </div>

      <div className="p-3 border-t border-line shrink-0">
        <div className="flex items-end gap-2 bg-surface border border-line-2 rounded-xl px-3 py-2 focus-within:border-accent/50">
          <textarea
            rows={1}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
            }}
            disabled={busy}
            dir="auto"
            placeholder="Make the menu cheaper…"
            aria-label="Ask the agent to change this event"
            className="flex-1 min-w-0 resize-none bg-transparent outline-none focus:outline-none focus-visible:outline-none text-[13.5px] leading-relaxed placeholder:text-ink-4 max-h-24"
          />
          <button
            onClick={() => send()}
            disabled={busy || !text.trim()}
            aria-label="Send"
            className={cx(
              "w-7 h-7 grid place-items-center rounded-lg shrink-0 transition-colors",
              text.trim() && !busy ? "bg-accent text-white hover:bg-accent-hi" : "bg-sunk text-ink-4"
            )}
          >
            <ArrowUp size={14} strokeWidth={2.25} />
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop: a real column, so the workspace stays visible while you type. */}
      <aside
        className={cx(
          "hidden lg:flex flex-col shrink-0 h-screen sticky top-0 border-l border-line bg-canvas",
          "transition-[width] duration-200 overflow-hidden",
          open ? "w-[340px]" : "w-0 border-l-0"
        )}
      >
        {open && body}
      </aside>
      {/* HH_EVENT_AGENT_LAUNCHER_REMOVED */}

      {/* Mobile: a sheet. */}
      {open && (
        <div className="lg:hidden fixed inset-0 z-50 flex justify-end">
          <button
            aria-label="Close agent panel"
            className="absolute inset-0 bg-ink/25"
            onClick={() => onOpenChange(false)}
          />
          <div className="relative w-full max-w-[380px] h-full bg-canvas border-l border-line hh-rise">
            {body}
          </div>
        </div>
      )}
    </>
  );
}
