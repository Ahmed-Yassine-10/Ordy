"use client";

import { useEffect, useState } from "react";
import { api, loadToken, type Restaurant, type SearchHit } from "@/lib/api";

export default function KnowledgePage() {
  const [restaurants, setRestaurants] = useState<Restaurant[]>([]);
  const [rid, setRid] = useState("");
  const [query, setQuery] = useState("how much is the pepperoni pizza?");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

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

  async function search(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setHits(await api.searchKnowledge(rid, query));
      setSearched(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-2xl font-bold">Knowledge retrieval</h1>
      <p className="mt-1 text-sm text-zinc-500">
        Inspect what the agent would retrieve for a question — hybrid search (vector + full-text)
        over approved chunks, with the source each answer came from.
      </p>

      <form onSubmit={search} className="mt-6 flex flex-col gap-3">
        <select value={rid} onChange={(e) => setRid(e.target.value)} className="rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-900">
          {restaurants.map((r) => (
            <option key={r.id} value={r.id}>{r.name}</option>
          ))}
        </select>
        <div className="flex gap-3">
          <input value={query} onChange={(e) => setQuery(e.target.value)} className="flex-1 rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-700 dark:bg-zinc-900" placeholder="Ask a menu / hours / policy question…" />
          <button type="submit" disabled={busy || !rid} className="rounded-lg bg-ordy-accent px-4 py-2 font-medium text-white hover:opacity-90 disabled:opacity-50">
            {busy ? "…" : "Search"}
          </button>
        </div>
      </form>

      {error && <p className="mt-4 text-red-500">{error}</p>}

      <ul className="mt-8 flex flex-col gap-3">
        {hits.map((h, i) => (
          <li key={h.chunk_id} className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
            <div className="flex items-center justify-between text-xs text-zinc-500">
              <span>#{i + 1} · score {h.score.toFixed(4)}{h.language ? ` · ${h.language}` : ""}</span>
              {h.provenance?.source_url && (
                <a href={h.provenance.source_url} className="text-ordy-accent hover:underline" target="_blank" rel="noreferrer">
                  {h.provenance.doc_type ?? "source"} ↗
                </a>
              )}
            </div>
            <p className="mt-2 whitespace-pre-wrap text-sm">{h.content}</p>
          </li>
        ))}
        {searched && hits.length === 0 && (
          <p className="text-zinc-500">No chunks matched — has a menu been ingested &amp; approved for this restaurant?</p>
        )}
      </ul>
    </main>
  );
}
