"use client";

import { useEffect, useRef, useState } from "react";
import { api, loadToken, type AgentTrace, type Restaurant } from "@/lib/api";

interface Msg {
  role: "customer" | "agent";
  text: string;
  trace?: AgentTrace;
}

export default function SandboxPage() {
  const [restaurants, setRestaurants] = useState<Restaurant[]>([]);
  const [rid, setRid] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!loadToken()) {
      window.location.href = "/login";
      return;
    }
    api.myRestaurants().then((r) => {
      setRestaurants(r);
      if (r[0]) setRid(r[0].id);
    });
  }, []);

  useEffect(() => bottom.current?.scrollIntoView({ behavior: "smooth" }), [messages]);

  async function ensureConversation(): Promise<string> {
    if (conversationId) return conversationId;
    const ref = await api.startSandbox(rid);
    setConversationId(ref.conversation_id);
    return ref.conversation_id;
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() || !rid) return;
    const text = input.trim();
    setInput("");
    setMessages((m) => [...m, { role: "customer", text }]);
    setBusy(true);
    setError(null);
    try {
      const cid = await ensureConversation();
      const res = await api.sandboxTurn(rid, cid, text);
      setMessages((m) => [...m, { role: "agent", text: res.reply, trace: res.trace }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Turn failed");
    } finally {
      setBusy(false);
    }
  }

  function resetConversation(newRid?: string) {
    setConversationId(null);
    setMessages([]);
    if (newRid) setRid(newRid);
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col px-6 py-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Agent sandbox</h1>
        <select
          value={rid}
          onChange={(e) => resetConversation(e.target.value)}
          className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        >
          {restaurants.map((r) => (
            <option key={r.id} value={r.id}>{r.name}</option>
          ))}
        </select>
      </div>
      <p className="mt-1 text-sm text-zinc-500">
        Chat with the agent as a customer would (text mode, read-only). Each reply shows how it
        was routed and whether it was grounded in your knowledge.
      </p>

      <div className="mt-6 flex-1 space-y-4">
        {messages.map((m, i) => (
          <div key={i} className={m.role === "customer" ? "text-right" : ""}>
            <div
              className={
                "inline-block max-w-[85%] rounded-2xl px-4 py-2 text-sm " +
                (m.role === "customer"
                  ? "bg-ordy-accent text-white"
                  : "bg-zinc-100 dark:bg-zinc-800")
              }
            >
              {m.text}
            </div>
            {m.trace && (
              <div className="mt-1 flex flex-wrap gap-2 text-xs text-zinc-500">
                <span className="rounded-full border border-zinc-200 px-2 py-0.5 dark:border-zinc-700">
                  {m.trace.route}
                </span>
                {m.trace.grounding && (
                  <span className={m.trace.grounding.grounded ? "text-green-600" : "text-amber-600"}>
                    {m.trace.grounding.grounded ? "grounded" : "ungrounded"}
                  </span>
                )}
                {m.trace.retrieved?.[0]?.source && (
                  <a href={m.trace.retrieved[0].source} target="_blank" rel="noreferrer" className="text-ordy-accent hover:underline">
                    source ↗
                  </a>
                )}
              </div>
            )}
          </div>
        ))}
        {messages.length === 0 && (
          <p className="text-zinc-400">
            Try: &ldquo;how much is the pepperoni pizza?&rdquo; · &ldquo;vegetarian options?&rdquo; · &ldquo;what are your hours?&rdquo;
          </p>
        )}
        <div ref={bottom} />
      </div>

      {error && <p className="text-sm text-red-500">{error}</p>}

      <form onSubmit={send} className="sticky bottom-4 mt-4 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type a customer message…"
          className="flex-1 rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-900"
        />
        <button type="submit" disabled={busy || !rid} className="rounded-lg bg-ordy-accent px-4 py-2 font-medium text-white hover:opacity-90 disabled:opacity-50">
          {busy ? "…" : "Send"}
        </button>
      </form>
    </main>
  );
}
