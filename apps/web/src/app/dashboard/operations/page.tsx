"use client";

import { useCallback, useEffect, useState } from "react";
import { api, loadToken, type OrderRow, type Restaurant } from "@/lib/api";

const STATUS_STYLES: Record<string, string> = {
  confirmed: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  preparing: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  ready: "bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300",
  out_for_delivery: "bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300",
  completed: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300",
  cancelled: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
};

function money(minor: number, currency: string): string {
  const exp = currency === "TND" ? 3 : 2;
  return `${(minor / 10 ** exp).toFixed(exp)} ${currency}`;
}

export default function OperationsPage() {
  const [restaurants, setRestaurants] = useState<Restaurant[]>([]);
  const [rid, setRid] = useState("");
  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!rid) return;
    try {
      setOrders(await api.listOrders(rid));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load orders");
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

  // Poll the feed; the WebSocket live feed replaces this with the events pipeline.
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 10_000);
    return () => clearInterval(timer);
  }, [refresh]);

  async function advance(order: OrderRow, status: string) {
    setBusy(order.id);
    setError(null);
    try {
      const updated = await api.changeOrderStatus(rid, order.id, status);
      setOrders((all) => all.map((o) => (o.id === updated.id ? updated : o)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Status change failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <main className="mx-auto max-w-4xl px-6 py-12">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Live orders</h1>
        <select value={rid} onChange={(e) => setRid(e.target.value)} className="rounded-lg border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-700 dark:bg-zinc-900">
          {restaurants.map((r) => (
            <option key={r.id} value={r.id}>{r.name}</option>
          ))}
        </select>
      </div>
      <p className="mt-1 text-sm text-zinc-500">
        Orders the agent placed land here. Status changes follow the same state machine the
        agent does — only valid next steps are offered.
      </p>

      {error && <p className="mt-4 text-red-500">{error}</p>}

      <ul className="mt-6 flex flex-col gap-3">
        {orders.map((order) => (
          <li key={order.id} className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLES[order.status] ?? ""}`}>
                {order.status.replace(/_/g, " ")}
              </span>
              <span className="text-xs text-zinc-500">
                {order.type} · {order.channel} · via {order.executed_via}
              </span>
              <span className="ml-auto font-semibold">{money(order.total_minor, order.currency)}</span>
            </div>

            <ul className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
              {order.items.map((item, i) => (
                <li key={i}>{item.quantity}× {item.name}</li>
              ))}
            </ul>

            {order.next_states.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {order.next_states.map((next) => (
                  <button
                    key={next}
                    onClick={() => advance(order, next)}
                    disabled={busy === order.id}
                    className="rounded-lg border border-zinc-300 px-3 py-1 text-xs font-medium hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:hover:bg-zinc-900"
                  >
                    Mark {next.replace(/_/g, " ")}
                  </button>
                ))}
              </div>
            )}
          </li>
        ))}
        {orders.length === 0 && !error && (
          <p className="py-8 text-center text-zinc-400">
            No orders yet — place one from the <a href="/dashboard/sandbox" className="text-ordy-accent hover:underline">sandbox</a>.
          </p>
        )}
      </ul>
    </main>
  );
}
