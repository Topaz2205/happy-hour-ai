"use client";

import { useEffect, useState } from "react";
import { Store, ExternalLink, Package } from "lucide-react";
import { api } from "@/lib/api";
import { PageHeader, Card, EmptyState, Skeleton, money, cx } from "@/components/ui";

type Supplier = { id: string; name: string; website?: string | null };
type Product = {
  product_name: string;
  ingredient_name?: string | null;
  package_size?: number | null;
  package_unit?: string | null;
  price_after_vat?: number | null;
  vat_rate?: number | null;
  is_historical?: boolean | null;
  product_url?: string | null;
};

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<Supplier[] | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const [products, setProducts] = useState<Product[] | null>(null);

  useEffect(() => {
    api.getSuppliers()
      .then((r) => {
        setSuppliers(r.suppliers);
        if (r.suppliers.length) setActive(r.suppliers[0].id);
      })
      .catch(() => setSuppliers([]));
  }, []);

  useEffect(() => {
    if (!active) return;
    setProducts(null);
    fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/suppliers/${active}/products`)
      .then((r) => r.json())
      .then((d) => setProducts(d.products ?? d.items ?? []))
      .catch(() => setProducts([]));
  }, [active]);

  return (
    <main className="max-w-[1100px] mx-auto px-5 md:px-8 py-8">
      <PageHeader
        title="Suppliers"
        subtitle="Where prices come from. Each listing records the VAT rate it was captured at."
      />

      {suppliers === null ? (
        <Skeleton className="h-9 w-full max-w-[520px] mb-5" />
      ) : suppliers.length === 0 ? (
        <Card><EmptyState icon={Store} title="No suppliers yet." /></Card>
      ) : (
        <>
          <div className="flex flex-wrap gap-1.5 mb-5">
            {suppliers.map((s) => (
              <button
                key={s.id}
                onClick={() => setActive(s.id)}
                className={cx(
                  "h-8 px-3 rounded-lg border text-[13px] transition-colors",
                  active === s.id
                    ? "bg-ink text-white border-ink"
                    : "bg-surface border-line text-ink-2 hover:border-line-2"
                )}
              >
                {s.name}
              </button>
            ))}
          </div>

          <Card className="overflow-hidden">
            {products === null ? (
              <div className="p-4 flex flex-col gap-2">
                {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-8" />)}
              </div>
            ) : products.length === 0 ? (
              <EmptyState icon={Package} title="No products for this supplier." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-[13px] min-w-[560px]">
                  <thead>
                    <tr className="bg-sunk border-b border-line text-ink-3">
                      <th className="px-3 py-2 text-left font-medium text-[11.5px] uppercase tracking-[.05em]">Product</th>
                      <th className="px-3 py-2 text-right font-medium text-[11.5px] uppercase tracking-[.05em]">Pack</th>
                      <th className="px-3 py-2 text-right font-medium text-[11.5px] uppercase tracking-[.05em]">Price</th>
                      <th className="px-3 py-2 text-right font-medium text-[11.5px] uppercase tracking-[.05em]">VAT</th>
                      <th className="px-3 py-2" />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {products.map((p, i) => (
                      <tr key={i} className="hover:bg-raised">
                        <td className="px-3 py-2.5">
                          <div className="text-ink" dir="auto">{p.product_name}</div>
                          {p.ingredient_name && p.ingredient_name !== p.product_name && (
                            <div className="text-[12px] text-ink-4">{p.ingredient_name}</div>
                          )}
                        </td>
                        <td className="px-3 py-2.5 text-right tnum text-ink-3">
                          {p.package_size ? `${p.package_size.toLocaleString()}${p.package_unit ?? ""}` : "—"}
                        </td>
                        <td className="px-3 py-2.5 text-right tnum text-ink">{money(p.price_after_vat)}</td>
                        <td className="px-3 py-2.5 text-right tnum text-ink-4">
                          {p.vat_rate != null ? `${Math.round(p.vat_rate * 100)}%` : "—"}
                          {p.is_historical && <span className="ml-1 text-[11px]">hist.</span>}
                        </td>
                        <td className="px-3 py-2.5 text-right">
                          {p.product_url && (
                            <a href={p.product_url} target="_blank" rel="noopener noreferrer"
                               className="inline-flex items-center gap-1 text-[12.5px] text-accent-hi hover:underline">
                              Open <ExternalLink size={11} strokeWidth={2} />
                            </a>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </main>
  );
}
