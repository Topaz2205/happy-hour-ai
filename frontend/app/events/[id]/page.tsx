"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  LayoutGrid, GlassWater, Calculator, ShoppingCart, Store, CircleDollarSign,
  Users, MapPin, Clock, Wallet, ArrowLeft, RefreshCw, Sparkles, AlertCircle,
  ChefHat,
} from "lucide-react";
import { useEventData } from "@/lib/useEventData";
import {
  OverviewSection, MenuSection, QuantitiesSection,
  ShoppingSection, SuppliersSection, CostsSection,
} from "@/components/event/sections";
import AgentSidePanel from "@/components/event/AgentSidePanel";
import MenuEditor from "@/components/event/MenuEditor";
import PrepSection from "@/components/event/PrepSection";
import ProductAlternatives from "@/components/event/ProductAlternatives";
import BuyCompareScreen from "@/components/event/BuyCompareScreen";
import {
  PageHeader, MetaItem, StatusBadge, Button, Note, Skeleton, money, cx,
} from "@/components/ui";

const TABS = [
  { key: "overview", label: "Overview", icon: LayoutGrid },
  { key: "menu", label: "Menu", icon: GlassWater },
  { key: "quantities", label: "Quantities", icon: Calculator },
  { key: "prep", label: "Prep", icon: ChefHat },
  { key: "shopping", label: "Buy & Compare", icon: ShoppingCart },
  { key: "costs", label: "Costs", icon: CircleDollarSign },
] as const;

export default function EventWorkspace() {
  const params = useParams<{ id: string }>();
  const id = params?.id ?? "";
  const [retailer, setRetailer] = useState<string | undefined>(undefined);
  const [tab, setTab] = useState<string>("overview");
  const [panelOpen, setPanelOpen] = useState(false);
  const [comparing, setComparing] = useState<string | null>(null);

  const data = useEventData(id, retailer);
  const { event, cost, plan, shopping, loading, error, calculate, calculating } = data;

  if (loading) {
    return (
      <main className="max-w-[1100px] mx-auto px-5 md:px-8 py-8">
        <Skeleton className="h-7 w-64 mb-3" />
        <Skeleton className="h-4 w-96 mb-8" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[104px]" />)}
        </div>
      </main>
    );
  }

  if (error || !event) {
    return (
      <main className="max-w-[700px] mx-auto px-5 md:px-8 py-16">
        <Note tone="warn" icon={AlertCircle}>{error ?? "Event not found."}</Note>
        <div className="mt-4">
          <Link href="/"><Button icon={ArrowLeft}>Back to home</Button></Link>
        </div>
      </main>
    );
  }

  return (
    <div className="flex min-h-screen">
      <main className="flex-1 min-w-0 max-w-[1100px] mx-auto px-5 md:px-8 py-8">
        <Link
          href="/events"
          className="inline-flex items-center gap-1.5 text-[13px] text-ink-3 hover:text-ink transition-colors mb-4"
        >
          <ArrowLeft size={14} strokeWidth={1.75} /> Events
        </Link>

        <PageHeader
          title={event.name}
          meta={
            <>
              <MetaItem icon={Users}>{event.guest_count} guests</MetaItem>
              {event.location && <MetaItem icon={MapPin}>{event.location}</MetaItem>}
              <MetaItem icon={Clock}>{event.duration_hours} hours</MetaItem>
              {event.budget != null && <MetaItem icon={Wallet}>{money(event.budget)} budget</MetaItem>}
              <StatusBadge status={event.status} />
            </>
          }
          actions={
            <>
              <Button
                icon={RefreshCw}
                onClick={calculate}
                disabled={calculating || event.menu.length === 0}
                title={event.menu.length === 0 ? "Add cocktails to the menu first" : undefined}
              >
                {calculating ? "Calculating…" : "Recalculate"}
              </Button>
              {/* The "Prep sheet" button lived here until the Prep tab existed.
                  Two controls called Prep in one header is one too many — the
                  tab owns this now, and Print lives inside it next to the
                  quantities it prints. */}
              <Button
                variant="primary"
                icon={Sparkles}
                onClick={() => setPanelOpen((o) => !o)}
                className="lg:hidden"
              >
                Agent
              </Button>
            </>
          }
        />

        <nav className="flex gap-0.5 border-b border-line mb-6 overflow-x-auto max-w-full">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={cx(
                "inline-flex items-center gap-1.5 px-3 h-9 text-[13.5px] whitespace-nowrap",
                "border-b-2 -mb-px transition-colors",
                tab === key
                  ? "border-accent text-ink font-medium"
                  : "border-transparent text-ink-3 hover:text-ink-2"
              )}
            >
              <Icon size={14} strokeWidth={tab === key ? 2 : 1.75} />
              {label}
            </button>
          ))}
        </nav>

        <div className="hh-rise" key={tab}>
          {tab === "overview" && (
            <OverviewSection
              event={event} cost={cost} plan={plan} shopping={shopping}
              onGoTo={setTab}
            />
          )}
          {tab === "menu" && <MenuEditor event={event} onSaved={data.reload} />}
          {tab === "quantities" && (
            <QuantitiesSection
              shopping={shopping}
              eventId={id}
              onCompare={setComparing}
            />
          )}
          {tab === "prep" && (
            <PrepSection event={event} eventId={id} onChanged={data.reload} />
          )}
          {tab === "shopping" && (
            <BuyCompareScreen eventId={id} />
          )}

          {tab === "suppliers" && (
            <div className="flex flex-col gap-7">
              {/* Kit is bought from a shop like everything else, so it belongs
                  on the tab about where things come from. */}
              <SuppliersSection plan={plan} />
            </div>
          )}
          {tab === "costs" && (
            <div className="flex flex-col gap-7">
              <CostsSection cost={cost} event={event} />
              {/* A workshop's kit is a real line in what the event costs, and
                  leaving it off this tab would understate the total. */}
            </div>
          )}
        </div>
      </main>

      <AgentSidePanel
        eventId={id}
        currentTab={tab}
        open={panelOpen}
        onOpenChange={setPanelOpen}
        onChanged={data.reload}
      />

      {comparing && (
        <ProductAlternatives
          eventId={id}
          ingredientId={comparing}
          onClose={() => setComparing(null)}
          onApplied={data.reload}
        />
      )}
    </div>
  );
}
