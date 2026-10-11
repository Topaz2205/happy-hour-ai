"use client";

import { useEffect, useState } from "react";
import {
  Store,
  ExternalLink,
  ChefHat,
  ShoppingBasket,
} from "lucide-react";

import { getShopComparison } from "@/lib/api";


type CompareLine = {
  ingredient_id: string;
  ingredient: string;
  product: string;
  package_size: number;
  package_unit: string;
  price_per_package: number;
  packages: number;
  event_total: number;
  url?: string | null;
};


type CompareShop = {
  shop: string;
  website?: string | null;

  covers: number;
  of: number;

  missing: string[];

  subtotal: number;
  bottles: number;

  lines: CompareLine[];

  below_minimum?: boolean;
  delivery?: number | null;
  delivered_total?: number | null;
};


type OtherSupply = {
  ingredient_id: string;
  ingredient: string;

  category?: string | null;

  channel:
    | "house_made"
    | "juice_supplier"
    | "supermarket"
    | "supermarket_or_beverage_supplier"
    | "other";

  required_amount: number;
  unit?: string | null;

  packages_required?: number | null;
  package_size?: number | null;
  package_unit?: string | null;

  estimated_total?: number | null;

  product_url?: string | null;
};


type CompareResponse = {
  event_id: string;

  comparison_scope?: string | null;

  ingredients: number;

  shops: CompareShop[];

  other_supplies?: OtherSupply[];

  fully_covered_by_any_shop?: boolean;

  note?: string | null;
};


function money(
  value: number | null | undefined
) {
  if (value == null) {
    return "—";
  }

  return new Intl.NumberFormat(
    "he-IL",
    {
      style: "currency",
      currency: "ILS",
      maximumFractionDigits: 2,
    }
  ).format(value);
}


function quantity(
  amount: number,
  unit?: string | null
) {
  if (!unit) {
    return String(amount);
  }

  if (unit === "ml" && amount >= 1000) {
    const litres = amount / 1000;

    return `${litres.toFixed(
      litres % 1 === 0 ? 0 : 2
    )} L`;
  }

  return `${amount} ${unit}`;
}


function channelLabel(
  channel: OtherSupply["channel"]
) {
  switch (channel) {
    case "house_made":
      return "Make in-house";

    case "juice_supplier":
      return "Juice supplier";

    case "supermarket":
      return "Supermarket";

    case "supermarket_or_beverage_supplier":
      return "Supermarket / beverage store";

    default:
      return "Other supply";
  }
}


function channelDescription(
  channel: OtherSupply["channel"]
) {
  switch (channel) {
    case "house_made":
      return "Prepare during event prep";

    case "juice_supplier":
      return "Order separately from the juice supplier";

    case "supermarket":
      return "Buy with the general grocery order";

    case "supermarket_or_beverage_supplier":
      return "Buy from a supermarket or beverage supplier";

    default:
      return "Source separately";
  }
}


