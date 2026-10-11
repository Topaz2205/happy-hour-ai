"""
Purchase-link resolution.

Two kinds of link, never conflated:

  DIRECT — a real product page URL somebody recorded for this exact product.
           Trustworthy: it goes to the item itself.

  SEARCH — a link to a retailer's own search endpoint, pre-filled with the
           product name. Lands on that shop's results for the term. It is NOT
           a promise that the shop stocks the item.

Deep product URLs are never fabricated. Guessing a path like
/product/bombay-sapphire-700ml yields a 404 and quietly erodes trust in every
other number on the page, so the fallback is an honest search instead.

Verification status of each retailer's search endpoint (checked 2026-08-21):

  * paneco.co.il       — Magento. `/catalogsearch/` confirmed present in
                         robots.txt; `/catalogsearch/result/?q=` is the Magento
                         framework default. SEARCH links enabled.
  * the-importer.co.il — Magento (Adobe Commerce). Same confirmation. SEARCH
                         links enabled.
  * mashkaot.co.il     — custom PHP. Candidate GET patterns were tested against
                         the live site and returned an unrelated snacks
                         category rather than results for the query, so its
                         search is POST- or JS-driven and NOT expressible as a
                         URL. Rather than ship a link that silently goes to the
                         wrong page, this retailer is homepage-only.

The robots.txt restriction on the two Magento search paths blocks automated
crawling; it does not affect a person clicking the link in a browser.

If a retailer's search breaks or a new one is added, verify it the same way:
build the URL, fetch it, and confirm the results actually match the query.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from urllib.parse import quote


class LinkKind(str, Enum):
    DIRECT = "DIRECT"       # real product page for this exact item
    SEARCH = "SEARCH"       # retailer search results for the term
    HOMEPAGE = "HOMEPAGE"   # shop's front page; search it yourself
    NONE = "NONE"           # nothing honest to link to


@dataclass(frozen=True)
class RetailerSpec:
    key: str
    display_name: str
    website: str
    # None means the shop's search is not reachable by URL. Such a retailer
    # yields a HOMEPAGE link — never a fabricated search URL.
    search_url_template: Optional[str] = None
    prefers_hebrew_query: bool = True
    verification_note: str = ""


# Verified retailer definitions. Adding a shop means verifying its search
# endpoint first — see the module docstring.
RETAILERS: dict[str, RetailerSpec] = {
    "paneco": RetailerSpec(
        key="paneco",
        display_name="Paneco",
        website="https://www.paneco.co.il/",
        search_url_template="https://www.paneco.co.il/catalogsearch/result/?q={query}",
        prefers_hebrew_query=True,
        verification_note="Magento; /catalogsearch/ confirmed in robots.txt.",
    ),
    "the_importer": RetailerSpec(
        key="the_importer",
        display_name="היבואן",
        website="https://www.the-importer.co.il/",
        search_url_template="https://www.the-importer.co.il/catalogsearch/result/?q={query}",
        prefers_hebrew_query=True,
        verification_note="Adobe Commerce/Magento; /catalogsearch/ confirmed in robots.txt.",
    ),
    "mashkaot": RetailerSpec(
        key="mashkaot",
        display_name="שר המשקאות",
        website="https://www.mashkaot.co.il/",
        search_url_template=None,  # search is not URL-addressable — see docstring
        prefers_hebrew_query=True,
        verification_note=(
            "Custom PHP. Candidate GET search patterns were tested live and "
            "returned an unrelated category, so no search URL is published. "
            "Homepage link only."
        ),
    ),
}

# Paneco is the default: it is the one confirmed-searchable shop with the
# widest catalog of the branded spirits the recipe book names.
DEFAULT_RETAILER_KEY = "paneco"


# Bookkeeping phrases that live in the source spreadsheets' product names.
# They describe how a line was priced, not what the bottle is, and they wreck
# a search query if passed through.
_NOISE_PATTERNS = [
    r"בקבוק\s+חישוב\s+לארגז",   # "bottle, calculated per case"
    r"חישוב\s+לארגז",
    r"\bחישוב\b",
    r"\bלארגז\b",
    r"\d+\s*יח['׳]?",             # "24 יח׳" — pack count
    r"\(per\s+case\)",
    r"\(per\s+bottle\)",
    r"\(can\)",
    r"\(bottle\)",
    r"\(\d+\s*L\)",
    r"\(fruit\)",
]


def clean_query(name: str) -> str:
    """
    Strip pricing bookkeeping out of a product name so the search term is the
    thing you'd actually type into a shop's search box.

    'קורונה בקבוק חישוב לארגז' -> 'קורונה'
    """
    q = name or ""
    for pattern in _NOISE_PATTERNS:
        q = re.sub(pattern, " ", q, flags=re.IGNORECASE)
    q = re.sub(r"[|/\\]+", " ", q)
    q = re.sub(r"\s{2,}", " ", q).strip(" -–—,·")
    return q.strip()


def choose_query_term(
    product_name: Optional[str],
    canonical_name: Optional[str],
    prefers_hebrew: bool = True,
) -> Optional[str]:
    """
    Pick the better search term.

    Product names came off Israeli price lists, so they are the local trade
    names these shops actually index. The English canonical name is the
    fallback for ingredients that never appeared in a price list.
    """
    product_clean = clean_query(product_name) if product_name else ""
    canonical_clean = clean_query(canonical_name) if canonical_name else ""

    has_hebrew = bool(re.search(r"[֐-׿]", product_clean))

    if prefers_hebrew and has_hebrew and len(product_clean) >= 2:
        return product_clean
    if product_clean and len(product_clean) >= 2:
        return product_clean
    if canonical_clean:
        return canonical_clean
    return None


@dataclass(frozen=True)
class PurchaseLink:
    kind: LinkKind
    url: Optional[str]
    retailer_key: Optional[str]
    retailer_name: Optional[str]
    query_term: Optional[str]
    # Plain-language note for the UI, so a SEARCH link is never mistaken for
    # a confirmed product page.
    note: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "kind": self.kind.value,
            "url": self.url,
            "retailer_key": self.retailer_key,
            "retailer_name": self.retailer_name,
            "query_term": self.query_term,
            "note": self.note,
        }


NO_LINK = PurchaseLink(
    kind=LinkKind.NONE,
    url=None,
    retailer_key=None,
    retailer_name=None,
    query_term=None,
    note=None,
)


def build_search_url(spec: RetailerSpec, term: str) -> str:
    # quote() with no safe chars so Hebrew and spaces both encode correctly
    return spec.search_url_template.format(query=quote(term, safe=""))


def resolve_purchase_link(
    *,
    direct_url: Optional[str] = None,
    direct_url_supplier_name: Optional[str] = None,
    product_name: Optional[str] = None,
    canonical_name: Optional[str] = None,
    retailer_key: Optional[str] = DEFAULT_RETAILER_KEY,
) -> PurchaseLink:
    """
    A recorded product URL always wins. Otherwise fall back to a search link
    at the chosen retailer. Returns NO_LINK when there is nothing honest to
    point at.
    """
    if direct_url:
        return PurchaseLink(
            kind=LinkKind.DIRECT,
            url=direct_url,
            retailer_key=None,
            retailer_name=direct_url_supplier_name,
            query_term=None,
            note=None,
        )

    spec = RETAILERS.get(retailer_key or "") or RETAILERS.get(DEFAULT_RETAILER_KEY)
    if spec is None:
        return NO_LINK

    term = choose_query_term(product_name, canonical_name, spec.prefers_hebrew_query)

    # Shop whose search cannot be expressed as a URL: send them to the front
    # door rather than to a guessed path that would land on the wrong page.
    if not spec.search_url_template:
        return PurchaseLink(
            kind=LinkKind.HOMEPAGE,
            url=spec.website,
            retailer_key=spec.key,
            retailer_name=spec.display_name,
            query_term=term,
            note=(
                f"{spec.display_name} has no linkable search — opens the shop's "
                f"home page; search for “{term}” there."
                if term else
                f"Opens {spec.display_name}'s home page."
            ),
        )

    if not term:
        return NO_LINK

    return PurchaseLink(
        kind=LinkKind.SEARCH,
        url=build_search_url(spec, term),
        retailer_key=spec.key,
        retailer_name=spec.display_name,
        query_term=term,
        note=f"Search results at {spec.display_name} — confirm the bottle and size before ordering.",
    )
