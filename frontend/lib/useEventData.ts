"use client";

import { useCallback, useEffect, useState } from "react";
import {
  api, type Event, type CostSummary, type PurchasePlan, type ShoppingList,
} from "./api";

export interface EventData {
  event: Event | null;
  cost: CostSummary | null;
  plan: PurchasePlan | null;
  shopping: ShoppingList | null;
  loading: boolean;
  error: string | null;
  /** True once the engine has produced purchase items for this event. */
  costed: boolean;
  reload: () => Promise<void>;
  calculate: () => Promise<void>;
  calculating: boolean;
}

/**
 * Loads everything the workspace shows, in one place.
 *
 * The cost / purchase-plan / shopping endpoints legitimately 404 before an
 * event has been calculated — that is an empty state, not a failure, so those
 * rejections resolve to null instead of surfacing an error banner.
 */
export function useEventData(id: string, retailer?: string): EventData {
  const [event, setEvent] = useState<Event | null>(null);
  const [cost, setCost] = useState<CostSummary | null>(null);
  const [plan, setPlan] = useState<PurchasePlan | null>(null);
  const [shopping, setShopping] = useState<ShoppingList | null>(null);
  const [loading, setLoading] = useState(true);
  const [calculating, setCalculating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!id) return;
    try {
      const ev = await api.getEvent(id);
      setEvent(ev);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load this event");
      setLoading(false);
      return;
    }

    const soft = <T,>(p: Promise<T>) => p.then((v) => v).catch(() => null);
    const [c, pl, sh] = await Promise.all([
      soft(api.getCostSummary(id)),
      soft(api.getPurchasePlan(id, retailer)),
      soft(api.getShoppingList(id)),
    ]);
    setCost(c);
    setPlan(pl);
    setShopping(sh);
    setLoading(false);
  }, [id, retailer]);

  useEffect(() => { reload(); }, [reload]);

  const calculate = useCallback(async () => {
    if (!id) return;
    setCalculating(true);
    setError(null);
    try {
      await api.calculate(id);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Calculation failed");
    } finally {
      setCalculating(false);
    }
  }, [id, reload]);

  return {
    event, cost, plan, shopping, loading, error,
    costed: Boolean(shopping && shopping.items.length > 0),
    reload, calculate, calculating,
  };
}
