"use client";

import { useEffect, useState } from "react";
import {
  Wrench, AlertTriangle, Users, PackageX, Info,
} from "lucide-react";
import { api, type EquipmentPlan } from "@/lib/api";
import { Card, Button, Note, Chip, money, cx } from "@/components/ui";

const RATIOS = [1, 2, 3, 4];

/**
 * The kit a workshop needs, and what the station ratio does to the bill.
 *
 * THE RATIO IS THE WHOLE SCREEN
 * One person per station or four changes the equipment cost by a factor of
 * three and a half — ₪4,400 against ₪1,235 for twenty people. It is the single
 * largest lever in a workshop's budget and it is a judgement about how the
 * workshop should feel, not a calculation. So it sits at the top as a control,
 * the numbers move as you press it, and nothing is saved until you say so.
 *
 * Glassware does not move with it, which is the point worth seeing: tools are
 * shared per station, glasses are one each because everyone drinks.
 */
export default function WorkshopEquipment({
  eventId, onSaved,
}: {
  eventId: string;
  onSaved?: () => void;
}) {
  const [plan, setPlan] = useState<EquipmentPlan | null>(null);
  const [ratio, setRatio] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.getEquipment(eventId, ratio ?? undefined)
      .then((p) => {
        if (!alive) return;
        setPlan(p);
        if (ratio === null) setRatio(p.people_per_station);
      })
      .catch((e) => {
        if (alive) setError(e instanceof Error ? e.message : "Could not plan the kit");
      });
    return () => { alive = false; };
  }, [eventId, ratio]);

  async function save() {
    if (ratio == null) return;
    setSaving(true);
    try {
      await api.setWorkshop(eventId, { people_per_station: ratio });
      const p = await api.getEquipment(eventId);
      setPlan(p);
      onSaved?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    } finally {
      setSaving(false);
    }
  }

  if (error) return <Note tone="warn" icon={AlertTriangle}>{error}</Note>;
  if (!plan || ratio == null) return null;

  const dirty = ratio !== plan.saved_people_per_station;
  const shakerAlts = plan.alternatives.filter((a) => a.for === "shaker");

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-[15px] font-medium text-ink">Equipment</h2>
          <p className="text-[12.5px] text-ink-3 mt-0.5">
            {plan.participants} participants · {plan.stations}{" "}
            {plan.stations === 1 ? "station" : "stations"}
          </p>
        </div>
        <div className="text-end">
          {plan.total_cost != null ? (
            <>
              <div className="text-[20px] font-semibold tnum text-ink leading-none">
                {money(plan.total_cost)}
              </div>
              <div className="mt-1 text-[11.5px] text-ink-4">
                {money(plan.total_cost / plan.participants)} per person
              </div>
            </>
          ) : (
            <div className="text-[13px] text-warn">Incomplete — see below</div>
          )}
        </div>
      </div>

      <Card className="p-3.5">
        <div className="flex items-center gap-2 flex-wrap">
          <Users size={14} strokeWidth={1.75} className="text-ink-4" />
          <span className="text-[12.5px] text-ink-2">People per station</span>
          {RATIOS.map((n) => (
            <Chip key={n} active={n === ratio} onClick={() => setRatio(n)}>
              {n}
            </Chip>
          ))}
          {dirty && (
            <Button variant="primary" onClick={save} disabled={saving} className="ms-auto">
              {saving ? "Saving…" : "Save this ratio"}
            </Button>
          )}
        </div>
        <p className="mt-2 text-[11.5px] text-ink-4 leading-relaxed">
          Tools are shared per station, so this halves or doubles most of the bill.
          Glassware does not change — everyone drinks from their own glass.
        </p>
      </Card>

      <Card className="p-0 overflow-hidden">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="bg-sunk border-b border-line text-[10.5px] uppercase tracking-[.05em] text-ink-3">
              <th className="text-start font-medium px-3.5 py-2">Item</th>
              <th className="text-end font-medium px-2 py-2 w-[76px]">Needed</th>
              <th className="text-end font-medium px-2 py-2 w-[104px]">Buy</th>
              <th className="text-end font-medium px-3.5 py-2 w-[92px]">Cost</th>
            </tr>
          </thead>
          <tbody>
            {plan.lines.map((l) => (
              <tr key={l.key} className="border-b border-line/70 last:border-0">
                <td className="px-3.5 py-2">
                  <span className="text-ink">{l.name}</span>
                  {!l.essential && (
                    <span className="ms-1.5 text-[11px] text-ink-4">optional</span>
                  )}
                  {l.product_name && (
                    <div dir="auto" className="text-[11.5px] text-ink-4 mt-0.5">
                      {l.product_name}
                      {!l.in_stock && (
                        <span className="text-warn"> · out of stock</span>
                      )}
                    </div>
                  )}
                  {l.status === "PRICE_MISSING" && (
                    <div className="text-[11.5px] text-warn mt-0.5">
                      No price — {l.note ?? "no shop publishes one"}
                    </div>
                  )}
                </td>
                <td className="px-2 py-2 text-end tnum text-ink-2">{l.needed}</td>
                <td className="px-2 py-2 text-end tnum text-ink-3">
                  {/* The gap between needed and bought is the pack size, and it
                      is money. Twenty glasses means twenty-four bought. */}
                  {l.packs != null
                    ? l.pack_size > 1
                      ? `${l.packs} × ${l.pack_size} = ${l.units_bought}`
                      : `${l.packs}`
                    : "—"}
                </td>
                <td className="px-3.5 py-2 text-end tnum font-medium text-ink">
                  {l.total != null ? money(l.total) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {plan.out_of_stock.length > 0 && (
        <Note tone="warn" icon={PackageX}>
          Out of stock right now: {plan.out_of_stock.join(", ")}. The price is real
          and the total includes it, but the order cannot be placed today.
        </Note>
      )}

      {!plan.is_complete && (
        <Note tone="warn" icon={AlertTriangle}>
          No total, because {plan.missing.join(", ")} has no published price
          anywhere. The priced part comes to {money(plan.known_cost)} — do not
          budget from that figure as though it were the whole kit.
        </Note>
      )}

      {shakerAlts.length > 0 && (
        <Card className="p-3.5">
          <div className="flex items-center gap-1.5 mb-1.5">
            <Info size={13} strokeWidth={1.75} className="text-ink-4" />
            <h3 className="text-[12.5px] font-medium text-ink">
              About the shaker
            </h3>
          </div>
          <p className="text-[12px] text-ink-3 leading-relaxed">
            The costed line uses the full bartender kit, because both standalone
            shakers are out of stock:
          </p>
          <div className="mt-2 flex flex-col gap-1">
            {shakerAlts.map((a) => (
              <div key={a.product} className="flex items-center justify-between gap-3 text-[12px]">
                <span dir="auto" className="text-ink-2 truncate">
                  {a.product}
                  {!a.in_stock && <span className="text-warn"> · out of stock</span>}
                </span>
                <span className="tnum text-ink-3 shrink-0">{money(a.price)}</span>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[11.5px] text-ink-4 leading-relaxed">
            Worth a phone call — a standalone shaker at {money(shakerAlts[0].price)}{" "}
            against {money(130)} for the kit is most of this bill.
          </p>
        </Card>
      )}

      <p className="text-[11.5px] text-ink-4 leading-relaxed">{plan.note}</p>
    </div>
  );
}
