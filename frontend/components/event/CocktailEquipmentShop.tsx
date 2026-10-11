"use client";

import {
  useEffect,
  useState,
} from "react";

import {
  Wrench,
  ExternalLink,
  AlertTriangle,
  ArrowRight,
  X,
  ShoppingBag,
} from "lucide-react";

import {
  getEquipmentShop,
  type EquipmentShop,
} from "@/lib/api";

import {
  Card,
  Note,
  money,
} from "@/components/ui";


export default function CocktailEquipmentShop({
  eventId,
}: {
  eventId: string;
}) {
  const [open, setOpen] = useState(false);

  const [data, setData] =
    useState<EquipmentShop | null>(null);

  const [loading, setLoading] =
    useState(false);

  const [error, setError] =
    useState<string | null>(null);


  // ----------------------------------------------------------
  // Load equipment only when the user actually opens the shop.
  // ----------------------------------------------------------

  useEffect(() => {
    if (!open || data || loading) {
      return;
    }

    let alive = true;

    setLoading(true);
    setError(null);

    getEquipmentShop(eventId)
      .then((result) => {
        if (!alive) return;

        setData(result);
        setLoading(false);
      })
      .catch((e) => {
        if (!alive) return;

        setError(
          e instanceof Error
            ? e.message
            : "Could not load equipment"
        );

        setLoading(false);
      });

    return () => {
      alive = false;
    };
  }, [
    open,
    data,
    loading,
    eventId,
  ]);


  // ----------------------------------------------------------
  // ESC closes drawer + prevent background scrolling.
  // ----------------------------------------------------------

  useEffect(() => {
    if (!open) return;

    const previous =
      document.body.style.overflow;

    document.body.style.overflow =
      "hidden";

    const onKeyDown = (
      event: KeyboardEvent
    ) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    window.addEventListener(
      "keydown",
      onKeyDown
    );

    return () => {
      document.body.style.overflow =
        previous;

      window.removeEventListener(
        "keydown",
        onKeyDown
      );
    };
  }, [open]);


  return (
    <>
      {/* ----------------------------------------------------
          COMPACT ENTRY CARD
      ---------------------------------------------------- */}

      <Card className="p-0 overflow-hidden">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="w-full px-5 py-4 flex items-center justify-between gap-4 text-start hover:bg-canvas transition-colors"
        >
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-full border border-line bg-white flex items-center justify-center shrink-0">
              <Wrench
                size={17}
                className="text-ink-2"
              />
            </div>

            <div className="min-w-0">
              <div className="text-[14px] font-medium text-ink">
                Need bar equipment for this event?
              </div>

              <div className="text-[12px] text-ink-3 mt-0.5">
                Shakers, jiggers, strainers,
                bar spoons, glassware and more.
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0 text-accent text-[12.5px] font-medium">
            Browse equipment
            <ArrowRight size={14} />
          </div>
        </button>
      </Card>


      {/* ----------------------------------------------------
          DRAWER
      ---------------------------------------------------- */}

      {open && (
        <div
          className="fixed inset-0 z-[100] bg-black/25 flex justify-end"
          onMouseDown={() =>
            setOpen(false)
          }
        >
          <aside
            role="dialog"
            aria-modal="true"
            aria-label="Cocktail equipment"
            onMouseDown={(event) =>
              event.stopPropagation()
            }
            className="h-full w-full max-w-[620px] bg-white shadow-2xl flex flex-col"
          >

            {/* HEADER */}

            <div className="px-5 py-4 border-b border-line flex items-start justify-between gap-4 shrink-0">
              <div>
                <div className="flex items-center gap-2">
                  <ShoppingBag
                    size={17}
                    className="text-accent"
                  />

                  <h2 className="text-[17px] font-semibold text-ink">
                    Cocktail equipment
                  </h2>
                </div>

                <p className="mt-1 text-[12px] text-ink-3">
                  Compare equipment prices and
                  buy directly from the store.
                </p>
              </div>

              <button
                type="button"
                onClick={() =>
                  setOpen(false)
                }
                aria-label="Close equipment"
                className="w-9 h-9 rounded-full border border-line flex items-center justify-center text-ink-3 hover:text-ink hover:bg-canvas"
              >
                <X size={17} />
              </button>
            </div>


            {/* CONTENT */}

            <div className="flex-1 overflow-y-auto p-5">

              {loading && (
                <div className="py-16 text-center">
                  <div className="text-[13px] text-ink-3">
                    Loading cocktail equipment…
                  </div>
                </div>
              )}


              {error && (
                <Note
                  tone="warn"
                  icon={AlertTriangle}
                >
                  {error}
                </Note>
              )}


              {!loading &&
                !error &&
                data &&
                data.groups.length === 0 && (
                  <Card className="p-4">
                    <p className="text-[13px] text-ink-3">
                      No equipment listings
                      available yet.
                    </p>
                  </Card>
                )}


              {!loading &&
                !error &&
                data &&
                data.groups.length > 0 && (
                  <div className="flex flex-col gap-4">

                    <div className="text-[11.5px] text-ink-4">
                      {data.total_categories} equipment categories
                    </div>

                    {data.groups.map(
                      (group) => (
                        <Card
                          key={group.key}
                          className="p-0 overflow-hidden"
                        >

                          {/* CATEGORY */}

                          <div className="px-4 py-3 border-b border-line bg-canvas/40">
                            <div className="flex items-center justify-between gap-3">
                              <h3 className="text-[14px] font-medium text-ink">
                                {group.name}
                              </h3>

                              <span className="text-[11px] text-ink-4">
                                {group.options.length}{" "}
                                {group.options.length === 1
                                  ? "option"
                                  : "options"}
                              </span>
                            </div>
                          </div>


                          {/* PRODUCTS */}

                          <div>
                            {group.options.map(
                              (
                                option,
                                index
                              ) => (
                                <div
                                  key={`${option.product_id}-${option.supplier}`}
                                  className="px-4 py-3 border-b border-line/70 last:border-0"
                                >
                                  <div className="flex items-center justify-between gap-4">

                                    <div className="min-w-0">

                                      <div
                                        dir="auto"
                                        className="text-[13px] font-medium text-ink"
                                      >
                                        {option.product}
                                      </div>

                                      <div className="mt-1 text-[11.5px] text-ink-3">
                                        {option.supplier}

                                        {" · "}

                                        {option.package_size}{" "}
                                        {option.package_unit}

                                        {!option.available && (
                                          <span className="text-warn">
                                            {" · "}
                                            Out of stock
                                          </span>
                                        )}
                                      </div>

                                    </div>


                                    <div className="flex items-center gap-3 shrink-0">

                                      <div className="text-end">

                                        {index === 0 &&
                                          option.available && (
                                            <div className="text-[10px] text-good">
                                              Best price
                                            </div>
                                          )}

                                        <div className="text-[15px] font-semibold text-ink tnum">
                                          {money(
                                            option.price
                                          )}
                                        </div>

                                      </div>


                                      {option.url && (
                                        <a
                                          href={
                                            option.url
                                          }
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          className="inline-flex items-center gap-1.5 rounded-full bg-accent px-3.5 py-2 text-[12px] font-medium text-white"
                                        >
                                          Buy

                                          <ExternalLink
                                            size={12}
                                          />
                                        </a>
                                      )}

                                    </div>

                                  </div>
                                </div>
                              )
                            )}
                          </div>

                        </Card>
                      )
                    )}

                  </div>
                )}

            </div>
          </aside>
        </div>
      )}
    </>
  );
}
