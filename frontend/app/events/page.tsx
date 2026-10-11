"use client";

import { useEffect, useState } from "react";
import { CalendarDays } from "lucide-react";
import { api, type EventListItem } from "@/lib/api";
import EventCard from "@/components/EventCard";
import { PageHeader, EmptyState, Card, Skeleton } from "@/components/ui";

export default function EventsPage() {
  const [events, setEvents] = useState<EventListItem[] | null>(null);

  useEffect(() => {
    api.listEvents(100).then((r) => setEvents(r.items)).catch(() => setEvents([]));
  }, []);

  return (
    <main className="max-w-[900px] mx-auto px-5 md:px-8 py-8">
      <PageHeader
        title="Events"
        subtitle={events ? `${events.length} event${events.length === 1 ? "" : "s"}` : undefined}
      />
      {events === null ? (
        <div className="flex flex-col gap-2">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[70px]" />)}
        </div>
      ) : events.length === 0 ? (
        <Card>
          <EmptyState
            icon={CalendarDays}
            title="No events yet."
            body="Tell Happy Hour AI what you're planning and we'll build it with you."
          />
        </Card>
      ) : (
        <div className="flex flex-col gap-2">
          {events.map((e) => <EventCard key={e.id} event={e} />)}
        </div>
      )}
    </main>
  );
}
