"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import {
  GlassWater, Search, X, Plus, RefreshCw, AlertTriangle, Check, Undo2,
} from "lucide-react";
import { api, type Event, type Cocktail } from "@/lib/api";
import { Card, Button, EmptyState, Note, cx } from "@/components/ui";

type Row = {
  cocktail_id: string;
  name: string;
  allocation_pct: number;
  ingredients?: string[];
};

/**
 * The first few ingredients, as a sentence.
 *
 * A menu is chosen by people who do not necessarily know what a Sbagliato or a
 * Jasmine contains, and a list of bare names asks them to pick blindly. Three
 * is enough to recognise a drink — the full recipe is a click away on Prep and
 * would crowd the row here.
 */
function summarise(ingredients?: string[], limit = 3): string | null {
  if (!ingredients || ingredients.length === 0) return null;
  const shown = ingredients.slice(0, limit).join(", ");
  const rest = ingredients.length - limit;
  return rest > 0 ? `${shown} +${rest}` : shown;
}

/**
 * The menu, editable.
 *
 * Until now a menu could only be created — by the planner or the agent — and
 * never touched again. So "I asked for a Margarita and a Negroni and it came out
 * too expensive" had no answer inside the product: the only way to change one
 * drink was to plan the whole event again.
 *
 * TWO RULES SHAPE THIS COMPONENT
 *
 * Saving always recalculates. A menu change leaves every cost on the other tabs
 * describing a menu that no longer exists, and a stale price is worse than no
 * price — someone sets a budget by it. Save and recalculate are one action here
 * because they are one action in truth.
 *
 * Nothing is saved until you say so. Edits live in local state and the header
 * shows what will change, so trying an idea costs nothing and abandoning it
 * costs nothing.
 */
