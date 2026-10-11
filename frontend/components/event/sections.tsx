"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  GlassWater, Package, CircleDollarSign, Store, ShoppingCart, Calculator,
  AlertTriangle, ExternalLink, Search, Home, CheckCircle2, Wallet, Users,
} from "lucide-react";
import {
  api, type CocktailDetail, type CostSummary, type Event,
  type PurchasePlan, type ShoppingList,
} from "@/lib/api";
import {
  Card, MetricCard, SectionTitle, EmptyState, Note, Button,
  StatusBadge, money, money2, cx, Skeleton, amount,
} from "@/components/ui";

// ── Overview ────────────────────────────────────────────────────────────────

export function OverviewSection({
  event, cost, plan, shopping, onGoTo,
}: {
  event: Event;
  cost: CostSummary | null;
  plan: PurchasePlan | null;
  shopping: ShoppingList | null;
  onGoTo: (tab: string) => void;
}) {
  const bottles = shopping?.items.reduce((n, i) => n + (i.packages_required ?? 0), 0) ?? 0;
  const remaining =
    cost?.budget != null && cost?.total_cost != null ? cost.budget - cost.total_cost : null;
  const blocked = plan?.blocked_count ?? 0;
  const drinks = shopping ? Math.round(
    event.guest_count * Number(event.expected_drinks_per_guest)) : null;
  const priced = shopping
    ? shopping.items.filter((i) => i.total_price != null).length : 0;
  const coverage = shopping && shopping.items.length
    ? Math.round((priced / shopping.items.length) * 100) : null;

  return (
    <div className="flex flex-col gap-6">
      {/* One line that answers "can I act on this yet?" before any number does.
          Ready and blocked are different states with different next steps, and
          burying that distinction inside a warning below the metrics made
          people read six figures before learning the total was incomplete. */}
      <ReadinessBanner
        blocked={blocked}
        partial={!!cost?.is_partial}
        hasMenu={event.menu.length > 0}
        costed={cost?.total_cost != null}
        onGoTo={onGoTo}
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <MetricCard
          label="Menu" icon={GlassWater}
          value={event.menu.length}
          hint={
            drinks != null
              ? `${drinks.toLocaleString()} drinks planned`
              : (event.menu.length === 1 ? "cocktail selected" : "cocktails selected")
          }
          onClick={() => onGoTo("menu")}
        />
        <MetricCard
          label="To buy" icon={Package}
          value={bottles || "—"}
          hint={shopping ? `${shopping.items.length} line items` : "not calculated"}
          onClick={() => onGoTo("quantities")}
        />
        <MetricCard
          label="Estimated cost" icon={CircleDollarSign}
          value={money(cost?.total_cost)}
          hint={cost?.cost_per_guest != null ? `${money2(cost.cost_per_guest)} per guest` : undefined}
          tone={cost?.is_partial ? "warn" : "neutral"}
          onClick={() => onGoTo("costs")}
        />
        {/* An event without a budget is fully costable; it simply gets no
            over/under verdict. Showing "—" against a budget nobody set would
            imply a failure, so the card becomes a coverage reading instead —
            which is the thing that IS unknown when no budget exists. */}
        {event.budget != null ? (
          <MetricCard
            label="Budget left" icon={Wallet}
            value={remaining == null ? "—" : money(remaining)}
            hint={cost?.budget_status?.replace(/_/g, " ").toLowerCase()}
            tone={remaining == null ? "neutral" : remaining < 0 ? "bad" : "good"}
            onClick={() => onGoTo("costs")}
          />
        ) : (
          <MetricCard
            label="Priced" icon={CheckCircle2}
            value={coverage != null ? `${coverage}%` : "—"}
            hint={blocked > 0 ? `${blocked} without a price` : "no budget set"}
            tone={blocked > 0 ? "warn" : "good"}
            onClick={() => onGoTo("quantities")}
          />
        )}
      </div>

      {/* The Assumptions card lived here until Aug 2026. Topaz: the figures in it
          are not the ones she reasons with, and it took half the width from the
          cost breakdown, which is. The same numbers still appear under the event
          title, where they read as context rather than as a panel. */}
      <div className="grid gap-3 items-start">
        <Card className="p-4">
          <SectionTitle hint="Where the money goes">Cost by category</SectionTitle>
          {cost && Object.keys(cost.cost_by_category).length > 0 ? (
            <CategoryBars data={cost.cost_by_category} total={cost.total_cost} />
          ) : (
            <p className="text-[13px] text-ink-3 py-3">Nothing costed yet.</p>
          )}
        </Card>
      </div>

      {event.ai_request && (
        <Card className="p-4">
          <SectionTitle hint="What you asked for">Original brief</SectionTitle>
          <p className="text-[13.5px] text-ink-2 leading-relaxed" dir="auto">
            {event.ai_request}
          </p>
        </Card>
      )}
    </div>
  );
}


