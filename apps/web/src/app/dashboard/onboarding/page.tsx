"use client";

import { useEffect, useState } from "react";
import { api, loadToken, type DraftItem, type ReviewData, type Restaurant } from "@/lib/api";

function formatMinor(minor: number | null, currency: string): string {
  if (minor === null) return "—";
  const exp = currency === "TND" ? 3 : 2;
  return `${(minor / 10 ** exp).toFixed(exp)} ${currency}`;
}

export default function OnboardingPage() {
  const [restaurants, setRestaurants] = useState<Restaurant[]>([]);
  const [rid, setRid] = useState("");
  const [kind, setKind] = useState("website");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [review, setReview] = useState<ReviewData | null>(null);
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [published, setPublished] = useState<string | null>(null);

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

  async function runIngestion(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setReview(null);
    setPublished(null);
    try {
      const source = await api.createSource(rid, kind, url);
      const run = await api.triggerRun(rid, source.id); // inline in dev → awaiting_review
      const data = await api.getReview(rid, run.id);
      setReview(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ingestion failed");
    } finally {
      setBusy(false);
    }
  }

  function toggle(name: string) {
    setExcluded((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  }

  async function approve() {
    if (!review) return;
    setBusy(true);
    try {
      const res = await api.submitReview(rid, review.run.id, [...excluded]);
      setPublished(`Published ${res.published_products} products in ${res.published_categories} categories.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Publish failed");
    } finally {
      setBusy(false);
    }
  }

  const items: DraftItem[] = review?.menu_draft?.items ?? [];

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-2xl font-bold">Onboard a restaurant</h1>
      <p className="mt-1 text-sm text-zinc-500">
        Point Ordy at a website or an API doc. It extracts a menu draft and a capability map for you
        to review before anything goes live.
      </p>

      <form onSubmit={runIngestion} className="mt-6 flex flex-col gap-3 rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
        <select value={rid} onChange={(e) => setRid(e.target.value)} className="rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-900">
          {restaurants.map((r) => (
            <option key={r.id} value={r.id}>{r.name}</option>
          ))}
        </select>
        <div className="flex gap-3">
          <select value={kind} onChange={(e) => setKind(e.target.value)} className="rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-900">
            <option value="website">Website</option>
            <option value="api_doc">API doc (OpenAPI)</option>
          </select>
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" required className="flex-1 rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-900" />
        </div>
        <button type="submit" disabled={busy || !rid} className="self-start rounded-lg bg-ordy-accent px-4 py-2 font-medium text-white hover:opacity-90 disabled:opacity-50">
          {busy ? "Working…" : "Ingest"}
        </button>
      </form>

      {error && <p className="mt-4 text-red-500">{error}</p>}

      {review && (
        <section className="mt-8">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Review — {items.length} items extracted</h2>
            <button onClick={approve} disabled={busy} className="rounded-lg bg-ordy-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50">
              Approve &amp; publish
            </button>
          </div>
          {review.warnings.length > 0 && (
            <ul className="mt-2 text-sm text-amber-600">{review.warnings.map((w) => <li key={w}>⚠ {w}</li>)}</ul>
          )}
          {published && <p className="mt-3 rounded-lg bg-green-50 p-3 text-green-700 dark:bg-green-950">{published}</p>}

          <ul className="mt-4 divide-y divide-zinc-200 dark:divide-zinc-800">
            {items.map((it) => (
              <li key={it.name} className="flex items-center gap-3 py-2">
                <input type="checkbox" checked={!excluded.has(it.name)} onChange={() => toggle(it.name)} />
                <div className="flex-1">
                  <span className="font-medium">{it.name}</span>
                  {it.category && <span className="ml-2 text-xs text-zinc-500">{it.category}</span>}
                  {it.needs_review && <span className="ml-2 text-xs text-amber-600">needs review</span>}
                </div>
                <div className="text-sm text-zinc-500">
                  {it.variants.length > 0
                    ? it.variants.map((v) => `${v.name} ${formatMinor(v.price_minor, it.currency)}`).join(" · ")
                    : formatMinor(it.price_minor, it.currency)}
                </div>
              </li>
            ))}
          </ul>

          {review.capability_map && (
            <div className="mt-6">
              <h3 className="text-sm font-semibold text-zinc-500">Capability map</h3>
              <div className="mt-2 flex flex-wrap gap-2">
                {review.capability_map.capabilities.map((c) => (
                  <span key={c.action} className="rounded-full border border-zinc-200 px-2.5 py-1 text-xs dark:border-zinc-700">
                    {c.action} → {c.adapter}
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>
      )}
    </main>
  );
}