export default function MenuEditor({
  event, onSaved,
}: {
  event: Event;
  onSaved: () => void;
}) {
  const initial = useMemo<Row[]>(
    () => event.menu.map((m) => ({
      cocktail_id: m.cocktail_id,
      name: m.cocktail_name ?? "Cocktail",
      allocation_pct: m.allocation_pct,
      // The event's own menu does not carry ingredients, so they are filled in
      // from the library once it loads — the chosen rows should read the same
      // way as the ones you are choosing between.
      ingredients: undefined,
    })),
    [event.menu]
  );

  const [rows, setRows] = useState<Row[]>(initial);
  const [library, setLibrary] = useState<Cocktail[] | null>(null);
  const [query, setQuery] = useState("");
  const [picking, setPicking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { setRows(initial); }, [initial]);

  // Loaded once and used for both lists: the picker needs it to describe what
  // is on offer, and the chosen rows need it to describe what was chosen.
  useEffect(() => {
    let alive = true;
    api.getCocktails({ page_size: "200" })
      .then((r: any) => { if (alive) setLibrary(r.items ?? r.cocktails ?? []); })
      .catch(() => { if (alive) setLibrary([]); });
    return () => { alive = false; };
  }, []);

  const dirty = useMemo(() => {
    if (rows.length !== initial.length) return true;
    const a = [...rows].sort((x, y) => x.cocktail_id.localeCompare(y.cocktail_id));
    const b = [...initial].sort((x, y) => x.cocktail_id.localeCompare(y.cocktail_id));
    return a.some((r, i) =>
      r.cocktail_id !== b[i].cocktail_id ||
      Math.abs(r.allocation_pct - b[i].allocation_pct) > 0.001);
  }, [rows, initial]);

  // Shares must total 100%, and the numbers on screen must total 100 too.
  //
  // An even split of three is 33.33% each. Stored as exact thirds the engine is
  // right, but the inputs render 33, 33, 33 — and someone reading 99% has every
  // reason to think the app has lost a percent. So the split is done in whole
  // percentages using largest-remainder: 34, 33, 33. What you see adds up,
  // because it is what is actually stored.
  const rebalance = useCallback((list: Row[]): Row[] => {
    if (list.length === 0) return list;
    const n = list.length;
    const base = Math.floor(100 / n);
    const spare = 100 - base * n;       // 0..n-1, handed out one each
    return list.map((r, i) => ({
      ...r,
      allocation_pct: (base + (i < spare ? 1 : 0)) / 100,
    }));
  }, []);

  const total = rows.reduce((n, r) => n + r.allocation_pct, 0);
  const balanced = Math.abs(total - 1) < 0.005;

  function add(c: Cocktail) {
    if (rows.some((r) => r.cocktail_id === c.id)) return;
    setRows(rebalance([...rows, {
      cocktail_id: c.id, name: c.name, allocation_pct: 0,
      ingredients: c.ingredient_names,
    }]));
    setQuery("");
  }

  function remove(id: string) {
    setRows(rebalance(rows.filter((r) => r.cocktail_id !== id)));
  }

  function setPct(id: string, pct: number) {
    setRows(rows.map((r) =>
      r.cocktail_id === id ? { ...r, allocation_pct: Math.max(0, pct) / 100 } : r));
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await api.setMenu(event.id, rows.map((r) => ({
        cocktail_id: r.cocktail_id,
        allocation_pct: r.allocation_pct,
      })));
      // Not optional. Leaving the old costs on screen next to a new menu would
      // show a price for something nobody is making.
      if (rows.length > 0) await api.calculate(event.id);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save the menu");
    } finally {
      setSaving(false);
    }
  }

  const byId = new Map((library ?? []).map((c) => [c.id, c]));
  const chosen = new Set(rows.map((r) => r.cocktail_id));
  const results = (library ?? []).filter(
    (c) => !chosen.has(c.id) &&
      (!query.trim() || c.name.toLowerCase().includes(query.trim().toLowerCase()))
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-[15px] font-medium text-ink">Menu</h2>
          <p className="text-[12.5px] text-ink-3 mt-0.5">
            {rows.length} {rows.length === 1 ? "cocktail" : "cocktails"}
            {dirty && <span className="text-accent"> · unsaved changes</span>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {dirty && (
            <Button icon={Undo2} onClick={() => setRows(initial)} disabled={saving}>
              Discard
            </Button>
          )}
          {/* Primary only when there is something to save. A filled accent
              button with nothing behind it invites a click that does nothing. */}
          <Button
            variant={dirty ? "primary" : "secondary"}
            icon={saving ? RefreshCw : Check}
            onClick={save}
            disabled={!dirty || saving || !balanced}
            title={!balanced ? "Shares must add up to 100%" : undefined}
          >
            {saving ? "Saving and recalculating…"
              : dirty ? "Save and recalculate" : "Saved"}
          </Button>
        </div>
      </div>

      {error && <Note tone="warn" icon={AlertTriangle}>{error}</Note>}

      {!balanced && rows.length > 0 && (
        <Note tone="warn" icon={AlertTriangle}>
          Shares add up to {Math.round(total * 100)}%, not 100%. Adjust them, or
          remove and re-add a cocktail to split evenly.
        </Note>
      )}

      {rows.length === 0 ? (
        <Card>
          <EmptyState
            icon={GlassWater}
            title="No cocktails on the menu."
            body="Add one below, or ask the agent on the right to build a menu for you."
          />
        </Card>
      ) : (
        <div className="flex flex-col gap-2">
          {rows.map((r) => (
            <Card key={r.cocktail_id} className="px-4 py-3 flex items-center gap-3">
              <div className="min-w-0 flex-1">
                <div dir="auto" className="text-[14px] font-medium text-ink truncate">
                  {r.name}
                </div>
                {summarise(byId.get(r.cocktail_id)?.ingredient_names) && (
                  <div dir="auto" className="text-[11.5px] text-ink-4 truncate mt-0.5">
                    {summarise(byId.get(r.cocktail_id)?.ingredient_names)}
                  </div>
                )}
                <div className="mt-1 h-1.5 bg-sunk rounded-full overflow-hidden max-w-[220px]">
                  <div
                    className="h-full bg-accent/70 rounded-full transition-all"
                    style={{ width: `${Math.min(100, r.allocation_pct * 100)}%` }}
                  />
                </div>
              </div>
              <label className="flex items-center gap-1.5 shrink-0">
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={Math.round(r.allocation_pct * 100)}
                  onChange={(e) => setPct(r.cocktail_id, Number(e.target.value))}
                  aria-label={`Share of drinks for ${r.name}`}
                  className="w-14 h-8 text-[13px] tnum text-end px-2 rounded-lg border border-line bg-surface focus:border-accent/50"
                />
                <span className="text-[12.5px] text-ink-4">%</span>
              </label>
              <button
                onClick={() => remove(r.cocktail_id)}
                aria-label={`Remove ${r.name}`}
                className="w-8 h-8 grid place-items-center rounded-lg text-ink-4 hover:text-bad hover:bg-bad-soft transition-colors shrink-0"
              >
                <X size={15} strokeWidth={2} />
              </button>
            </Card>
          ))}
        </div>
      )}

      {!picking ? (
        <button
          onClick={() => setPicking(true)}
          className="flex items-center justify-center gap-1.5 h-10 rounded-[12px] border border-dashed border-line-2 text-[13px] text-ink-2 hover:border-accent-line hover:bg-accent-soft/40 transition-colors"
        >
          <Plus size={15} strokeWidth={1.75} /> Add a cocktail
        </button>
      ) : (
        <Card className="p-3">
          <div className="flex items-center gap-2 mb-2.5">
            <Search size={14} strokeWidth={1.75} className="text-ink-4 shrink-0" />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              dir="auto"
              placeholder="Search the cocktail library…"
              className="flex-1 min-w-0 bg-transparent outline-none text-[13.5px] placeholder:text-ink-4"
            />
            <button
              onClick={() => { setPicking(false); setQuery(""); }}
              aria-label="Close"
              className="w-7 h-7 grid place-items-center rounded-lg text-ink-4 hover:bg-sunk"
            >
              <X size={15} />
            </button>
          </div>

          {library === null ? (
            <p className="text-[13px] text-ink-4 py-2">Loading the library…</p>
          ) : results.length === 0 ? (
            <p className="text-[13px] text-ink-4 py-2">
              {query ? `Nothing matching "${query}".` : "Everything is already on the menu."}
            </p>
          ) : (
            <>
              {/* A scrolling list, not a chip cloud. Thirty names wrapped as
                  pills is a wall to read; rows in a fixed order can be skimmed,
                  and there is room beside each one to say what it actually is. */}
              <div className="max-h-[300px] overflow-y-auto -mx-1 px-1">
                {results.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => add(c)}
                    className="w-full flex items-center justify-between gap-3 px-2.5 py-2 rounded-lg text-start hover:bg-accent-soft transition-colors group"
                  >
                    <span className="min-w-0">
                      <span dir="auto" className="block text-[13.5px] text-ink truncate">
                        {c.name}
                      </span>
                      {summarise(c.ingredient_names) && (
                        <span dir="auto" className="block text-[11.5px] text-ink-4 truncate">
                          {summarise(c.ingredient_names)}
                        </span>
                      )}
                    </span>
                    <span className="flex items-center gap-2 shrink-0">
                      {!c.alcoholic && (
                        <span className="text-[10.5px] uppercase tracking-[.05em] text-good">
                          no alcohol
                        </span>
                      )}
                      {c.complexity && (
                        <span className="text-[11.5px] text-ink-4">{c.complexity}</span>
                      )}
                      <Plus
                        size={14}
                        strokeWidth={2}
                        className="text-ink-4 group-hover:text-accent"
                      />
                    </span>
                  </button>
                ))}
              </div>
              <p className="mt-2 pt-2 border-t border-line text-[11.5px] text-ink-4">
                {results.length} available{query ? ` matching "${query}"` : ""}
              </p>
            </>
          )}
        </Card>
      )}
    </div>
  );
}
