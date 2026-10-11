"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import Link from "next/link";

import {
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  PencilLine,
  Plus,
  Wallet,
} from "lucide-react";

import {
  api,
  type EventListItem,
} from "@/lib/api";

import EventCard from "@/components/EventCard";

import {
  EmptyState,
  SectionTitle,
  Skeleton,
  StatTile,
  money,
} from "@/components/ui";


const STATS_SAMPLE = 100;
const RECENT_SHOWN = 6;


export default function Home() {
  const [events, setEvents] =
    useState<EventListItem[] | null>(null);

  const [total, setTotal] =
    useState<number | null>(null);


  const load = useCallback(
    async () => {
      try {
        const res =
          await api.listEvents(
            STATS_SAMPLE
          );

        setEvents(res.items);
        setTotal(res.count);
      } catch {
        setEvents([]);
        setTotal(null);
      }
    },
    []
  );


  useEffect(() => {
    load();
  }, [load]);


  const stats = useMemo(() => {
    if (!events) return null;

    const costed =
      events.filter(
        (event) =>
          event.estimated_cost != null &&
          !event.cost_is_partial
      );

    const drafts =
      events.filter(
        (event) =>
          event.menu_count === 0 ||
          event.estimated_cost == null
      );

    const budgets =
      events
        .filter(
          (event) =>
            event.budget != null
        )
        .map(
          (event) =>
            event.budget as number
        );

    const avg =
      budgets.length
        ? Math.round(
            budgets.reduce(
              (sum, value) =>
                sum + value,
              0
            ) / budgets.length
          )
        : null;

    return {
      costed: costed.length,
      drafts: drafts.length,
      avg,
    };
  }, [events]);


  const recent =
    events?.slice(
      0,
      RECENT_SHOWN
    ) ?? [];


  return (
    <main className="w-full max-w-[1120px] mx-auto px-5 md:px-8 py-8 md:py-12">

      <header className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-5 mb-8">

        <div>
          <h1 className="text-[28px] md:text-[32px] font-semibold tracking-[-.025em] text-ink">
            Your events
          </h1>

          <p className="mt-2 text-[14px] text-ink-3 max-w-[580px]">
            Create, manage and review your cocktail events.
          </p>
        </div>


        <Link
          href="/events/new"
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-ink px-4 py-2.5 text-[13px] font-medium text-white hover:bg-ink-2 transition-colors"
        >
          <Plus size={15} />
          Create new event
        </Link>

      </header>


      <section className="mb-9">

        {events === null ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">
            {[0, 1, 2, 3].map(
              (index) => (
                <Skeleton
                  key={index}
                  className="h-[78px]"
                />
              )
            )}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5">

            <StatTile
              icon={CalendarDays}
              label="Events"
              value={
                total ??
                events.length
              }
              sub="all time"
            />

            <StatTile
              icon={CheckCircle2}
              label="Costed"
              tone="good"
              value={
                stats?.costed ?? 0
              }
              sub="fully priced"
            />

            <StatTile
              icon={PencilLine}
              label="Drafts"
              value={
                stats?.drafts ?? 0
              }
              sub="not costed yet"
            />

            <StatTile
              icon={Wallet}
              label="Avg budget"
              tone="accent"
              value={
                stats?.avg != null
                  ? money(stats.avg)
                  : "—"
              }
              sub={
                stats?.avg != null
                  ? "where one was set"
                  : "none set yet"
              }
            />

          </div>
        )}

      </section>


      <section>

        <SectionTitle
          hint={
            total &&
            total > RECENT_SHOWN
              ? `Your ${RECENT_SHOWN} most recent of ${total}`
              : "Newest first"
          }
          right={
            events &&
            events.length > 0 ? (
              <Link
                href="/events"
                className="inline-flex items-center gap-1 text-[13px] text-ink-2 hover:text-ink transition-colors"
              >
                View all
                <ArrowRight size={13} />
              </Link>
            ) : null
          }
        >
          Recent events
        </SectionTitle>


        {events === null ? (
          <div className="flex flex-col gap-2.5">
            {[0, 1, 2].map(
              (index) => (
                <Skeleton
                  key={index}
                  className="h-[86px]"
                />
              )
            )}
          </div>
        ) : events.length === 0 ? (
          <div className="bg-surface border border-line rounded-[12px]">

            <EmptyState
              icon={CalendarDays}
              title="No events yet."
              body="Create your first event and Happy Hour AI will guide you through the setup."
            />

          </div>
        ) : (
          <div className="flex flex-col gap-2.5">

            {recent.map(
              (event) => (
                <EventCard
                  key={event.id}
                  event={event}
                />
              )
            )}

          </div>
        )}

      </section>

    </main>
  );
}
