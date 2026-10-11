"use client";

import { useEffect, useState, useCallback } from "react";
import { api, type PurchasePlan, type PurchaseLinkInfo } from "@/lib/api";

export default function PurchasePlanView({ eventId }: { eventId: string }) {
  const [plan, setPlan] = useState<PurchasePlan | null>(null);
  const [retailer, setRetailer] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (key?: string) => {
      setLoading(true);
      try {
        const res = await api.getPurchasePlan(eventId, key);
        setPlan(res);
        setRetailer(res.retailer.key);
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not load the purchase plan");
      } finally {
        setLoading(false);
      }
    },
    [eventId]
  );

  useEffect(() => {
    load();
  }, [load]);

  if (loading && !plan) {
    return <div className="py-10 text-stone-400 animate-pulse">Building purchase plan…</div>;
  }
  if (error) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
        {error}
        <div className="mt-1 text-xs text-amber-800">
          If nothing has been costed yet, press Calculate first.
        </div>
      </div>
    );
  }
  if (!plan) return null;

  return (
    <div className="space-y-6">
      {/* Store picker + totals */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <label className="block text-xs font-medium text-stone-600 mb-1.5">
            Order from
          </label>
          <div className="flex gap-1.5">
            {plan.available_retailers.map((r) => (
              <button
                key={r.key}
                onClick={() => load(r.key)}
                className={`rounded-md px-3 py-1.5 text-sm border transition ${
                  retailer === r.key
                    ? "border-amber-800 bg-amber-900 text-white"
                    : "border-stone-300 bg-white text-stone-700 hover:bg-stone-50"
                }`}
              >
                {r.name}
                {!r.search_linkable && (
                  <span className="ml-1.5 text-[10px] opacity-70">no search</span>
                )}
              </button>
            ))}
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs uppercase tracking-wide text-stone-500">
            Ready to order
          </div>
          <div className="text-2xl font-semibold tabular-nums text-stone-900">
            ₪{plan.orderable_total.toLocaleString()}
          </div>
          <div className="text-xs text-stone-500">
            {plan.orderable_item_count} item
            {plan.orderable_item_count === 1 ? "" : "s"}
          </div>
        </div>
      </div>

      {!plan.retailer.search_linkable && (
        <div className="rounded-lg border border-stone-200 bg-stone-50 px-4 py-3 text-xs text-stone-600">
          <strong className="text-stone-800">{plan.retailer.name}</strong> has no
          search you can link to, so each item opens the shop&apos;s home page and
          shows you the term to search for. The other two shops link straight to
          results.
        </div>
      )}

      {/* Store groups */}
      {plan.groups.map((g) => (
        <section key={g.group_key} className="rounded-lg border border-stone-200 overflow-hidden">
          <header className="flex items-center justify-between bg-stone-50 px-4 py-3 border-b border-stone-200">
            <div>
              <h3 className="font-semibold text-stone-900">{g.store_name}</h3>
              <p className="text-xs text-stone-500">
                {g.item_count} item{g.item_count === 1 ? "" : "s"} in this order
              </p>
            </div>
            <div className="text-right">
              <div className="text-lg font-semibold tabular-nums text-stone-900">
                ₪{g.subtotal.toLocaleString()}
              </div>
              {g.store_website && (
                <a
                  href={g.store_website}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-amber-800 hover:underline"
                >
                  open shop ↗
                </a>
              )}
            </div>
          </header>

          <ul className="divide-y divide-stone-100">
            {g.items.map((item, idx) => (
              <li
                key={`${g.group_key}-${idx}`}
                className="flex flex-wrap items-center gap-3 px-4 py-3 hover:bg-stone-50"
              >
                <div className="w-24 shrink-0">
                  <span className="inline-block rounded bg-amber-100 px-2 py-1 text-sm font-semibold text-amber-900 tabular-nums">
                    {item.order_line}
                  </span>
                </div>
                <div className="flex-1 min-w-[12rem]">
                  <div className="font-medium text-stone-900">{item.ingredient_name}</div>
                  {item.product_name &&
                    item.product_name !== item.ingredient_name && (
                      <div className="text-xs text-stone-500" dir="auto">
                        buying: {item.product_name}
                      </div>
                    )}
                </div>
                <div className="w-24 text-right tabular-nums text-stone-700">
                  {item.total_price != null ? `₪${item.total_price}` : "—"}
                </div>
                <BuyButton link={item.purchase_link} />
              </li>
            ))}
          </ul>
        </section>
      ))}

      {/* Blocked */}
      {plan.blocked_count > 0 && (
        <section className="rounded-lg border border-amber-200 bg-amber-50/50 overflow-hidden">
          <header className="px-4 py-3 border-b border-amber-200 bg-amber-50">
            <h3 className="font-semibold text-amber-900">
              Not ready to order ({plan.blocked_count})
            </h3>
            <p className="text-xs text-amber-800 mt-0.5">
              These are excluded from the total above rather than guessed at.
            </p>
          </header>
          <ul className="divide-y divide-amber-100">
            {plan.blocked.map((b, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-x-3 px-4 py-2.5">
                <span className="font-medium text-stone-800">{b.ingredient_name}</span>
                {b.required_amount != null && (
                  <span className="text-xs text-stone-500 tabular-nums">
                    needs {Math.round(b.required_amount)}
                    {b.unit}
                  </span>
                )}
                <span className="ml-auto text-xs text-amber-900">{b.reason}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function BuyButton({ link }: { link: PurchaseLinkInfo }) {
  if (!link.url) {
    return <span className="w-28 text-right text-xs text-stone-400">no link</span>;
  }

  const label =
    link.kind === "DIRECT"
      ? "Buy"
      : link.kind === "SEARCH"
        ? "Find"
        : "Open shop";

  return (
    <a
      href={link.url}
      target="_blank"
      rel="noopener noreferrer"
      title={link.note ?? undefined}
      className={`w-28 text-center rounded-md px-3 py-1.5 text-sm font-medium transition ${
        link.kind === "DIRECT"
          ? "bg-amber-900 text-white hover:bg-amber-800"
          : "border border-amber-800 text-amber-900 hover:bg-amber-50"
      }`}
    >
      {label} ↗
    </a>
  );
}
