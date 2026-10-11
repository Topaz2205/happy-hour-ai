"use client";

import { useEffect, useState } from "react";
import {
  ChevronDown,
  ExternalLink,
  Store,
  Wrench,
  X,
  ShoppingBasket,
  ChefHat,
} from "lucide-react";

import {
  getShopComparison,
  getEquipmentShop,
} from "@/lib/api";


type ShopLine = {
  ingredient_id?: string;
  ingredient: string;
  product: string;
  package_size: number;
  package_unit: string;
  price_per_package: number;
  packages: number;
  event_total: number;
  url?: string | null;
};

type Shop = {
  shop: string;
  website?: string | null;
  covers: number;
  of: number;
  bottles?: number;
  subtotal: number;
  missing?: string[];
  lines: ShopLine[];
};

type OtherSupply = {
  ingredient?: string;
  name?: string;
  channel?: string;
  required_amount?: number | null;
  amount?: number | null;
  unit?: string | null;
  cost?: number | null;
  total_price?: number | null;
  url?: string | null;
  product_url?: string | null;
  note?: string | null;
};

type Comparison = {
  ingredients: number;
  shops: Shop[];
  other_supplies?: OtherSupply[];
};

type EquipmentOption = {
  product_id: string;
  product: string;
  supplier: string;
  price: number;
  package_size: number;
  package_unit: string;
  available: boolean;
  url?: string | null;
};

type EquipmentGroup = {
  key: string;
  name: string;
  options: EquipmentOption[];
};

type EquipmentData = {
  groups: EquipmentGroup[];
  total_categories: number;
};


function money(value?: number | null) {
  if (value == null) return "—";

  return new Intl.NumberFormat("he-IL", {
    style: "currency",
    currency: "ILS",
    maximumFractionDigits: 2,
  }).format(value);
}


function channelLabel(channel?: string) {
  if (channel === "house_made") return "Make in-house";
  if (channel === "juice_supplier") return "Juice supplier";
  if (channel === "supermarket") return "Supermarket";
  if (channel === "beverage_supplier") return "Beverage store";

  return channel?.replaceAll("_", " ") ?? "Other";
}


