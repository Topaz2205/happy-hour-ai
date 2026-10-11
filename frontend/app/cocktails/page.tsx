"use client";

import { useEffect, useMemo, useState } from "react";
import { Search, GlassWater, X, Filter } from "lucide-react";
import { api, type Cocktail, type CocktailDetail } from "@/lib/api";
import {
  PageHeader, Card, EmptyState, Skeleton, Button, cx, amount,
} from "@/components/ui";

export default function CocktailsPage() {
  const [all, setAll] = useState<Cocktail[] | null>(null);
  const [themes, setThemes] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const [theme, setTheme] = useState<string | null>(null);
  const [selected, setSelected] = useState<CocktailDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  useEffect(() => {
    api.getCocktails({ limit: "200" }).then((r) => setAll(r.items)).catch(() => setAll([]));
    api.getCocktailThemes().then((r) => setThemes(r.themes)).catch(() => setThemes([]));
  }, []);

  const shown = useMemo(() => {
    if (!all) return null;
    const needle = q.trim().toLowerCase();
    return all.filter(
      (c) =>
        (!theme || c.theme === theme) &&
        (!needle || c.name.toLowerCase().includes(needle))
    );
  }, [all, q, theme]);

  async function open(c: Cocktail) {
    setLoadingDetail(true);
    setSelected(null);
    try { setSelected(await api.getCocktail(c.id)); }
    finally { setLoadingDetail(false); }
  }

  return (
    <main className="max-w-[1100px] mx-auto px-5 md:px-8 py-8">
      <PageHeader
        title="Cocktails"
        subtitle={shown ? `${shown.length} of ${all?.length ?? 0} recipes` : undefined}
      />

      <div className="flex flex-wrap items-center gap-2 mb-5">
        <div className="relative flex-1 min-w-[200px] max-w-[320px]">
          <Search size={15} strokeWidth={1.75}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-4 pointer-events-none" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search cocktails"
            aria-label="Search cocktails"
            className="w-full h-9 pl-9 pr-3 bg-surface border border-line rounded-lg text-[13.5px] outline-none focus:border-accent/50 placeholder:text-ink-4"
          />
        </div>
        <div className="flex items-center gap-1.5">
          <Filter size={14} strokeWidth={1.75} className="text-ink-4" />
          <button
            onClick={() => setTheme(null)}
            className={cx(
              "h-8 px-2.5 rounded-lg text-[13px] border transition-colors",
              theme === null ? "bg-ink text-white border-ink" : "bg-surface border-line text-ink-2 hover:border-line-2"
            )}
          >
            All
          </button>
          {themes.map((t) => (
            <button
              key={t}
              onClick={() => setTheme(t === theme ? null : t)}
              className={cx(
                "h-8 px-2.5 rounded-lg text-[13px] border capitalize transition-colors",
                theme === t ? "bg-ink text-white border-ink" : "bg-surface border-line text-ink-2 hover:border-line-2"
              )}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="flex gap-5">
        <div className="flex-1 min-w-0">
          {shown === null ? (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
              {Array.from({ length: 9 }).map((_, i) => <Skeleton key={i} className="h-[68px]" />)}
            </div>
          ) : shown.length === 0 ? (
            <Card><EmptyState icon={GlassWater} title="No cocktails match." body="Try a different search or clear the filter." /></Card>
          ) : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
              {shown.map((c) => (
                <button
                  key={c.id}
                  onClick={() => open(c)}
                  className={cx(
                    "text-left bg-surface border rounded-[10px] px-3.5 py-3 transition-colors",
                    selected?.id === c.id ? "border-accent" : "border-line hover:border-line-2"
                  )}
                >
                  <div className="text-[13.5px] font-medium text-ink truncate">{c.name}</div>
                  <div className="mt-1 flex items-center gap-2 text-[12px] text-ink-4">
                    {c.theme && <span className="capitalize">{c.theme}</span>}
                    {c.glass_type && <span className="truncate" dir="auto">{c.glass_type}</span>}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {(selected || loadingDetail) && (
          <aside className="hidden lg:block w-[300px] shrink-0">
            <Card className="p-4 sticky top-6 hh-rise">
              {loadingDetail || !selected ? (
                <div className="flex flex-col gap-2">
                  {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-4" />)}
                </div>
              ) : (
                <>
                  <div className="flex items-start justify-between gap-2 mb-3">
                    <h2 className="text-[15px] font-semibold leading-tight">{selected.name}</h2>
                    <button
                      onClick={() => setSelected(null)}
                      aria-label="Close"
                      className="w-7 h-7 grid place-items-center rounded-lg text-ink-4 hover:bg-sunk shrink-0"
                    >
                      <X size={15} />
                    </button>
                  </div>
                  {(selected.technique || selected.glass_type) && (
                    <p className="text-[12.5px] text-ink-3 mb-3 leading-relaxed" dir="auto">
                      {[selected.technique, selected.glass_type].filter(Boolean).join(" · ")}
                    </p>
                  )}
                  <table className="w-full mb-3">
                    <tbody>
                      {selected.ingredients.map((ing) => (
                        <tr key={ing.ingredient_id}>
                          <td className="py-[3px] text-[12.5px] text-accent-hi font-medium tnum whitespace-nowrap w-[76px]">
                            {amount(ing.amount, ing.unit)}
                          </td>
                          <td className="py-[3px] text-[13px] text-ink-2">{ing.canonical_name}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {selected.garnish && (
                    <p className="pt-3 border-t border-line text-[12.5px] text-ink-3" dir="auto">
                      Garnish: {selected.garnish}
                    </p>
                  )}
                </>
              )}
            </Card>
          </aside>
        )}
      </div>

      {/* Mobile detail sheet */}
      {selected && (
        <div className="lg:hidden fixed inset-x-0 bottom-0 z-50 max-h-[70vh] overflow-y-auto bg-surface border-t border-line rounded-t-2xl p-4 hh-rise shadow-2xl">
          <div className="flex items-start justify-between gap-2 mb-3">
            <h2 className="text-[15px] font-semibold">{selected.name}</h2>
            <Button size="sm" variant="ghost" onClick={() => setSelected(null)}>Close</Button>
          </div>
          <table className="w-full">
            <tbody>
              {selected.ingredients.map((ing) => (
                <tr key={ing.ingredient_id}>
                  <td className="py-1 text-[12.5px] text-accent-hi font-medium tnum w-[76px]">
                    {amount(ing.amount, ing.unit)}
                  </td>
                  <td className="py-1 text-[13px] text-ink-2">{ing.canonical_name}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
