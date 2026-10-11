/**
 * Happy Hour AI — API Client
 * All data fetching goes through these typed functions.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  let res: Response;

  try {
    res = await fetch(`${API_URL}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch {
    // fetch() only rejects on a transport-level failure — the API process is
    // down, or the browser blocked the response. Browsers word this uselessly
    // ("Load failed" in Safari, "Failed to fetch" in Chrome), so say what it
    // actually means and what to do about it.
    throw new Error(
      `Can't reach the API at ${API_URL}. Make sure the backend terminal is ` +
        `still running: cd backend && source venv/bin/activate && ` +
        `uvicorn app.main:app --reload --port 8000`
    );
  }

  if (!res.ok) {
    const err = await res.json().catch(() => null);
    const detail =
      (err && (err.detail || err.message)) || `${res.status} ${res.statusText}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  // 204 and friends carry no body
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Types ──────────────────────────────────────────────────────────────────

export interface Cocktail {
  // Names only, in recipe order, from the list endpoint — so a picker can say
  // what a drink actually is. Distinct from CocktailDetail.ingredients, which
  // is the measured recipe.
  ingredient_names?: string[];
  id: string;
  name: string;
  description?: string;
  alcoholic: boolean;
  theme?: string;
  complexity?: string;
  glass_type?: string;
  technique?: string;
  active: boolean;
}

export interface CocktailDetail extends Cocktail {
  garnish?: string;
  comments?: string;
  non_alc_variant?: string;
  ingredients: IngredientLine[];
}

export interface IngredientLine {
  ingredient_id: string;
  canonical_name: string;
  category: string;
  amount?: number;
  unit: string;
  alcoholic: boolean;
  optional: boolean;
}

export interface Event {
  is_workshop?: boolean;
  people_per_station?: number;
  id: string;
  name: string;
  event_date?: string;
  location?: string;
  guest_count: number;
  budget: number;
  duration_hours: number;
  expected_drinks_per_guest: number;
  non_alcoholic_pct: number;
  waste_buffer_pct: number;
  theme?: string;
  status: string;
  ai_request?: string;
  menu: EventMenuItem[];
}

export interface EventMenuItem {
  cocktail_id: string;
  cocktail_name?: string;
  allocation_pct: number;
  expected_servings?: number;
  ai_rationale?: string;
}

export interface PurchaseItem {
  ingredient_id: string;
  product_id?: string | null;
  ingredient_name: string;
  product_name?: string;
  required_amount: number;
  unit: string;
  packages_required?: number;
  package_size?: number;
  package_unit?: string;
  unit_price?: number;
  total_price?: number;
  status: string;
  supplier_name?: string;
  product_url?: string;
}

export interface ShoppingList {
  event_id: string;
  items: PurchaseItem[];
  total_cost: number;
  has_missing_data: boolean;
}

export interface CostSummary {
  event_id: string;
  guest_count: number;
  budget?: number;
  total_cost: number;
  cost_per_guest?: number;
  budget_variance?: number;
  budget_status?: string;
  items_with_data: number;
  items_missing_data: number;
  cost_by_category: Record<string, number>;
  is_partial: boolean;
}

// ── Purchase plan (shopping list grouped by store) ─────────────────────────

export type LinkKind = "DIRECT" | "SEARCH" | "HOMEPAGE" | "NONE";

export interface PurchaseLinkInfo {
  kind: LinkKind;
  url?: string | null;
  retailer_key?: string | null;
  retailer_name?: string | null;
  query_term?: string | null;
  note?: string | null;
}

export interface PurchasePlanItem {
  ingredient_name: string;
  product_name?: string | null;
  order_line: string;
  packages_required: number;
  package_size?: number | null;
  package_unit?: string | null;
  required_amount?: number | null;
  unit?: string | null;
  unit_price?: number | null;
  total_price?: number | null;
  purchase_link: PurchaseLinkInfo;
}

export interface PurchasePlanGroup {
  group_key: string;
  store_name: string;
  store_website?: string | null;
  items: PurchasePlanItem[];
  subtotal: number;
  item_count: number;
}

export interface BlockedItem {
  ingredient_name: string;
  product_name?: string | null;
  required_amount?: number | null;
  unit?: string | null;
  status: string;
  reason: string;
}

export interface PurchasePlan {
  event_id: string;
  retailer: {
    key: string;
    name: string;
    website: string;
    search_linkable: boolean;
    note?: string;
  };
  available_retailers: { key: string; name: string; search_linkable: boolean }[];
  groups: PurchasePlanGroup[];
  orderable_total: number;
  orderable_item_count: number;
  blocked: BlockedItem[];
  blocked_count: number;
}

// ── Ingredient → Product mapping ───────────────────────────────────────────

export interface UnmappedIngredient {
  ingredient_id: string;
  canonical_name: string;
  category: string;
  unit_type: string;
  alcoholic: boolean;
  cocktail_usage_count: number;
}

export interface MappingCandidate {
  product_id: string;
  product_name: string;
  canonical_name?: string | null;
  brand?: string | null;
  package_size?: number | null;
  package_unit?: string | null;
  price_after_vat?: number | null;
  price_before_vat?: number | null;
  vat_rate?: number | null;
  is_historical?: boolean | null;
  supplier_name?: string | null;
  has_price: boolean;
}

export interface CandidatesResponse {
  ingredient: {
    ingredient_id: string;
    canonical_name: string;
    category: string;
    unit_type: string;
  };
  same_category: MappingCandidate[];
  other: MappingCandidate[];
}

export interface ExistingMapping {
  mapping_id: string;
  ingredient_id: string;
  ingredient_name?: string | null;
  category?: string | null;
  product_id: string;
  product_name?: string | null;
  preferred: boolean;
  substitution_allowed: boolean;
  notes?: string | null;
  price_after_vat?: number | null;
  supplier_name?: string | null;
  has_price: boolean;
}

export interface MappingCoverage {
  total_ingredients: number;
  mapped: number;
  unmapped: number;
  mapped_and_priced: number;
  mapped_without_price: number;
  coverage_pct: number;
}

export interface CalcResult {
  total_drinks: number;
  alcoholic_drinks: number;
  non_alcoholic_drinks: number;
  total_cost?: number;
  cost_per_guest?: number;
  budget_status?: string;
  budget_variance?: number;
  has_missing_prices: boolean;
  has_missing_mappings: boolean;
  warnings: string[];
}

// ── API calls ──────────────────────────────────────────────────────────────

export const api = {
  // Cocktails
  getCocktails: (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return apiFetch<{ total: number; items: Cocktail[] }>(`/api/cocktails${qs}`);
  },
  getCocktail: (id: string) =>
    apiFetch<CocktailDetail>(`/api/cocktails/${id}`),
  getCocktailThemes: () =>
    apiFetch<{ themes: string[] }>("/api/cocktails/themes"),

  // Events
  createEvent: (data: {
    name: string;
    guest_count: number;
    budget: number;
    company_name?: string;
    event_date?: string;
    location?: string;
    duration_hours?: number;
    expected_drinks_per_guest?: number;
    non_alcoholic_pct?: number;
    theme?: string;
    ai_request?: string;
    waste_buffer_pct?: number;
  }) =>
    apiFetch<{ id: string; name: string; status: string }>("/api/events", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  listEvents: (limit = 50) =>
    apiFetch<{ count: number; items: EventListItem[] }>(`/api/events?limit=${limit}`),
  getEvent: (id: string) => apiFetch<Event>(`/api/events/${id}`),
  updateEvent: (
    id: string,
    data: {
      name?: string;
      guest_count?: number;
      budget?: number | null;
      location?: string | null;
      event_date?: string | null;
    }
  ) =>
    apiFetch<{
      id: string;
      name: string;
      guest_count: number;
      budget: number | null;
      location: string | null;
      event_date: string | null;
      status: string;
    }>(`/api/events/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  deleteEvent: (id: string) =>
    apiFetch<{ deleted: boolean; id: string }>(
      `/api/events/${id}`,
      { method: "DELETE" }
    ),

  setMenu: (
    eventId: string,
    menu: { cocktail_id: string; allocation_pct: number; ai_rationale?: string }[]
  ) =>
    apiFetch(`/api/events/${eventId}/menu`, {
      method: "PUT",
      body: JSON.stringify({ menu }),
    }),
  calculate: (eventId: string) =>
    apiFetch<CalcResult>(`/api/events/${eventId}/calculate`, { method: "POST" }),
  getBatch: (eventId: string, cocktailId: string, servings: number) =>
    apiFetch<Batch>(`/api/events/${eventId}/cocktails/${cocktailId}/batch?servings=${servings}`),
  getAlternatives: (eventId: string, ingredientId: string) =>
    apiFetch<Alternatives>(`/api/events/${eventId}/ingredients/${ingredientId}/alternatives`),
  setEventProduct: (eventId: string, ingredientId: string, productId: string, reason?: string) =>
    apiFetch<Alternatives>(`/api/events/${eventId}/ingredients/${ingredientId}/product`, {
      method: "PUT",
      body: JSON.stringify({ product_id: productId, reason }),
    }),
  clearEventProduct: (eventId: string, ingredientId: string) =>
    apiFetch<Alternatives>(`/api/events/${eventId}/ingredients/${ingredientId}/product`, {
      method: "DELETE",
    }),
  getEventMessages: (eventId: string) =>
    apiFetch<{ messages: StoredMessage[] }>(`/api/events/${eventId}/messages`),
  getEquipment: (eventId: string, peoplePerStation?: number) =>
    apiFetch<EquipmentPlan>(
      `/api/events/${eventId}/equipment` +
      (peoplePerStation ? `?people_per_station=${peoplePerStation}` : "")),
  setWorkshop: (eventId: string,
                body: { is_workshop?: boolean; people_per_station?: number }) =>
    apiFetch<{ is_workshop: boolean; people_per_station: number }>(
      `/api/events/${eventId}/workshop`,
      { method: "PUT", body: JSON.stringify(body) }),
  compareShops: (eventId: string) =>
    apiFetch<ShopComparison>(`/api/events/${eventId}/compare-shops`),
  getPrepSheet: (eventId: string) =>
    apiFetch<PrepSheet>(`/api/events/${eventId}/prep-sheet`),
  getShoppingList: (eventId: string) =>
    apiFetch<ShoppingList>(`/api/events/${eventId}/shopping-list`),
  getPurchasePlan: (eventId: string, retailer?: string) =>
    apiFetch<PurchasePlan>(
      `/api/events/${eventId}/purchase-plan${retailer ? `?retailer=${retailer}` : ""}`
    ),
  getCostSummary: (eventId: string) =>
    apiFetch<CostSummary>(`/api/events/${eventId}/cost`),

  // Suppliers
  getSuppliers: () => apiFetch<{ suppliers: { id: string; name: string }[] }>("/api/suppliers"),

  // Ingredient → Product mapping
  getMappingCoverage: () => apiFetch<MappingCoverage>("/api/mappings/coverage"),
  getUnmapped: () =>
    apiFetch<{ count: number; items: UnmappedIngredient[] }>("/api/mappings/unmapped"),
  getMapped: () =>
    apiFetch<{ count: number; items: ExistingMapping[] }>("/api/mappings/mapped"),
  getCandidates: (ingredientId: string) =>
    apiFetch<CandidatesResponse>(`/api/mappings/candidates/${ingredientId}`),
  createMapping: (data: {
    ingredient_id: string;
    product_id: string;
    preferred?: boolean;
    substitution_allowed?: boolean;
    notes?: string;
  }) =>
    apiFetch<{
      mapping_id: string;
      ingredient_name: string;
      product_name: string;
      has_price: boolean;
      warning?: string | null;
    }>("/api/mappings", { method: "POST", body: JSON.stringify(data) }),
  deleteMapping: (mappingId: string) =>
    apiFetch<{ status: string }>(`/api/mappings/${mappingId}`, { method: "DELETE" }),

  // Agent
  // `currentTab` is one word, not a payload: the backend can read the event
  // itself, and the only thing it cannot know is where the person is standing.
  chat: (
    eventId: string,
    messages: { role: string; content: string }[],
    currentTab?: string,
  ) =>
    apiFetch<{ response: string; event_status: string; iterations: number }>("/api/agent/chat", {
      method: "POST",
      body: JSON.stringify({ event_id: eventId, messages, current_tab: currentTab }),
    }),

  // Plan — one sentence in, a full costed plan out
  createPlan: (description: string, retailer?: string) =>
    apiFetch<PlanResult>("/api/plan", {
      method: "POST",
      body: JSON.stringify({ description, retailer }),
    }),

  // Pre-event AI coach
  eventBuilderAdvice: (data: {
    message: string;
    draft: Record<string, string>;
    history: {
      role: "user" | "assistant";
      content: string;
    }[];
  }) =>
    apiFetch<{
      message: string;
      updates: Record<string, string | number>;
      recommended_cocktails: string[];
      ready_to_create: boolean;
      provider: string;
      model: string;
    }>("/api/event-builder/advice", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  // Health
  health: () => apiFetch<{ status: string }>("/api/health"),
};

// ── Events list ────────────────────────────────────────────────────────────

export interface EventListItem {
  id: string;
  name: string;
  status: string;
  guest_count: number;
  budget?: number | null;
  location?: string | null;
  event_date?: string | null;
  theme?: string | null;
  menu_count: number;
  estimated_cost?: number | null;
  cost_is_partial: boolean;
  created_at?: string | null;
}

// ── Plan (conversation-first front door) ───────────────────────────────────

export interface PlanRecipeLine {
  ingredient: string;
  amount?: number | null;
  unit: string;
  total_for_event?: number | null;
}

export interface PlanMenuItem {
  cocktail_id: string;
  name: string;
  servings: number;
  allocation_pct: number;
  glass?: string | null;
  technique?: string | null;
  garnish?: string | null;
  recipe: PlanRecipeLine[];
}

export interface PlanShopItem {
  ingredient_name: string;
  product_name?: string | null;
  order_line: string;
  packages_required: number;
  total_price?: number | null;
  purchase_link: PurchaseLinkInfo;
}

export interface PlanResult {
  event_id: string;
  event_name: string;
  parsed: {
    guests: number;
    budget?: number | null;
    requested_cocktails: string[];
    requested_count?: number | null;
    defaults_used: string[];
  };
  totals: {
    guests: number;
    total_drinks: number;
    alcoholic_drinks: number;
    non_alcoholic_drinks: number;
    cost?: number | null;
    cost_per_guest?: number | null;
    budget?: number | null;
    budget_status?: string | null;
    budget_variance?: number | null;
  };
  menu: PlanMenuItem[];
  shopping: {
    groups: {
      store_name: string;
      store_website?: string | null;
      items: PlanShopItem[];
      subtotal: number;
    }[];
    blocked: {
      ingredient_name: string;
      required_amount?: number | null;
      unit?: string | null;
      status: string;
      reason: string;
    }[];
    retailer: { key: string; name: string; search_linkable: boolean };
    available_retailers: { key: string; name: string; search_linkable: boolean }[];
  };
  notes: string[];
  engine_warnings: string[];
  sanity_warnings: string[];
}


// ── Prep sheet (the printable batch instructions) ──────────────────────────

export interface PrepLine {
  name: string;
  per_drink: number | null;
  unit: string;
  batch_total: number | null;
  bottles: number | null;
  bottle_size_ml?: number | null;
  note: string | null;
}

export interface PrepCocktail {
  cocktail_id: string;
  name: string;
  servings: number;
  glass?: string | null;
  technique?: string | null;
  garnish?: string | null;
  non_alc_variant?: string | null;
  ingredients: PrepLine[];
  glass_instruction?: string | null;
  batch_allowed?: boolean;
  batch_blocked_by?: string[];
  batch_instruction?: string | null;
}

export interface PrepSheet {
  event_id: string;
  event_name: string;
  guests: number;
  duration_hours: number;
  total_drinks: number;
  cocktails: PrepCocktail[];
}


// ── Batch, alternatives, stored conversation ───────────────────────────────

export interface BatchLine {
  ingredient_id: string;
  name: string;
  unit: string;
  per_serving: number | null;
  total: number | null;
  bottles_exact: number | null;
  bottles_to_buy: number | null;
  package_size: number | null;
  package_unit: string | null;
  product_name: string | null;
  note: string | null;
}

export interface Batch {
  cocktail_id: string;
  name: string;
  servings: number;
  measured_volume_ml: number | null;
  has_unmeasured: boolean;
  unmeasured: string[];
  lines: BatchLine[];
}

export interface AlternativeOption {
  product_id: string;
  product_name: string;
  hebrew_name: string;
  package_size: number;
  package_unit: string;
  price_per_package: number;
  packages_required: number;
  event_total: number;
  difference_vs_current: number | null;
  is_current: boolean;
  is_house_recommendation: boolean;
  supplier_name: string | null;
}

export interface Alternatives {
  event_id: string;
  ingredient_id: string;
  ingredient_name: string | null;
  required_amount: number;
  required_unit: string;
  current_total: number | null;
  current_product_id: string | null;
  is_overridden: boolean;
  options: AlternativeOption[];
  note: string;
}

export interface StoredMessage {
  role: "user" | "assistant";
  content: string;
  tab: string | null;
  created_at: string | null;
}


// ── Basket comparison across shops ─────────────────────────────────────────

export interface ShopLine {
  ingredient_id: string;
  ingredient: string;
  product: string;
  package_size: number;
  package_unit: string;
  price_per_package: number;
  packages: number;
  event_total: number;
  url: string | null;
}

export interface ShopBasket {
  shop: string;
  website: string | null;
  covers: number;
  of: number;
  missing: string[];
  subtotal: number;
  bottles: number;
  free_delivery_over: number | null;
  delivery_fee: number | null;
  // The smallest order the shop accepts. A different obstacle from delivery:
  // it does not make the basket dearer, it makes it un-orderable.
  minimum_order: number | null;
  below_minimum: boolean;
  short_of_minimum_by: number | null;
  delivery_note: string | null;
  clears_free_delivery: boolean;
  // null when the shop does not publish terms covering an order this size.
  delivery: number | null;
  delivered_total: number | null;
  delivered_total_unknown_because: string | null;
  lines: ShopLine[];
}

export interface ShopComparison {
  event_id: string;
  ingredients: number;
  fully_covered_by_any_shop: boolean;
  shops: ShopBasket[];
  split: {
    total: number;
    shop_count: number;
    shops: string[];
    covers: number;
    of: number;
    saving_vs_best_single: number | null;
    comparable: boolean;
    best_single_shop: string | null;
    best_single_covers: number;
    leg_totals: Record<string, number>;
    below_minimum: {
      shop: string;
      leg_total: number;
      minimum_order: number;
      short_by: number;
    }[];
    note: string;
  };
  note: string;
}


// ── Workshop equipment ─────────────────────────────────────────────────────

export interface EquipmentLine {
  key: string;
  name: string;
  basis: "per_station" | "per_participant" | "fixed";
  needed: number;
  packs: number | null;
  pack_size: number;
  units_bought: number | null;
  price_per_pack: number | null;
  total: number | null;
  product_name: string | null;
  supplier: string | null;
  in_stock: boolean;
  essential: boolean;
  note: string | null;
  status: "OK" | "PRICE_MISSING" | "OUT_OF_STOCK";
}

export interface EquipmentPlan {
  event_id: string;
  is_workshop: boolean;
  participants: number;
  people_per_station: number;
  saved_people_per_station: number;
  stations: number;
  lines: EquipmentLine[];
  // null when anything essential has no published price anywhere.
  total_cost: number | null;
  known_cost: number;
  is_complete: boolean;
  missing: string[];
  out_of_stock: string[];
  alternatives: {
    for: string; product: string; price: number;
    in_stock: boolean; supplier: string | null; url: string | null;
  }[];
  note: string;
}


export const getShopComparison = (eventId: string) =>
  apiFetch<ShopComparison>(
    `/api/events/${eventId}/compare-shops`
  );


export interface EquipmentShopOption {
  product_id: string;
  product: string;
  supplier: string;
  supplier_website: string | null;
  price: number;
  package_size: number;
  package_unit: string;
  available: boolean;
  url: string | null;
}

export interface EquipmentShopGroup {
  key: string;
  name: string;
  options: EquipmentShopOption[];
}

export interface EquipmentShop {
  event_id: string;
  groups: EquipmentShopGroup[];
  total_categories: number;
  note: string;
}

export const getEquipmentShop = (
  eventId: string
) =>
  apiFetch<EquipmentShop>(
    `/api/events/${eventId}/equipment-shop`
  );