export default function BuyCompareScreen({
  eventId,
}: {
  eventId: string;
}) {
  const [comparison, setComparison] =
    useState<Comparison | null>(null);

  const [equipment, setEquipment] =
    useState<EquipmentData | null>(null);

  const [equipmentOpen, setEquipmentOpen] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);


  // Load BOTH once.
  // Equipment is ready before the user opens the drawer.
  useEffect(() => {
    let alive = true;

    setError(null);

    Promise.all([
      getShopComparison(eventId),
      getEquipmentShop(eventId),
    ])
      .then(([shops, gear]) => {
        if (!alive) return;

        setComparison(
          shops as unknown as Comparison
        );

        setEquipment(
          gear as unknown as EquipmentData
        );
      })
      .catch((e) => {
        if (!alive) return;

        setError(
          e instanceof Error
            ? e.message
            : "Could not load buying data"
        );
      });

    return () => {
      alive = false;
    };
  }, [eventId]);


  // ESC closes equipment.
  useEffect(() => {
    if (!equipmentOpen) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setEquipmentOpen(false);
      }
    };

    window.addEventListener(
      "keydown",
      onKeyDown
    );

    return () =>
      window.removeEventListener(
        "keydown",
        onKeyDown
      );
  }, [equipmentOpen]);


  if (error) {
    return (
      <div className="rounded-xl border border-orange-200 bg-orange-50 px-4 py-3 text-[13px]">
        Could not load Buy & Compare: {error}
      </div>
    );
  }


  if (!comparison) {
    return (
      <div className="rounded-xl border border-line px-4 py-5 text-[13px] text-ink-3">
        Loading Buy & Compare…
      </div>
    );
  }


  const shops = comparison.shops ?? [];
  const other = comparison.other_supplies ?? [];
  const best = shops[0];


  return (
    <div className="flex flex-col gap-5">

      {/* ==================================================
          EQUIPMENT — ALWAYS FIRST
      ================================================== */}

      <button
        type="button"
        onClick={() => setEquipmentOpen(true)}
        className="w-full rounded-xl border border-line bg-white px-5 py-4 flex items-center justify-between gap-4 text-start hover:bg-canvas transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full border border-line flex items-center justify-center">
            <Wrench
              size={17}
              className="text-ink-2"
            />
          </div>

          <div>
            <div className="text-[14px] font-medium text-ink">
              Need bar equipment for this event?
            </div>

            <div className="text-[12px] text-ink-3 mt-0.5">
              Shakers, jiggers, strainers,
              bar spoons, glassware and more.
            </div>
          </div>
        </div>

        <div className="text-[12.5px] font-medium text-accent">
          Browse equipment →
        </div>
      </button>


      {/* ==================================================
          ALCOHOL HEADER
      ================================================== */}

      <section>
        <div className="flex items-end justify-between gap-4 mb-3">
          <div>
            <div className="text-[10.5px] uppercase tracking-[.12em] text-ink-4">
              Alcohol
            </div>

            <h2 className="text-[20px] font-semibold text-ink mt-1">
              Store price comparison
            </h2>

            <p className="text-[12px] text-ink-3 mt-1">
              All stores are collapsed. Open one
              only when you want to inspect its products.
            </p>
          </div>

          <div className="text-end">
            <div className="text-[22px] font-semibold text-ink">
              {comparison.ingredients}
            </div>

            <div className="text-[11px] text-ink-4">
              alcohol items
            </div>
          </div>
        </div>


        {/* BEST SHOP */}

        {best && (
          <div className="mb-3 rounded-xl border border-orange-200 bg-orange-50/60 px-4 py-3 flex items-center justify-between">
            <div>
              <div className="text-[10px] uppercase tracking-[.08em] text-orange-700">
                Best option
              </div>

              <div className="text-[14px] font-medium text-ink">
                {best.shop}
              </div>

              <div className="text-[11px] text-ink-3">
                Covers {best.covers}/{best.of}
                {best.bottles != null
                  ? ` · ${best.bottles} bottles`
                  : ""}
              </div>
            </div>

            <div className="text-[17px] font-semibold text-ink">
              {money(best.subtotal)}
            </div>
          </div>
        )}


        {/* ==================================================
            STORE ACCORDIONS
        ================================================== */}

        <div className="rounded-xl border border-line overflow-hidden bg-white">

          {shops.map((shop, index) => (
            <details
              key={shop.shop}
              className="group border-b border-line last:border-0"
            >
              <summary className="list-none cursor-pointer px-4 py-3 flex items-center justify-between gap-4 hover:bg-canvas/60">

                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-full border border-line flex items-center justify-center">
                    <Store
                      size={15}
                      className="text-ink-3"
                    />
                  </div>

                  <div>
                    <div className="flex items-center gap-2">
                      <span
                        dir="auto"
                        className="text-[13.5px] font-medium text-ink"
                      >
                        {shop.shop}
                      </span>

                      {index === 0 && (
                        <span className="rounded-md border border-orange-200 bg-orange-50 px-2 py-0.5 text-[10px] text-orange-700">
                          Best
                        </span>
                      )}
                    </div>

                    <div className="text-[11px] text-ink-4">
                      Covers {shop.covers}/{shop.of}

                      {shop.bottles != null &&
                        ` · ${shop.bottles} bottles`}

                      {shop.missing?.length
                        ? ` · ${shop.missing.length} missing`
                        : ""}
                    </div>
                  </div>
                </div>


                <div className="flex items-center gap-4">
                  <div className="text-end">
                    <div className="text-[15px] font-semibold text-ink">
                      {money(shop.subtotal)}
                    </div>

                    <div className="text-[10px] text-ink-4">
                      subtotal
                    </div>
                  </div>

                  <ChevronDown
                    size={17}
                    className="text-ink-3 group-open:rotate-180 transition-transform"
                  />
                </div>

              </summary>


              {/* PRODUCTS */}

              <div className="border-t border-line bg-canvas/30">

                {shop.lines.map(
                  (line, lineIndex) => (
                    <div
                      key={`${shop.shop}-${line.ingredient_id ?? lineIndex}`}
                      className="px-4 py-2.5 border-b border-line/70 last:border-0 flex items-center justify-between gap-4"
                    >
                      <div>
                        <div
                          dir="auto"
                          className="text-[12.5px] font-medium text-ink"
                        >
                          {line.ingredient}
                        </div>

                        <div
                          dir="auto"
                          className="text-[10.5px] text-ink-4 mt-0.5"
                        >
                          {line.product}
                          {" · "}
                          {line.packages} ×{" "}
                          {line.package_size}
                          {line.package_unit}
                          {" · "}
                          {money(
                            line.price_per_package
                          )}
                          /pack
                        </div>
                      </div>


                      <div className="flex items-center gap-3">
                        <span className="text-[12px] font-medium text-ink">
                          {money(
                            line.event_total
                          )}
                        </span>

                        {line.url && (
                          <a
                            href={line.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="rounded-full border border-line bg-white px-3 py-1.5 text-[11px]"
                          >
                            Buy ↗
                          </a>
                        )}
                      </div>
                    </div>
                  )
                )}


                {shop.website && (
                  <div className="px-4 py-2.5 flex justify-end">
                    <a
                      href={shop.website}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[11px] text-accent"
                    >
                      Open store ↗
                    </a>
                  </div>
                )}

              </div>
            </details>
          ))}

        </div>
      </section>


      {/* ==================================================
          OTHER SUPPLIES — COLLAPSED
      ================================================== */}

      {other.length > 0 && (
        <details className="group rounded-xl border border-line bg-white overflow-hidden">

          <summary className="list-none cursor-pointer px-4 py-3 flex items-center justify-between hover:bg-canvas/60">

            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-full border border-line flex items-center justify-center">
                <ShoppingBasket
                  size={15}
                  className="text-ink-3"
                />
              </div>

              <div>
                <div className="text-[10px] uppercase tracking-[.08em] text-ink-4">
                  Other supplies
                </div>

                <div className="text-[13.5px] font-medium text-ink">
                  Prep & supermarket
                </div>

                <div className="text-[11px] text-ink-4">
                  {other.length} items
                </div>
              </div>
            </div>

            <ChevronDown
              size={17}
              className="text-ink-3 group-open:rotate-180 transition-transform"
            />

          </summary>


          <div className="border-t border-line">

            {other.map((item, index) => {
              const name =
                item.ingredient ??
                item.name ??
                "Supply";

              const cost =
                item.cost ??
                item.total_price;

              const url =
                item.url ??
                item.product_url;

              const isHouse =
                item.channel === "house_made";

              return (
                <div
                  key={`${name}-${index}`}
                  className="px-4 py-2.5 border-b border-line last:border-0 flex items-center justify-between gap-4"
                >

                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full border border-line flex items-center justify-center">
                      {isHouse ? (
                        <ChefHat size={13} />
                      ) : (
                        <ShoppingBasket size={13} />
                      )}
                    </div>

                    <div>
                      <div
                        dir="auto"
                        className="text-[12.5px] font-medium text-ink"
                      >
                        {name}
                      </div>

                      <div className="text-[10.5px] text-ink-4">
                        {channelLabel(
                          item.channel
                        )}
                      </div>
                    </div>
                  </div>


                  <div className="flex items-center gap-3">

                    {cost != null && (
                      <span className="text-[12px] font-medium">
                        {money(cost)}
                      </span>
                    )}

                    {url && (
                      <a
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="rounded-full border border-line px-3 py-1.5 text-[11px]"
                      >
                        Open ↗
                      </a>
                    )}

                  </div>
                </div>
              );
            })}

          </div>
        </details>
      )}


      {/* ==================================================
          EQUIPMENT DRAWER
      ================================================== */}

      {equipmentOpen && (
        <div
          className="fixed inset-0 z-[100] bg-black/25 flex justify-end"
          onClick={() =>
            setEquipmentOpen(false)
          }
        >
          <aside
            className="w-full max-w-[620px] h-full bg-white shadow-2xl flex flex-col"
            onClick={(e) =>
              e.stopPropagation()
            }
          >

            <div className="px-5 py-4 border-b border-line flex items-center justify-between">
              <div>
                <h2 className="text-[17px] font-semibold text-ink">
                  Cocktail equipment
                </h2>

                <p className="text-[12px] text-ink-3">
                  Compare equipment and buy
                  directly from the store.
                </p>
              </div>

              <button
                type="button"
                onClick={() =>
                  setEquipmentOpen(false)
                }
                className="w-9 h-9 rounded-full border border-line flex items-center justify-center"
              >
                <X size={17} />
              </button>
            </div>


            <div className="flex-1 overflow-y-auto p-5">

              {!equipment ? (
                <div className="text-[13px] text-ink-3">
                  Loading equipment…
                </div>
              ) : equipment.groups.length === 0 ? (
                <div className="text-[13px] text-ink-3">
                  No equipment listings available.
                </div>
              ) : (
                <div className="flex flex-col gap-3">

                  {equipment.groups.map(
                    (group) => (
                      <details
                        key={group.key}
                        className="group rounded-xl border border-line overflow-hidden"
                      >

                        <summary className="list-none cursor-pointer px-4 py-3 flex items-center justify-between">
                          <div>
                            <div className="text-[13.5px] font-medium text-ink">
                              {group.name}
                            </div>

                            <div className="text-[10.5px] text-ink-4">
                              {group.options.length} options
                            </div>
                          </div>

                          <ChevronDown
                            size={16}
                            className="group-open:rotate-180 transition-transform"
                          />
                        </summary>


                        <div className="border-t border-line">

                          {group.options.map(
                            (option, index) => (
                              <div
                                key={`${option.product_id}-${option.supplier}`}
                                className="px-4 py-3 border-b border-line last:border-0 flex items-center justify-between gap-4"
                              >

                                <div>
                                  <div
                                    dir="auto"
                                    className="text-[12.5px] font-medium text-ink"
                                  >
                                    {option.product}
                                  </div>

                                  <div className="text-[10.5px] text-ink-4">
                                    {option.supplier}
                                    {" · "}
                                    {option.package_size}{" "}
                                    {option.package_unit}
                                  </div>
                                </div>


                                <div className="flex items-center gap-3">

                                  <div className="text-end">
                                    {index === 0 && (
                                      <div className="text-[9.5px] text-green-600">
                                        Best price
                                      </div>
                                    )}

                                    <div className="text-[13px] font-semibold">
                                      {money(
                                        option.price
                                      )}
                                    </div>
                                  </div>

                                  {option.url && (
                                    <a
                                      href={option.url}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="rounded-full bg-accent text-white px-3 py-1.5 text-[11px]"
                                    >
                                      Buy ↗
                                    </a>
                                  )}

                                </div>

                              </div>
                            )
                          )}

                        </div>
                      </details>
                    )
                  )}

                </div>
              )}

            </div>

          </aside>
        </div>
      )}

    </div>
  );
}
