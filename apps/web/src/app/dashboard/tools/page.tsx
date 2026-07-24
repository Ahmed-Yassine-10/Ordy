"use client";

import { useEffect, useState } from "react";
import { api, loadToken, type Restaurant, type Tool } from "@/lib/api";

const RISK_STYLES: Record<string, string> = {
  read: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300",
  write: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  financial: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
};

export default function ToolsPage() {
  const [restaurants, setRestaurants] = useState<Restaurant[]>([]);
  const [rid, setRid] = useState("");
  const [tools, setTools] = useState<Tool[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

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

  useEffect(() => {
    if (rid) api.listTools(rid).then(setTools).catch((e) => setError(String(e)));
  }, [rid]);

  async function toggle(tool: Tool) {
    setBusy(tool.key);
    setError(null);
    try {
      const updated = await api.updateTool(rid, tool.key, { enabled: !tool.enabled });
      setTools((all) => all.map((t) => (t.key === updated.key ? updated : t)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Agent tools</h1>
        <select value={rid} onChange={(e) => setRid(e.target.value)} className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900">
          {restaurants.map((r) => (
            <option key={r.id} value={r.id}>{r.name}</option>
          ))}
        </select>
      </div>
      <p className="mt-1 text-sm text-zinc-500">
        Nothing the agent does reaches your systems unless you enable it here. Every enabled
        action still passes validation, caps, and a customer confirmation before it runs.
      </p>

      {error && <p className="mt-4 text-red-500">{error}</p>}

      <ul className="mt-6 divide-y divide-zinc-200 dark:divide-zinc-800">
        {tools.map((tool) => (
          <li key={tool.key} className="flex items-start gap-4 py-4">
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium">{tool.title}</span>
                <span className={`rounded-full px-2 py-0.5 text-xs ${RISK_STYLES[tool.risk] ?? ""}`}>
                  {tool.risk}
                </span>
                {tool.requires_confirmation && (
                  <span className="text-xs text-zinc-500">needs confirmation</span>
                )}
              </div>
              <p className="mt-1 text-sm text-zinc-500">{tool.description}</p>
              {tool.enabled && (
                <p className="mt-1 text-xs text-zinc-400">
                  via {tool.adapter}
                  {Object.keys(tool.caps).length > 0 &&
                    ` · caps: ${Object.entries(tool.caps).map(([k, v]) => `${k}=${v}`).join(", ")}`}
                </p>
              )}
            </div>
            <button
              onClick={() => toggle(tool)}
              disabled={busy === tool.key}
              className={
                "rounded-lg px-3 py-1.5 text-sm font-medium disabled:opacity-50 " +
                (tool.enabled
                  ? "bg-ordy-accent text-white"
                  : "border border-zinc-300 dark:border-zinc-700")
              }
            >
              {tool.enabled ? "Enabled" : "Enable"}
            </button>
          </li>
        ))}
        {tools.length === 0 && !error && <p className="py-6 text-zinc-400">Loading tools…</p>}
      </ul>
    </main>
  );
}