/**
 * The state of the event in one sentence, with the next step attached.
 *
 * Four states, and they are genuinely different actions: nothing to cost yet,
 * something is blocking the total, the total is partial, or it is ready. A
 * single "warning" treatment for all of them made the most important one — a
 * cost that is quietly incomplete — look like the least important.
 */
function ReadinessBanner({
  blocked, partial, hasMenu, costed, onGoTo,
}: {
  blocked: number;
  partial: boolean;
  hasMenu: boolean;
  costed: boolean;
  onGoTo: (tab: string) => void;
}) {
  if (!hasMenu) {
    return (
      <Note icon={GlassWater}>
        No cocktails yet. Add them on the{" "}
        <button onClick={() => onGoTo("menu")} className="text-accent hover:underline">
          Menu tab
        </button>, or ask the agent to build one.
      </Note>
    );
  }
  if (blocked > 0) {
    return (
      <Note tone="warn" icon={AlertTriangle}>
        <strong className="font-medium">{blocked}</strong>{" "}
        {blocked === 1 ? "ingredient has" : "ingredients have"} no price, so this
        total is incomplete — do not budget from it yet.{" "}
        <button onClick={() => onGoTo("quantities")} className="underline">
          See which
        </button>
      </Note>
    );
  }
  if (partial) {
    return (
      <Note tone="warn" icon={AlertTriangle}>
        Some items have no price, so this total is partial.
      </Note>
    );
  }
  if (!costed) {
    return (
      <Note icon={Calculator}>
        Not costed yet. Press Recalculate, or change the menu and it runs itself.
      </Note>
    );
  }
  return (
    <Note tone="good" icon={CheckCircle2}>
      Fully priced and ready — the prep sheet and shopping list are good to use.
    </Note>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-ink-3">{label}</dt>
      <dd className="text-ink text-right tnum" dir="auto">{value}</dd>
    </>
  );
}

/**
 * Category share as bars rather than a pie: five or six categories with one
 * dominant value read faster on a common baseline, and it needs no legend.
 */
