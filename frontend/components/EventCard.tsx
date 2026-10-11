"use client";

import Link from "next/link";
import { useState } from "react";
import {
  Users,
  GlassWater,
  Wallet,
  MapPin,
  ChevronRight,
  CalendarDays,
  AlertTriangle,
  MoreHorizontal,
  Pencil,
  Trash2,
  X,
} from "lucide-react";

import { api, type EventListItem } from "@/lib/api";
import { StatusBadge, money, cx } from "./ui";

export default function EventCard({
  event,
}: {
  event: EventListItem;
}) {
  const partial =
    event.cost_is_partial &&
    event.estimated_cost != null;

  const over =
    event.budget != null &&
    event.estimated_cost != null &&
    !event.cost_is_partial &&
    event.estimated_cost > event.budget;

  const [menuOpen, setMenuOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const [name, setName] = useState(event.name);
  const [guests, setGuests] = useState(
    String(event.guest_count)
  );
  const [budget, setBudget] = useState(
    event.budget != null ? String(event.budget) : ""
  );
  const [location, setLocation] = useState(
    event.location ?? ""
  );
  const [eventDate, setEventDate] = useState(
    event.event_date ?? ""
  );

  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  async function saveEdit() {
    const guestCount = Number(guests);
    const budgetValue =
      budget.trim() === "" ? null : Number(budget);

    if (!name.trim()) {
      setError("Event name is required.");
      return;
    }

    if (
      !Number.isFinite(guestCount) ||
      guestCount < 1
    ) {
      setError("Guest count must be at least 1.");
      return;
    }

    if (
      budgetValue !== null &&
      (!Number.isFinite(budgetValue) ||
        budgetValue < 0)
    ) {
      setError("Budget cannot be negative.");
      return;
    }

    setSaving(true);
    setError("");

    try {
      await api.updateEvent(event.id, {
        name: name.trim(),
        guest_count: guestCount,
        budget: budgetValue,
        location: location.trim() || null,
        event_date: eventDate || null,
      });

      window.location.reload();
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Could not update event."
      );
    } finally {
      setSaving(false);
    }
  }

  async function removeEvent() {
    setDeleting(true);
    setError("");

    try {
      await api.deleteEvent(event.id);
      window.location.reload();
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Could not delete event."
      );
      setDeleting(false);
    }
  }

  return (
    <>
      <div
        className={cx(
          "relative group bg-surface border border-line rounded-[12px]",
          "hh-interactive"
        )}
      >
        <Link
          href={`/events/${event.id}`}
          className="block px-4 py-3.5 pr-12"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <h3
                  dir="auto"
                  className="text-[14.5px] font-medium text-ink truncate max-w-full group-hover:text-accent transition-colors"
                >
                  {event.name}
                </h3>

                <StatusBadge status={event.status} />
              </div>

              <div className="mt-2 flex items-center gap-x-3.5 gap-y-1 flex-wrap text-[12.5px] text-ink-3">
                <Meta icon={Users}>
                  {event.guest_count} guests
                </Meta>

                <Meta icon={GlassWater}>
                  {event.menu_count}{" "}
                  {event.menu_count === 1
                    ? "cocktail"
                    : "cocktails"}
                </Meta>

                {event.budget != null && (
                  <Meta icon={Wallet}>
                    {money(event.budget)} budget
                  </Meta>
                )}

                {event.location && (
                  <Meta icon={MapPin}>
                    {event.location}
                  </Meta>
                )}

                {event.event_date && (
                  <Meta icon={CalendarDays}>
                    {event.event_date}
                  </Meta>
                )}
              </div>
            </div>

            <div className="shrink-0 flex items-center gap-2.5 pt-0.5">
              <div className="text-right">
                {event.estimated_cost != null ? (
                  <>
                    <div
                      className={cx(
                        "text-[16px] font-semibold tracking-[-.02em] tnum leading-none",
                        over ? "text-bad" : "text-ink"
                      )}
                    >
                      {money(event.estimated_cost)}
                    </div>

                    <div className="mt-1 text-[11px] text-ink-4 leading-none">
                      {partial ? (
                        <span className="inline-flex items-center gap-1 text-warn">
                          <AlertTriangle
                            size={10}
                            strokeWidth={2}
                          />
                          partial
                        </span>
                      ) : over ? (
                        "over budget"
                      ) : (
                        "estimated"
                      )}
                    </div>
                  </>
                ) : (
                  <div className="text-[12.5px] text-ink-4">
                    not costed
                  </div>
                )}
              </div>

              <ChevronRight
                size={16}
                strokeWidth={1.75}
                className="text-ink-4 group-hover:text-ink-2 group-hover:translate-x-0.5 transition-all"
              />
            </div>
          </div>
        </Link>

        <div className="absolute right-2 top-2 z-20">
          <button
            type="button"
            aria-label="Event actions"
            onClick={() => setMenuOpen((v) => !v)}
            className="h-8 w-8 inline-flex items-center justify-center rounded-lg text-ink-4 hover:text-ink hover:bg-canvas transition-colors"
          >
            <MoreHorizontal
              size={17}
              strokeWidth={1.8}
            />
          </button>

          {menuOpen && (
            <div className="absolute right-0 top-9 z-30 w-40 rounded-[10px] border border-line bg-surface p-1 shadow-lg">
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  setEditOpen(true);
                }}
                className="w-full flex items-center gap-2 rounded-md px-2.5 py-2 text-left text-[12.5px] text-ink-2 hover:bg-canvas hover:text-ink"
              >
                <Pencil size={13} />
                Edit event
              </button>

              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  setDeleteOpen(true);
                }}
                className="w-full flex items-center gap-2 rounded-md px-2.5 py-2 text-left text-[12.5px] text-bad hover:bg-bad/5"
              >
                <Trash2 size={13} />
                Delete event
              </button>
            </div>
          )}
        </div>
      </div>

      {editOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/25 px-4">
          <div className="w-full max-w-md rounded-[14px] border border-line bg-surface shadow-xl">
            <div className="flex items-center justify-between border-b border-line px-5 py-4">
              <div>
                <h2 className="text-[16px] font-semibold text-ink">
                  Edit event
                </h2>
                <p className="mt-0.5 text-[12px] text-ink-4">
                  Update the basic event details.
                </p>
              </div>

              <button
                type="button"
                onClick={() => {
                  setEditOpen(false);
                  setError("");
                }}
                className="h-8 w-8 inline-flex items-center justify-center rounded-lg text-ink-4 hover:bg-canvas"
              >
                <X size={16} />
              </button>
            </div>

            <div className="space-y-3 px-5 py-4">
              <Field label="Event name">
                <input
                  dir="auto"
                  value={name}
                  onChange={(e) =>
                    setName(e.target.value)
                  }
                  className="w-full rounded-lg border border-line bg-canvas px-3 py-2 text-[13px] text-ink outline-none focus:border-accent"
                />
              </Field>

              <div className="grid grid-cols-2 gap-3">
                <Field label="Guests">
                  <input
                    type="number"
                    min="1"
                    value={guests}
                    onChange={(e) =>
                      setGuests(e.target.value)
                    }
                    className="w-full rounded-lg border border-line bg-canvas px-3 py-2 text-[13px] text-ink outline-none focus:border-accent"
                  />
                </Field>

                <Field label="Budget">
                  <input
                    type="number"
                    min="0"
                    value={budget}
                    onChange={(e) =>
                      setBudget(e.target.value)
                    }
                    className="w-full rounded-lg border border-line bg-canvas px-3 py-2 text-[13px] text-ink outline-none focus:border-accent"
                  />
                </Field>
              </div>

              <Field label="Location">
                <input
                  dir="auto"
                  value={location}
                  onChange={(e) =>
                    setLocation(e.target.value)
                  }
                  className="w-full rounded-lg border border-line bg-canvas px-3 py-2 text-[13px] text-ink outline-none focus:border-accent"
                />
              </Field>

              <Field label="Event date">
                <input
                  type="date"
                  value={eventDate}
                  onChange={(e) =>
                    setEventDate(e.target.value)
                  }
                  className="w-full rounded-lg border border-line bg-canvas px-3 py-2 text-[13px] text-ink outline-none focus:border-accent"
                />
              </Field>

              {error && (
                <div className="rounded-lg bg-bad/5 px-3 py-2 text-[12px] text-bad">
                  {error}
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2 border-t border-line px-5 py-4">
              <button
                type="button"
                onClick={() => {
                  setEditOpen(false);
                  setError("");
                }}
                className="rounded-lg border border-line px-3.5 py-2 text-[12.5px] text-ink-2 hover:bg-canvas"
              >
                Cancel
              </button>

              <button
                type="button"
                disabled={saving}
                onClick={saveEdit}
                className="rounded-lg bg-accent px-3.5 py-2 text-[12.5px] font-medium text-white disabled:opacity-50"
              >
                {saving ? "Saving..." : "Save changes"}
              </button>
            </div>
          </div>
        </div>
      )}

      {deleteOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/25 px-4">
          <div className="w-full max-w-sm rounded-[14px] border border-line bg-surface shadow-xl">
            <div className="px-5 py-5">
              <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-full bg-bad/10 text-bad">
                <Trash2 size={16} />
              </div>

              <h2 className="text-[16px] font-semibold text-ink">
                Delete event?
              </h2>

              <p
                dir="auto"
                className="mt-2 text-[12.5px] leading-relaxed text-ink-3"
              >
                “{event.name}” will be permanently
                deleted, including its menu,
                calculations and event conversation.
              </p>

              {error && (
                <div className="mt-3 rounded-lg bg-bad/5 px-3 py-2 text-[12px] text-bad">
                  {error}
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2 border-t border-line px-5 py-4">
              <button
                type="button"
                disabled={deleting}
                onClick={() => {
                  setDeleteOpen(false);
                  setError("");
                }}
                className="rounded-lg border border-line px-3.5 py-2 text-[12.5px] text-ink-2 hover:bg-canvas"
              >
                Cancel
              </button>

              <button
                type="button"
                disabled={deleting}
                onClick={removeEvent}
                className="rounded-lg bg-bad px-3.5 py-2 text-[12.5px] font-medium text-white disabled:opacity-50"
              >
                {deleting
                  ? "Deleting..."
                  : "Delete event"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function Meta({
  icon: Icon,
  children,
}: {
  icon: typeof Users;
  children: React.ReactNode;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 min-w-0">
      <Icon
        size={12.5}
        strokeWidth={1.75}
        className="text-ink-4 shrink-0"
      />
      <span className="truncate">
        {children}
      </span>
    </span>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11.5px] font-medium text-ink-3">
        {label}
      </span>
      {children}
    </label>
  );
}
