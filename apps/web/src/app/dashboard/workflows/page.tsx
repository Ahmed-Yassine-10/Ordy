"use client";

import { useCallback, useEffect, useState } from "react";
import { api, loadToken, type Restaurant, type Workflow } from "@/lib/api";

const STATUS_STYLES: Record<string, string> = {
  draft: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300",
  verifying: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  verified: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300",
  active: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300",
  degraded: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  disabled: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
};

export default function WorkflowsPage() {
  const [restaurants, setRestaurants] = useState<Restaurant[]>([]);
  const [rid, setRid] = useState("");
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!rid) return;
    try {
      setWorkflows(await api.listWorkflows(rid));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load workflows");
    }
  }, [rid]);

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
    refresh();
  }, [refresh]);

  async function act(wf: Workflow, action: "verify" | "approve" | "disable") {
    setBusy(wf.id);
    setError(null);
    try {
      if (action === "verify") await api.verifyWorkflow(rid, wf.id);
      if (action === "approve") await api.approveWorkflow(rid, wf.id);
      if (action === "disable") await api.disableWorkflow(rid, wf.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Website automation</h1>
        <select
          value={rid}
          onChange={(e) => setRid(e.target.value)}
          className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        >
          {restaurants.map((r) => (
            <option key={r.id} value={r.id}>{r.name}</option>
          ))}
        </select>
      </div>
      <p className="mt-1 text-sm text-zinc-500">
        For restaurants without an API, Ordy orders through your website. Workflows are generated
        once, verified by a dry-run that never submits, and approved by you before they go live.
        Ordy never types card details.
      </p>

      {error && <p className="mt-4 text-red-500">{error}</p>}

      <ul className="mt-6 divide-y divide-zinc-200 dark:divide-zinc-800">
        {workflows.map((wf) => (
          <li key={wf.id} className="flex items-start gap-4 py-4">
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium">{wf.action_key}</span>
                <span className={`rounded-full px-2 py-0.5 text-xs ${STATUS_STYLES[wf.status] ?? ""}`}>
                  {wf.status}
                </span>
              </div>
              <p className="mt-1 text-xs text-zinc-500">
                {wf.target_domain} · {wf.step_count} steps · v{wf.version}
                {wf.failure_count > 0 && ` · ${wf.failure_count} recent failures`}
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => act(wf, "verify")}
                disabled={busy === wf.id}
                className="rounded-lg border border-zinc-300 px-3 py-1.5 text-xs font-medium disabled:opacity-50 dark:border-zinc-700"
              >
                Dry run
              </button>
              {wf.status === "verified" && (
                <button
                  onClick={() => act(wf, "approve")}
                  disabled={busy === wf.id}
                  className="rounded-lg bg-ordy-accent px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
                >
                  Approve
                </button>
              )}
              {["active", "degraded"].includes(wf.status) && (
                <button
                  onClick={() => act(wf, "disable")}
                  disabled={busy === wf.id}
                  className="rounded-lg border border-red-300 px-3 py-1.5 text-xs font-medium text-red-600 disabled:opacity-50 dark:border-red-800"
                >
                  Disable
                </button>
              )}
            </div>
          </li>
        ))}
        {workflows.length === 0 && !error && (
          <p className="py-8 text-center text-zinc-400">
            No workflows yet — they are generated during onboarding for sites without an API.
          </p>
        )}
      </ul>
    </main>
  );
}
