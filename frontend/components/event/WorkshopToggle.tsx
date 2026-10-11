"use client";

import { useState } from "react";
import { Wrench, Users, Check } from "lucide-react";
import { api } from "@/lib/api";
import { Card, Button, Chip, cx } from "@/components/ui";

const RATIOS = [1, 2, 3, 4];

/**
 * Whether this event is a workshop, and how many people share a station.
 *
 * This is an event-level fact — the same kind of thing as the guest count —
 * so it belongs on Overview beside the rest of what the event IS. The
 * consequences show up elsewhere: kit cost on Costs, kit buying on Suppliers.
 * It lived on Prep for one round, which was wrong: Prep is about making the
 * drinks, not about deciding what sort of event this is.
 */
export default function WorkshopToggle({
  eventId, isWorkshop, peoplePerStation, onChanged,
}: {
  eventId: string;
  isWorkshop: boolean;
  peoplePerStation: number;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);

  async function update(body: { is_workshop?: boolean; people_per_station?: number }) {
    setBusy(true);
    try {
      await api.setWorkshop(eventId, body);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  if (!isWorkshop) {
    return (
      <Card className="p-3.5 border-dashed">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <Wrench size={13} strokeWidth={1.75} className="text-ink-4" />
              <h3 className="text-[13px] font-medium text-ink">
                Is this a cocktail workshop?
              </h3>
            </div>
            <p className="mt-1 text-[12px] text-ink-3 leading-relaxed max-w-[64ch]">
              If the guests make the drinks themselves, the event also needs kit.
              Turning this on adds equipment to the costs and to the shopping.
            </p>
          </div>
          <Button
            icon={Wrench}
            onClick={() => update({ is_workshop: true })}
            disabled={busy}
          >
            {busy ? "Setting up…" : "Yes, it's a workshop"}
          </Button>
        </div>
      </Card>
    );
  }

  return (
    <Card className="p-3.5">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-accent">
          <Check size={13} strokeWidth={2.25} /> Workshop
        </span>
        <span className="text-line-2">·</span>
        <Users size={13} strokeWidth={1.75} className="text-ink-4" />
        <span className="text-[12.5px] text-ink-2">People per station</span>
        {RATIOS.map((n) => (
          <Chip
            key={n}
            active={n === peoplePerStation}
            disabled={busy}
            onClick={() => update({ people_per_station: n })}
          >
            {n}
          </Chip>
        ))}
        <button
          onClick={() => update({ is_workshop: false })}
          disabled={busy}
          className="ms-auto text-[12px] text-ink-4 hover:text-ink-2 transition-colors"
        >
          Not a workshop
        </button>
      </div>
      <p className="mt-2 text-[11.5px] text-ink-4 leading-relaxed">
        Tools are shared per station, so this ratio decides most of the kit bill.
        The equipment is costed under Costs and bought under Suppliers.
      </p>
    </Card>
  );
}
