"use client";

import { useEffect, useState, useCallback } from "react";
import {
  api,
  type UnmappedIngredient,
  type MappingCandidate,
  type ExistingMapping,
  type MappingCoverage,
} from "@/lib/api";

type Tab = "unmapped" | "mapped";

export default function MappingsPage() {
  const [tab, setTab] = useState<Tab>("unmapped");
  const [coverage, setCoverage] = useState<MappingCoverage | null>(null);
  const [unmapped, setUnmapped] = useState<UnmappedIngredient[]>([]);
  const [mapped, setMapped] = useState<ExistingMapping[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Per-row candidate state
  const [openRow, setOpenRow] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<MappingCandidate[]>([]);
  const [candidatesLoading, setCandidatesLoading] = useState(false);
  const [showAllCandidates, setShowAllCandidates] = useState(false);
  const [allOther, setAllOther] = useState<MappingCandidate[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [cov, un, mp] = await Promise.all([
        api.getMappingCoverage(),
        api.getUnmapped(),
        api.getMapped(),
      ]);
      setCoverage(cov);
      setUnmapped(un.items);
      setMapped(mp.items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load mappings");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function openCandidates(ing: UnmappedIngredient) {
    if (openRow === ing.ingredient_id) {
      setOpenRow(null);
      return;
    }
    setOpenRow(ing.ingredient_id);
    setSelected("");
    setNotes("");
    setShowAllCandidates(false);
    setCandidatesLoading(true);
    try {
      const res = await api.getCandidates(ing.ingredient_id);
      setCandidates(res.same_category);
      setAllOther(res.other);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load candidates");
    } finally {
      setCandidatesLoading(false);
    }
  }

  async function save(ing: UnmappedIngredient) {
    if (!selected) return;
    setSaving(true);
    try {
      const res = await api.createMapping({
        ingredient_id: ing.ingredient_id,
        product_id: selected,
        preferred: true,
        substitution_allowed: true,
        notes: notes.trim() || undefined,
      });
      setFlash(
        res.warning
          ? `Mapped ${res.ingredient_name} → ${res.product_name}. ${res.warning}`
          : `Mapped ${res.ingredient_name} → ${res.product_name}.`
      );
      setOpenRow(null);
      await refresh();
      setTimeout(() => setFlash(null), 6000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save mapping");
    } finally {
      setSaving(false);
    }
  }

  async function remove(m: ExistingMapping) {
    setSaving(true);
    try {
      await api.deleteMapping(m.mapping_id);
      setFlash(`Removed mapping for ${m.ingredient_name}.`);
      await refresh();
      setTimeout(() => setFlash(null), 5000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to remove mapping");
    } finally {
      setSaving(false);
    }
  }

  const visibleCandidates = showAllCandidates
    ? [...candidates, ...allOther]
    : candidates;

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-12">
        <div className="animate-pulse text-ink-4">Loading mappings…</div>
      </div>
    );
  }

  return (
    <div className="max-w-[1100px] mx-auto px-5 md:px-8 py-8">
      <header className="mb-6">
        <h1 className="text-[22px] font-semibold tracking-[-.015em] text-ink">Mappings</h1>
        <p className="mt-1 text-[13.5px] text-ink-3 max-w-[70ch] leading-relaxed">
          Recipes name specific brands that the price lists don&apos;t always
          carry. Nothing is substituted automatically — each pairing below is a
          decision you make, and the costing engine only uses what you approve
          here.
        </p>
      </header>

      {/* Coverage */}
      {coverage && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <Stat
            label="Costable coverage"
            value={`${coverage.coverage_pct}%`}
            hint={`${coverage.mapped_and_priced} of ${coverage.total_ingredients} ingredients`}
            accent
          />
          <Stat label="Mapped" value={coverage.mapped} />
          <Stat label="Unmapped" value={coverage.unmapped} warn={coverage.unmapped > 0} />
          <Stat
            label="Mapped, no price"
            value={coverage.mapped_without_price}
            warn={coverage.mapped_without_price > 0}
          />
        </div>
      )}

      {coverage && (
        <div className="mb-8 h-2 w-full rounded-full bg-line overflow-hidden">
          <div
            className="h-full bg-accent transition-all"
            style={{ width: `${coverage.coverage_pct}%` }}
          />
        </div>
      )}

      {flash && (
        <div className="mb-6 rounded-lg border border-good/25 bg-good-soft px-4 py-3 text-sm text-good">
          {flash}
        </div>
      )}
      {error && (
        <div className="mb-6 rounded-lg border border-bad/25 bg-bad-soft px-4 py-3 text-sm text-bad">
          {error}
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-line mb-6">
        <TabButton active={tab === "unmapped"} onClick={() => setTab("unmapped")}>
          Needs mapping ({unmapped.length})
        </TabButton>
        <TabButton active={tab === "mapped"} onClick={() => setTab("mapped")}>
          Mapped ({mapped.length})
        </TabButton>
      </div>

      {tab === "unmapped" && (
        <div className="space-y-2">
          {unmapped.length === 0 && (
            <p className="text-ink-3 py-8 text-center">
              Every ingredient is mapped.
            </p>
          )}
          {unmapped.map((ing) => (
            <div
              key={ing.ingredient_id}
              className="rounded-[10px] border border-line bg-surface overflow-hidden"
            >
              <button
                onClick={() => openCandidates(ing)}
                className="w-full flex items-center gap-4 px-4 py-3 text-left hover:bg-sunk transition"
              >
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-ink truncate">
                    {ing.canonical_name}
                  </div>
                  <div className="text-xs text-ink-3 mt-0.5">
                    {ing.category} · {ing.unit_type}
                    {ing.alcoholic && " · alcoholic"}
                  </div>
                </div>
                {ing.cocktail_usage_count > 0 && (
                  <span
                    className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${
                      ing.cocktail_usage_count >= 5
                        ? "bg-accent-soft text-accent-hi"
                        : "bg-sunk text-ink-2"
                    }`}
                  >
                    {ing.cocktail_usage_count} cocktail
                    {ing.cocktail_usage_count === 1 ? "" : "s"}
                  </span>
                )}
                <span className="shrink-0 text-ink-4 text-sm">
                  {openRow === ing.ingredient_id ? "▲" : "▼"}
                </span>
              </button>

              {openRow === ing.ingredient_id && (
                <div className="border-t border-line bg-sunk px-4 py-4">
                  {candidatesLoading ? (
                    <div className="text-sm text-ink-3">Loading products…</div>
                  ) : (
                    <>
                      <label className="block text-xs font-medium text-ink-2 mb-1.5">
                        Substitute with
                      </label>
                      <select
                        value={selected}
                        onChange={(e) => setSelected(e.target.value)}
                        className="w-full rounded-md border border-line-2 bg-white px-3 py-2 text-sm focus:border-accent focus:outline-none focus:ring-1 focus:ring-amber-500"
                      >
                        <option value="">Select a product…</option>
                        {visibleCandidates.map((c) => (
                          <option key={c.product_id} value={c.product_id}>
                            {c.canonical_name || c.product_name}
                            {c.package_size ? ` · ${c.package_size}${c.package_unit ?? ""}` : ""}
                            {c.has_price
                              ? ` · ₪${c.price_after_vat}`
                              : " · NO PRICE"}
                            {c.supplier_name ? ` · ${c.supplier_name}` : ""}
                          </option>
                        ))}
                      </select>

                      {!showAllCandidates && allOther.length > 0 && (
                        <button
                          onClick={() => setShowAllCandidates(true)}
                          className="mt-2 text-xs text-accent-hi hover:text-accent-hi underline"
                        >
                          Showing {candidates.length} {ing.category} products —
                          show all {candidates.length + allOther.length}
                        </button>
                      )}

                      <label className="block text-xs font-medium text-ink-2 mt-4 mb-1.5">
                        Note <span className="font-normal text-ink-4">(optional)</span>
                      </label>
                      <input
                        value={notes}
                        onChange={(e) => setNotes(e.target.value)}
                        placeholder="e.g. house pour, approved by bar manager"
                        className="w-full rounded-md border border-line-2 bg-white px-3 py-2 text-sm focus:border-accent focus:outline-none focus:ring-1 focus:ring-amber-500"
                      />

                      {selected &&
                        !visibleCandidates.find((c) => c.product_id === selected)
                          ?.has_price && (
                          <p className="mt-3 rounded-md bg-accent-soft border border-accent-line px-3 py-2 text-xs text-accent-hi">
                            This product has no price on file. The mapping will
                            save, but costing will report PRICE_MISSING until a
                            price is added.
                          </p>
                        )}

                      <div className="mt-4 flex gap-2">
                        <button
                          onClick={() => save(ing)}
                          disabled={!selected || saving}
                          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hi disabled:opacity-40 disabled:cursor-not-allowed transition"
                        >
                          {saving ? "Saving…" : "Save mapping"}
                        </button>
                        <button
                          onClick={() => setOpenRow(null)}
                          className="rounded-md border border-line-2 bg-white px-4 py-2 text-sm text-ink-2 hover:bg-sunk transition"
                        >
                          Cancel
                        </button>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === "mapped" && (
        <div className="overflow-x-auto rounded-lg border border-line">
          <table className="w-full text-sm">
            <thead className="bg-sunk text-ink-2">
              <tr>
                <Th>Ingredient</Th>
                <Th>Mapped product</Th>
                <Th>Supplier</Th>
                <Th className="text-right">Price</Th>
                <Th>Note</Th>
                <Th />
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 bg-white">
              {mapped.map((m) => (
                <tr key={m.mapping_id} className="hover:bg-sunk">
                  <td className="px-4 py-2.5 font-medium text-ink">
                    {m.ingredient_name}
                  </td>
                  <td className="px-4 py-2.5 text-ink-2">{m.product_name}</td>
                  <td className="px-4 py-2.5 text-ink-3 text-xs">
                    {m.supplier_name ?? "—"}
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums">
                    {m.has_price ? (
                      `₪${m.price_after_vat}`
                    ) : (
                      <span className="rounded bg-accent-soft px-1.5 py-0.5 text-xs text-accent-hi">
                        PRICE_MISSING
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5 text-ink-3 text-xs max-w-[16rem] truncate">
                    {m.notes ?? "—"}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <button
                      onClick={() => remove(m)}
                      disabled={saving}
                      className="text-xs text-bad hover:text-bad hover:underline disabled:opacity-40"
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Small presentational helpers ───────────────────────────────────────────

function Stat({
  label,
  value,
  hint,
  accent,
  warn,
}: {
  label: string;
  value: string | number;
  hint?: string;
  accent?: boolean;
  warn?: boolean;
}) {
  return (
    <div
      className={`rounded-lg border p-4 ${
        accent
          ? "border-accent-line bg-accent-soft"
          : warn
            ? "border-accent-line bg-white"
            : "border-line bg-white"
      }`}
    >
      <div className="text-xs uppercase tracking-wide text-ink-3">{label}</div>
      <div
        className={`mt-1 text-2xl font-semibold tabular-nums ${
          warn ? "text-accent-hi" : "text-ink"
        }`}
      >
        {value}
      </div>
      {hint && <div className="mt-0.5 text-xs text-ink-3">{hint}</div>}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition ${
        active
          ? "border-accent-hi text-accent-hi"
          : "border-transparent text-ink-3 hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
}

function Th({
  children,
  className = "",
}: {
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <th
      className={`px-4 py-2.5 text-left font-medium text-xs uppercase tracking-wide ${className}`}
    >
      {children}
    </th>
  );
}