function CategoryBars({ data, total }: { data: Record<string, number>; total: number }) {
  const rows = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(...rows.map((r) => r[1]), 1);
  return (
    <div className="flex flex-col gap-2">
      {rows.map(([cat, amount]) => (
        <div key={cat}>
          <div className="flex justify-between text-[12.5px] mb-1">
            <span className="text-ink-2 capitalize">{cat}</span>
            <span className="text-ink tnum">
              {money(amount)}
              <span className="text-ink-4 ml-1.5">
                {total ? Math.round((amount / total) * 100) : 0}%
              </span>
            </span>
          </div>
          <div className="h-1.5 bg-sunk rounded-full overflow-hidden">
            <div
              className="h-full bg-accent/70 rounded-full transition-[width] duration-500"
              style={{ width: `${(amount / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Menu ────────────────────────────────────────────────────────────────────

export function MenuSection({ event }: { event: Event }) {
  const [details, setDetails] = useState<Record<string, CocktailDetail>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    (async () => {
      const entries = await Promise.all(
        event.menu.map(async (m) => {
          try { return [m.cocktail_id, await api.getCocktail(m.cocktail_id)] as const; }
          catch { return null; }
        })
      );
      if (!alive) return;
      setDetails(Object.fromEntries(entries.filter(Boolean) as [string, CocktailDetail][]));
      setLoading(false);
    })();
    return () => { alive = false; };
  }, [event.menu]);

  if (event.menu.length === 0) {
    return (
      <Card>
        <EmptyState
          icon={GlassWater}
          title="No cocktails on the menu yet."
          body="Ask the agent for a menu, or browse the cocktail library."
          action={<Link href="/cocktails"><Button variant="secondary">Browse cocktails</Button></Link>}
        />
      </Card>
    );
  }

  return (
    <div className="grid md:grid-cols-2 gap-3 items-start">
      {event.menu.map((m) => {
        const d = details[m.cocktail_id];
        return (
          <Card key={m.cocktail_id} className="p-4">
            <div className="flex items-start justify-between gap-3 mb-2">
              <div className="min-w-0">
                <h3 className="text-[14.5px] font-medium text-ink truncate">
                  {m.cocktail_name ?? d?.name ?? "Cocktail"}
                </h3>
                {d && (d.technique || d.glass_type) && (
                  <p
                    className="text-[12px] text-ink-4 mt-0.5 line-clamp-2 leading-snug"
                    dir="auto"
                    title={[d.technique, d.glass_type].filter(Boolean).join(" \u00b7 ")}
                  >
                    {[d.technique, d.glass_type].filter(Boolean).join(" \u00b7 ")}
                  </p>
                )}
              </div>
              <span className="shrink-0 text-[11.5px] font-medium text-accent-hi bg-accent-soft border border-accent-line rounded-md px-2 py-1 tnum">
                {m.expected_servings ?? Math.round(m.allocation_pct * 100) + "%"}
                {m.expected_servings != null && " servings"}
              </span>
            </div>

            {loading && !d ? (
              <div className="flex flex-col gap-1.5 mt-3">
                {[0, 1, 2].map((i) => <Skeleton key={i} className="h-4" />)}
              </div>
            ) : d ? (
              <table className="w-full mt-2">
                <tbody>
                  {d.ingredients.map((ing) => (
                    <tr key={ing.ingredient_id}>
                      <td className="py-[3px] text-[12.5px] text-accent-hi font-medium tnum whitespace-nowrap w-[68px]">
                        {amount(ing.amount, ing.unit)}
                      </td>
                      <td className="py-[3px] text-[13px] text-ink-2">{ing.canonical_name}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-[12.5px] text-ink-4 mt-2">Recipe unavailable.</p>
            )}

            {d?.garnish && (
              <p className="mt-2.5 pt-2.5 border-t border-line text-[12px] text-ink-3" dir="auto">
                Garnish: {d.garnish}
              </p>
            )}
          </Card>
        );
      })}
    </div>
  );
}

// ── Quantities ──────────────────────────────────────────────────────────────

/**
 * The calculated-versus-purchase distinction, made explicit.
 *
 * Every figure here is read from what the engine already produced. "Exact" is
 * the recipe requirement divided by the pack size and is shown only to explain
 * why the purchase count rounds up — it is never used to compute cost.
 */
export function QuantitiesSection({
  shopping, eventId, onCompare,
}: {
  shopping: ShoppingList | null;
  eventId?: string;
  onCompare?: (ingredientId: string) => void;
}) {
  if (!shopping || shopping.items.length === 0) {
    return (
      <Card>
        <EmptyState icon={Calculator} title="Nothing calculated yet."
          body="Run the calculation to see exactly how much of each ingredient the event needs." />
      </Card>
    );
  }

  const rows = [...shopping.items].sort((a, b) => (b.total_price ?? 0) - (a.total_price ?? 0));

  return (
    <div className="flex flex-col gap-3">
      <Note icon={Calculator}>
        <strong className="font-medium">Exact</strong> is what the recipes need.{" "}
        <strong className="font-medium">Buy</strong> is whole packages, always rounded up —
        you cannot buy 13.4 bottles. The difference is the leftover.
      </Note>

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-[13px] min-w-[720px]">
            <thead>
              <tr className="bg-sunk border-b border-line text-ink-3">
                <Th className="text-left">Ingredient</Th>
                <Th className="text-right">Required</Th>
                <Th className="text-right">Pack</Th>
                <Th className="text-right">Exact</Th>
                <Th className="text-right">Buy</Th>
                <Th className="text-right">Leftover</Th>
                <Th className="text-right">Cost</Th>
                <Th className="text-right"><span className="sr-only">Alternatives</span></Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((it, i) => {
                const size = it.package_size ?? null;
                const exact = size && it.required_amount ? it.required_amount / size : null;
                const bought = it.packages_required ?? null;
                const leftover =
                  size && bought != null ? bought * size - it.required_amount : null;
                const ingredientId = it.ingredient_id;
                return (
                  <tr key={i} className="hover:bg-raised">
                    <Td className="text-ink font-medium">
                      <span dir="auto">{it.ingredient_name}</span>
                      {it.status !== "OK" && (
                        <StatusBadge status={it.status} className="ml-2 align-middle" />
                      )}
                      {it.product_name && (
                        <div dir="auto" className="text-[11.5px] font-normal text-ink-4 mt-0.5">
                          {it.product_name}
                        </div>
                      )}
                    </Td>
                    <Td className="text-right tnum text-ink-2">
                      {amount(it.required_amount, it.unit, true)}
                    </Td>
                    <Td className="text-right tnum text-ink-3">
                      {size ? amount(size, it.package_unit) : "\u2014"}
                    </Td>
                    <Td className="text-right tnum text-ink-3">
                      {exact != null ? exact.toFixed(2) : "—"}
                    </Td>
                    <Td className="text-right tnum font-semibold text-accent-hi">
                      {bought ?? "—"}
                    </Td>
                    <Td className="text-right tnum text-ink-4">
                      {leftover != null ? amount(leftover, it.package_unit, true) : "\u2014"}
                    </Td>
                    <Td className="text-right tnum text-ink">
                      {it.total_price != null ? money(it.total_price) : "—"}
                    </Td>

                    <Td className="text-right">
                      {onCompare && ingredientId && (
                        <button
                          type="button"
                          onClick={() => onCompare(ingredientId)}
                          className="text-[12px] font-medium text-accent hover:underline whitespace-nowrap"
                        >
                          {it.total_price == null ? "Find price" : "Options"}
                        </button>
                      )}
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function Th({ children, className }: { children?: React.ReactNode; className?: string }) {
  return (
    <th className={cx("px-3 py-2 font-medium text-[11.5px] uppercase tracking-[.05em]", className)}>
      {children}
    </th>
  );
}
function Td({ children, className }: { children?: React.ReactNode; className?: string }) {
  return <td className={cx("px-3 py-2.5", className)}>{children}</td>;
}

// ── Shopping ────────────────────────────────────────────────────────────────

const CATEGORY_ICON: Record<string, typeof Package> = {
  DIRECT: ShoppingCart, SEARCH: Search, HOMEPAGE: Home,
};

export function ShoppingSection({
  plan, onRetailer,
}: { plan: PurchasePlan | null; onRetailer: (key: string) => void }) {
  const [checked, setChecked] = useState<Record<string, boolean>>({});

  if (!plan) {
    return (
      <Card>
        <EmptyState icon={ShoppingCart} title="No shopping list yet."
          body="Run the calculation and the list builds itself from the menu." />
      </Card>
    );
  }

  const makeCount = plan.groups
    .filter((g) => g.store_name.toLowerCase() === "house-made")
    .reduce((total, g) => total + g.item_count, 0);

  const verifyCount = plan.groups
    .filter((g) => g.store_name.toLowerCase().includes("historical"))
    .reduce((total, g) => total + g.item_count, 0);

  const buyCount = Math.max(
    0,
    plan.orderable_item_count - makeCount - verifyCount
  );

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1.5">
          {plan.available_retailers.map((r) => (
            <button
              key={r.key}
              onClick={() => onRetailer(r.key)}
              className={cx(
                "h-8 px-3 rounded-lg border text-[13px] transition-colors inline-flex items-center gap-1.5",
                plan.retailer.key === r.key
                  ? "bg-ink text-white border-ink"
                  : "bg-surface text-ink-2 border-line hover:border-line-2"
              )}
            >
              {r.name}
              {!r.search_linkable && (
                <span className="text-[10px] opacity-60">no search</span>
              )}
            </button>
          ))}
        </div>
        <div className="text-right">
          <div className="text-[18px] font-semibold tnum text-ink">
            {money(plan.orderable_total)}
          </div>
          <div className="text-[11.5px] text-ink-4">
            {buyCount} to buy · {makeCount} make · {verifyCount} price to verify
          </div>
        </div>
      </div>

      {!plan.retailer.search_linkable && (
        <Note>
          <strong className="font-medium">{plan.retailer.name}</strong> has no search that can be
          linked to, so items open the shop&apos;s home page with the term to search for.
        </Note>
      )}

      {plan.groups.map((g) => (
        <Card key={g.group_key} className="overflow-hidden">
          <header className="flex items-center justify-between gap-3 px-4 py-3 bg-sunk border-b border-line">
            <div className="flex items-center gap-2 min-w-0">
              <Store size={15} strokeWidth={1.75} className="text-ink-4 shrink-0" />
              <h3 className="text-[13.5px] font-medium text-ink truncate">{g.store_name}</h3>
              <span className="text-[12px] text-ink-4">
                {g.item_count} item{g.item_count === 1 ? "" : "s"}
              </span>
            </div>
            <span className="text-[14px] font-semibold tnum">{money(g.subtotal)}</span>
          </header>

          <ul className="divide-y divide-line">
            {g.items.map((it, i) => {
              const key = `${g.group_key}-${i}`;
              const Icon = CATEGORY_ICON[it.purchase_link.kind] ?? ShoppingCart;
              const on = checked[key];
              return (
                <li key={key} className={cx("flex items-center gap-3 px-4 py-2.5", on && "opacity-50")}>
                  <input
                    type="checkbox"
                    checked={!!on}
                    onChange={(e) => setChecked((c) => ({ ...c, [key]: e.target.checked }))}
                    aria-label={`Mark ${it.ingredient_name} as bought`}
                    className="w-4 h-4 rounded border-line-2 accent-[var(--color-accent)] shrink-0"
                  />
                  <span className="w-[92px] shrink-0 text-[12.5px] font-medium text-accent-hi bg-accent-soft border border-accent-line rounded-md px-2 py-1 text-center tnum">
                    {it.order_line}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className={cx("text-[13.5px] text-ink truncate", on && "line-through")}>
                      {it.ingredient_name}
                    </div>
                    {it.product_name && it.product_name !== it.ingredient_name && (
                      <div className="text-[12px] text-ink-4 truncate" dir="auto">
                        {it.product_name}
                      </div>
                    )}
                  </div>
                  <span className="text-[13px] tnum text-ink-2 shrink-0 w-[68px] text-right">
                    {money(it.total_price)}
                  </span>
                  {g.store_name.toLowerCase() === "house-made" ? (
                    <span className="shrink-0 inline-flex items-center h-7 px-2.5 rounded-lg border border-line text-[12.5px] font-medium text-ink-3">
                      Make in-house
                    </span>
                  ) : it.purchase_link.url ? (
                    <a
                      href={it.purchase_link.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={it.purchase_link.note ?? undefined}
                      className={cx(
                        "shrink-0 inline-flex items-center gap-1 h-7 px-2.5 rounded-lg text-[12.5px] font-medium transition-colors",
                        it.purchase_link.kind === "DIRECT"
                          ? "bg-accent text-white hover:bg-accent-hi"
                          : "border border-line-2 text-ink-2 hover:bg-sunk"
                      )}
                    >
                      <Icon size={12} strokeWidth={2} />
                      {it.purchase_link.kind === "DIRECT" ? "Buy" : it.purchase_link.kind === "SEARCH" ? "Find" : "Shop"}
                      <ExternalLink size={10} strokeWidth={2} className="opacity-60" />
                    </a>
                  ) : (
                    <span className="shrink-0 w-[72px] text-[12px] text-ink-4 text-right">no link</span>
                  )}
                </li>
              );
            })}
          </ul>
        </Card>
      ))}

      {plan.blocked.length > 0 && (
        <Card className="border-warn/30 overflow-hidden">
          <header className="px-4 py-3 bg-warn-soft border-b border-warn/25">
            <h3 className="text-[13.5px] font-medium text-warn">
              Not ready to order ({plan.blocked.length})
            </h3>
            <p className="text-[12.5px] text-warn/85 mt-0.5">
              Excluded from the total rather than guessed at. Fix on the{" "}
              <Link href="/mappings" className="underline underline-offset-2">Mappings</Link> page.
            </p>
          </header>
          <ul className="divide-y divide-line">
            {plan.blocked.map((b, i) => (
              <li key={i} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-2.5">
                <span className="text-[13.5px] font-medium text-ink">{b.ingredient_name}</span>
                {b.required_amount != null && (
                  <span className="text-[12px] text-ink-4 tnum">
                    needs {amount(b.required_amount, b.unit, true)}
                  </span>
                )}
                <span className="ml-auto text-[12.5px] text-ink-3">{b.reason}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

// ── Suppliers ───────────────────────────────────────────────────────────────

export function SuppliersSection({ plan }: { plan: PurchasePlan | null }) {
  if (!plan || plan.groups.length === 0) {
    return (
      <Card>
        <EmptyState icon={Store} title="No suppliers yet."
          body="Once the event is costed, the shops you'd order from appear here." />
      </Card>
    );
  }

  const cheapest = Math.min(...plan.groups.map((g) => g.subtotal));

  return (
    <div className="flex flex-col gap-3">
      <SectionTitle hint="Totals for this event's orderable items, by shop">
        Where this order would go
      </SectionTitle>
      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
        {plan.groups.map((g) => (
          <Card key={g.group_key} className={cx("p-4", g.subtotal === cheapest && "border-good/35")}>
            <div className="flex items-start justify-between gap-2 mb-3">
              <div className="flex items-center gap-2 min-w-0">
                <Store size={15} strokeWidth={1.75} className="text-ink-4 shrink-0" />
                <h3 className="text-[14px] font-medium truncate">{g.store_name}</h3>
              </div>
              {g.subtotal === cheapest && plan.groups.length > 1 && (
                <span className="shrink-0 inline-flex items-center gap-1 text-[11px] font-medium text-good bg-good-soft border border-good/25 rounded-md px-1.5 py-0.5">
                  <CheckCircle2 size={11} strokeWidth={2} /> Best price
                </span>
              )}
            </div>
            <div className="text-[24px] font-semibold tnum leading-none">{money(g.subtotal)}</div>
            <p className="mt-1.5 text-[12.5px] text-ink-3">
              {g.item_count} item{g.item_count === 1 ? "" : "s"}
            </p>
            {g.store_website && (
              <a
                href={g.store_website}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-3 inline-flex items-center gap-1 text-[12.5px] text-accent-hi hover:underline"
              >
                Open shop <ExternalLink size={11} strokeWidth={2} />
              </a>
            )}
          </Card>
        ))}
      </div>
      <Note>
        Delivery charges aren&apos;t included — the app has no data for them, so it
        doesn&apos;t guess. Add them on the shop&apos;s own checkout.
      </Note>
    </div>
  );
}

// ── Costs ───────────────────────────────────────────────────────────────────

export function CostsSection({
  cost, event,
}: { cost: CostSummary | null; event: Event }) {
  if (!cost) {
    return (
      <Card>
        <EmptyState icon={CircleDollarSign} title="Nothing costed yet."
          body="Run the calculation to see the full financial picture." />
      </Card>
    );
  }

  const budget = cost.budget ?? null;
  const variance = budget != null ? budget - cost.total_cost : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <MetricCard label="Budget" icon={Wallet} value={money(budget)}
          hint={budget == null ? "none set" : undefined} />
        <MetricCard label="Product cost" icon={CircleDollarSign} value={money(cost.total_cost)}
          hint={cost.is_partial ? "partial — some items unpriced" : "all items priced"}
          tone={cost.is_partial ? "warn" : "neutral"} />
        <MetricCard label="Per guest" icon={Users} value={money2(cost.cost_per_guest)}
          hint={`${cost.guest_count} guests`} />
        <MetricCard
          label={variance != null && variance < 0 ? "Over budget" : "Remaining"}
          icon={Wallet}
          value={variance == null ? "—" : money(Math.abs(variance))}
          hint={cost.budget_status?.replace(/_/g, " ").toLowerCase()}
          tone={variance == null ? "neutral" : variance < 0 ? "bad" : "good"}
        />
      </div>

      <Card className="p-4">
        <SectionTitle hint="Every priced line, grouped">Cost by category</SectionTitle>
        {Object.keys(cost.cost_by_category).length > 0 ? (
          <CategoryBars data={cost.cost_by_category} total={cost.total_cost} />
        ) : (
          <p className="text-[13px] text-ink-3">No priced items.</p>
        )}
      </Card>

      <Card className="p-4">
        <SectionTitle hint="What the total is built from">Coverage</SectionTitle>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 text-[13px]">
          <Row label="Items priced" value={String(cost.items_with_data)} />
          <Row label="Items missing data" value={String(cost.items_missing_data)} />
          <Row label="Waste buffer applied" value={`${Math.round(event.waste_buffer_pct * 100)}%`} />
          <Row label="Drinks planned"
            value={String(Math.round(event.guest_count * event.expected_drinks_per_guest))} />
        </dl>
        {cost.items_missing_data > 0 && (
          <div className="mt-3">
            <Note tone="warn" icon={AlertTriangle}>
              {cost.items_missing_data} item{cost.items_missing_data === 1 ? " has" : "s have"} no
              price, so this total is lower than the real one. The app flags them rather than
              filling in a guess.
            </Note>
          </div>
        )}
      </Card>
    </div>
  );
}