export default function ShopComparison({
  eventId,
}: {
  eventId: string;
}) {
  const [data, setData] =
    useState<CompareResponse | null>(null);

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState<string | null>(null);


  useEffect(() => {
    let cancelled = false;

    setLoading(true);
    setError(null);

    getShopComparison(eventId)
      .then((response) => {
        if (cancelled) {
          return;
        }

        setData(
          response as unknown as CompareResponse
        );
      })
      .catch((err: unknown) => {
        if (cancelled) {
          return;
        }

        setError(
          err instanceof Error
            ? err.message
            : "Could not load shop comparison."
        );
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [eventId]);


  if (loading) {
    return (
      <div className="rounded-xl border border-line bg-surface p-6">
        <div className="text-[13px] text-ink-3">
          Comparing alcohol prices…
        </div>
      </div>
    );
  }


  if (error) {
    return (
      <div className="rounded-xl border border-line bg-surface p-6">

        <div className="font-medium text-ink">
          Could not load supplier comparison
        </div>

        <div className="mt-1 text-[12px] text-ink-4">
          {error}
        </div>

      </div>
    );
  }


  if (!data) {
    return null;
  }


  const otherSupplies =
    data.other_supplies ?? [];


  return (
    <div className="flex flex-col gap-7">

      {/* ==================================================
          ALCOHOL STORE COMPARISON
      ================================================== */}

      <section className="flex flex-col gap-4">

        <div className="flex items-end justify-between gap-4">

          <div>

            <div className="text-[10.5px] font-semibold uppercase tracking-[0.12em] text-ink-4">
              Alcohol
            </div>

            <h2 className="mt-1 text-[20px] font-semibold text-ink">
              Store price comparison
            </h2>

            <p className="mt-1 max-w-[650px] text-[12.5px] leading-5 text-ink-4">
              Compare only the alcohol needed for this event.
              Syrups, juice, garnish and supermarket items are
              handled separately below.
            </p>

          </div>


          <div className="shrink-0 text-right">

            <div className="text-[23px] font-semibold tabular-nums text-ink">
              {data.ingredients}
            </div>

            <div className="text-[11px] text-ink-4">
              alcohol item
              {data.ingredients === 1 ? "" : "s"}
            </div>

          </div>

        </div>


        {data.comparison_scope !==
          "alcohol_only" && (

          <div className="rounded-xl border border-line bg-sunk px-4 py-3 text-[12px] text-ink-3">
            The backend is not currently returning
            alcohol-only comparison data.
          </div>

        )}


        {data.shops.length === 0 ? (

          <div className="rounded-xl border border-line bg-surface p-5">

            <div className="text-[13.5px] font-medium text-ink">
              No current alcohol prices found
            </div>

            <div className="mt-1 text-[12px] text-ink-4">
              There are no usable retail listings for the
              alcohol in this event yet.
            </div>

          </div>

        ) : (

          data.shops.map(
            (shop, index) => (

              <div
                key={shop.shop}
                className="overflow-hidden rounded-xl border border-line bg-surface"
              >

                {/* Store header */}

                <div className="flex items-center justify-between gap-4 border-b border-line bg-sunk px-4 py-3.5">

                  <div className="flex min-w-0 items-center gap-3">

                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-line bg-surface">

                      <Store
                        size={16}
                        className="text-ink-3"
                      />

                    </div>


                    <div className="min-w-0">

                      <div className="flex items-center gap-2">

                        <div className="truncate text-[14px] font-semibold text-ink">
                          {shop.shop}
                        </div>


                        {index === 0 && (
                          <span className="rounded-md border border-accent-line bg-accent-soft px-2 py-0.5 text-[10px] font-medium text-accent-hi">
                            Best option
                          </span>
                        )}

                      </div>


                      <div className="mt-0.5 text-[11.5px] text-ink-4">

                        Covers{" "}

                        <span className="font-medium text-ink-3">
                          {shop.covers}/{shop.of}
                        </span>

                        {" · "}

                        {shop.bottles} bottle
                        {shop.bottles === 1
                          ? ""
                          : "s"}

                      </div>

                    </div>

                  </div>


                  <div className="shrink-0 text-right">

                    <div className="text-[17px] font-semibold tabular-nums text-ink">
                      {money(shop.subtotal)}
                    </div>

                    <div className="text-[10.5px] text-ink-4">
                      product subtotal
                    </div>

                  </div>

                </div>


                {/* Products */}

                <div className="divide-y divide-line">

                  {shop.lines.map((line) => (

                    <div
                      key={`${shop.shop}-${line.ingredient_id}-${line.product}`}
                      className="flex items-center gap-3 px-4 py-3"
                    >

                      <div className="min-w-0 flex-1">

                        <div className="text-[13.5px] font-medium text-ink">
                          {line.ingredient}
                        </div>

                        <div className="mt-0.5 truncate text-[11.5px] text-ink-4">

                          {line.product}

                          {" · "}

                          {line.packages} ×{" "}
                          {line.package_size}
                          {line.package_unit}

                          {" · "}

                          {money(
                            line.price_per_package
                          )}
                          /bottle

                        </div>

                      </div>


                      <div className="shrink-0 text-[13px] font-semibold tabular-nums text-ink-2">
                        {money(
                          line.event_total
                        )}
                      </div>


                      {line.url && (

                        <a
                          href={line.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg border border-line px-2.5 text-[11.5px] font-medium text-ink-2 transition hover:border-line-2"
                        >

                          Buy

                          <ExternalLink
                            size={11}
                          />

                        </a>

                      )}

                    </div>

                  ))}

                </div>


                {shop.missing.length >
                  0 && (

                  <div className="border-t border-line bg-sunk px-4 py-2.5 text-[11.5px] text-ink-4">

                    Missing:{" "}

                    {shop.missing.join(
                      ", "
                    )}

                  </div>

                )}


                {shop.website && (

                  <div className="border-t border-line px-4 py-2.5 text-right">

                    <a
                      href={shop.website}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[11.5px] font-medium text-accent-hi hover:underline"
                    >

                      Open store

                      <ExternalLink
                        size={11}
                      />

                    </a>

                  </div>

                )}

              </div>

            )
          )

        )}

      </section>


      {/* ==================================================
          NON-ALCOHOL
      ================================================== */}

      {otherSupplies.length > 0 && (

        <section className="flex flex-col gap-4">

          <div>

            <div className="text-[10.5px] font-semibold uppercase tracking-[0.12em] text-ink-4">
              Other supplies
            </div>

            <h2 className="mt-1 text-[20px] font-semibold text-ink">
              Prep & supermarket
            </h2>

            <p className="mt-1 text-[12.5px] leading-5 text-ink-4">
              These ingredients are still part of the event,
              but they do not belong in the alcohol-store
              comparison.
            </p>

          </div>


          <div className="overflow-hidden rounded-xl border border-line bg-surface">

            <div className="divide-y divide-line">

              {otherSupplies.map(
                (item: OtherSupply) => {

                  const houseMade =
                    item.channel ===
                    "house_made";

                  return (

                    <div
                      key={item.ingredient_id}
                      className="flex items-center gap-3 px-4 py-3.5"
                    >

                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-line bg-sunk">

                        {houseMade ? (

                          <ChefHat
                            size={16}
                            className="text-ink-3"
                          />

                        ) : (

                          <ShoppingBasket
                            size={16}
                            className="text-ink-3"
                          />

                        )}

                      </div>


                      <div className="min-w-0 flex-1">

                        <div className="text-[13.5px] font-medium text-ink">
                          {item.ingredient}
                        </div>


                        <div className="mt-0.5 text-[11.5px] text-ink-4">

                          {quantity(
                            item.required_amount,
                            item.unit
                          )}

                          {" · "}

                          {channelDescription(
                            item.channel
                          )}

                        </div>

                      </div>


                      <span className="shrink-0 rounded-lg border border-line bg-sunk px-2.5 py-1.5 text-[11px] font-medium text-ink-3">
                        {channelLabel(
                          item.channel
                        )}
                      </span>


                      {item.estimated_total !=
                        null && (

                        <div className="w-[75px] shrink-0 text-right text-[12.5px] font-medium tabular-nums text-ink-2">
                          {money(
                            item.estimated_total
                          )}
                        </div>

                      )}


                      {item.product_url &&
                        !houseMade && (

                        <a
                          href={
                            item.product_url
                          }
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex h-8 shrink-0 items-center gap-1 rounded-lg border border-line px-2.5 text-[11.5px] font-medium text-ink-2"
                        >

                          Open

                          <ExternalLink
                            size={11}
                          />

                        </a>

                      )}

                    </div>

                  );
                }
              )}

            </div>

          </div>

        </section>

      )}

    </div>
  );
}
