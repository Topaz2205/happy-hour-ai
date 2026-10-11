"use client";

import { useEffect, useState } from "react";
import { Settings as SettingsIcon, Link2, Percent } from "lucide-react";
import { api, type MappingCoverage } from "@/lib/api";
import Link from "next/link";
import { PageHeader, Card, SectionTitle, Button, Skeleton, MetricCard } from "@/components/ui";

export default function SettingsPage() {
  const [cov, setCov] = useState<MappingCoverage | null>(null);

  useEffect(() => {
    api.getMappingCoverage().then(setCov).catch(() => setCov(null));
  }, []);

  return (
    <main className="max-w-[760px] mx-auto px-5 md:px-8 py-8">
      <PageHeader
        title="Settings"
        subtitle="Defaults the calculator uses, and how complete your price data is."
      />

      <div className="flex flex-col gap-4">
        <div>
          <SectionTitle hint="How much of the catalogue can actually be costed">
            Data coverage
          </SectionTitle>
          {cov === null ? (
            <Skeleton className="h-[104px]" />
          ) : (
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
              <MetricCard
                label="Costable" icon={Percent} value={`${cov.coverage_pct}%`}
                hint={`${cov.mapped_and_priced} of ${cov.total_ingredients} ingredients`}
                tone={cov.coverage_pct > 90 ? "good" : "warn"}
              />
              <MetricCard label="Mapped" icon={Link2} value={cov.mapped} />
              <MetricCard
                label="Unmapped" icon={Link2} value={cov.unmapped}
                tone={cov.unmapped > 0 ? "warn" : "good"}
              />
            </div>
          )}
          <div className="mt-3">
            <Link href="/mappings"><Button icon={Link2}>Open mappings</Button></Link>
          </div>
        </div>

        <Card className="p-4">
          <SectionTitle hint="Applied to every calculation unless an event overrides them">
            Calculator defaults
          </SectionTitle>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 text-[13px]">
            <dt className="text-ink-3">Drinks per guest</dt><dd className="text-right tnum">2.5</dd>
            <dt className="text-ink-3">Non-alcoholic share</dt><dd className="text-right tnum">25%</dd>
            <dt className="text-ink-3">Waste buffer</dt><dd className="text-right tnum">8%</dd>
            <dt className="text-ink-3">VAT on new prices</dt><dd className="text-right tnum">18%</dd>
            <dt className="text-ink-3">VAT on imported prices</dt><dd className="text-right tnum">17%</dd>
          </dl>
          <p className="mt-3 text-[12.5px] text-ink-3 leading-relaxed">
            These live in <code className="text-[12px] bg-sunk px-1 py-0.5 rounded">backend/.env</code> and
            <code className="text-[12px] bg-sunk px-1 py-0.5 rounded ml-1">app/core/config.py</code>.
            Editing them here isn&apos;t wired up yet — changing a default silently would
            change the cost of every past event.
          </p>
        </Card>
      </div>
    </main>
  );
}
