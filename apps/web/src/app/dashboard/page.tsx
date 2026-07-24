"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError, loadToken, type Restaurant } from "@/lib/api";

export default function DashboardPage() {
  const router = useRouter();
  const [restaurants, setRestaurants] = useState<Restaurant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loadToken()) {
      router.push("/login");
      return;
    }
    api
      .myRestaurants()
      .then(setRestaurants)
      .catch((err: ApiError) => {
        if (err.status === 401) router.push("/login");
        else setError(err.message);
      })
      .finally(() => setLoading(false));
  }, [router]);

  async function createDemo() {
    const name = prompt("Restaurant name?");
    if (!name) return;
    const created = await api.createRestaurant(name);
    setRestaurants((prev) => [created, ...prev]);
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Your restaurants</h1>
        <div className="flex gap-2">
          <a
            href="/dashboard/onboarding"
            className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-900"
          >
            Onboard
          </a>
          <a
            href="/dashboard/knowledge"
            className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-900"
          >
            Knowledge
          </a>
          <a
            href="/dashboard/sandbox"
            className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-900"
          >
            Sandbox
          </a>
          <a
            href="/dashboard/tools"
            className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-900"
          >
            Tools
          </a>
          <a
            href="/dashboard/operations"
            className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-900"
          >
            Orders
          </a>
          <button
            onClick={createDemo}
            className="rounded-lg bg-ordy-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90"
          >
            + New restaurant
          </button>
        </div>
      </div>

      {loading && <p className="mt-8 text-zinc-500">Loading…</p>}
      {error && <p className="mt-8 text-red-500">{error}</p>}

      <ul className="mt-8 flex flex-col gap-3">
        {restaurants.map((r) => (
          <li
            key={r.id}
            className="flex items-center justify-between rounded-xl border border-zinc-200 px-4 py-3 dark:border-zinc-800"
          >
            <div>
              <p className="font-medium">{r.name}</p>
              <p className="text-xs text-zinc-500">
                {r.slug} · {r.currency} · {r.status}
              </p>
            </div>
            <span className="rounded-full bg-zinc-100 px-2.5 py-1 text-xs font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
              {r.role}
            </span>
          </li>
        ))}
        {!loading && restaurants.length === 0 && (
          <p className="text-zinc-500">No restaurants yet — create your first one.</p>
        )}
      </ul>
    </main>
  );
}
