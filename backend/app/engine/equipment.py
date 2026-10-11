"""
What a workshop needs in kit, and what it costs.

WHY THIS IS A SEPARATE AXIS FROM THE DRINKS ENGINE
--------------------------------------------------
Ingredients scale with drinks. Equipment does not: twenty people making three
cocktails each still need twenty glasses and ten shakers, not sixty of either.
Kit scales with PEOPLE and STATIONS, so it gets its own deterministic function
rather than being bolted onto a calculation that multiplies by servings.

THE TWO RULES, AND WHY EACH IS WHAT IT IS
-----------------------------------------
Tools are per station. A shaker, jigger, strainer and spoon are shared by
whoever stands at that station, and the number of stations is
`ceil(participants / people_per_station)` — a ratio Topaz sets per event,
because whether people work alone or in pairs is a decision about the workshop,
not a fact about arithmetic.

Glassware is per participant, because everyone drinks. But it is sold in packs
of six at the only shop that publishes prices, so the real question is how many
PACKS — and 20 people means 4 packs and 24 glasses, not 20. Pretending you can
buy 20 would understate the cost and hand someone a shopping list they cannot
place.

WHAT IT WILL NOT DO
-------------------
Price an item with no price. The one shop that stocks shakers, pourers, ice
trays and coupe glasses publishes no prices at all — every product page is an
enquiry form. Those items are returned as needed-but-unpriced, and the total is
marked incomplete, rather than being quietly left out of a number someone will
budget from.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, Optional

# How a quantity is derived. Stated per item so the sheet can explain itself.
Basis = Literal["per_station", "per_participant", "fixed"]


@dataclass
class EquipmentSpec:
    """One thing a workshop needs, and the rule for how many."""
    key: str
    name: str
    basis: Basis
    # How many per station / per participant / in total.
    quantity: float = 1.0
    # Sold in packs of this many. 1 means singly.
    pack_size: int = 1
    essential: bool = True
    note: Optional[str] = None


@dataclass
class EquipmentPrice:
    product_name: str
    price_per_pack: float
    pack_size: int
    supplier: str
    in_stock: bool = True
    url: Optional[str] = None


@dataclass
class EquipmentLine:
    key: str
    name: str
    basis: Basis
    needed: int                 # actual units required
    packs: Optional[int] = None
    pack_size: int = 1
    units_bought: Optional[int] = None
    price_per_pack: Optional[float] = None
    total: Optional[float] = None
    product_name: Optional[str] = None
    supplier: Optional[str] = None
    in_stock: bool = True
    essential: bool = True
    note: Optional[str] = None
    status: str = "OK"          # OK | PRICE_MISSING | OUT_OF_STOCK


@dataclass
class EquipmentPlan:
    participants: int
    people_per_station: int
    stations: int
    lines: list[EquipmentLine] = field(default_factory=list)
    total_cost: Optional[float] = None      # None when anything essential is unpriced
    known_cost: float = 0.0
    is_complete: bool = True
    missing: list[str] = field(default_factory=list)
    out_of_stock: list[str] = field(default_factory=list)


# The default kit for a make-your-own-cocktail workshop.
#
# Glassware is one per participant and comes in sixes. Tools are one per
# station. Nothing here is a guess about Topaz's business: the RATIO of people
# to a station is hers to set, and this list only says what a station contains.
DEFAULT_KIT: list[EquipmentSpec] = [
    EquipmentSpec("shaker", "Cocktail shaker", "per_station"),
    EquipmentSpec("jigger", "Jigger", "per_station"),
    EquipmentSpec("strainer", "Strainer", "per_station"),
    EquipmentSpec("bar_spoon", "Bar spoon", "per_station"),
    EquipmentSpec("muddler", "Muddler", "per_station", essential=False,
                  note="Only needed for cocktails that muddle — mojito, caipirinha."),
    EquipmentSpec("glass_rocks", "Rocks glasses", "per_participant", pack_size=6),
    EquipmentSpec("glass_highball", "Highball glasses", "per_participant", pack_size=6,
                  essential=False,
                  note="Needed only if the menu includes a long drink."),
    EquipmentSpec("ice_bucket", "Ice bucket", "per_station", quantity=1, essential=False),
    EquipmentSpec("ice_tongs", "Ice tongs", "per_station", quantity=1, essential=False),
]


def plan_equipment(
    participants: int,
    people_per_station: int,
    prices: Optional[dict[str, EquipmentPrice]] = None,
    kit: Optional[list[EquipmentSpec]] = None,
) -> EquipmentPlan:
    """
    Turn a headcount and a station ratio into a costed kit list.

    `prices` maps a spec key to what one pack costs where. A key with no entry
    is reported as PRICE_MISSING and, if essential, makes the whole total
    incomplete — the same discipline the drinks engine uses, for the same
    reason: a partial total that looks whole is worse than no total.
    """
    if participants <= 0:
        raise ValueError("participants must be positive")
    if people_per_station <= 0:
        raise ValueError("people_per_station must be positive")

    prices = prices or {}
    kit = kit or DEFAULT_KIT

    stations = math.ceil(participants / people_per_station)
    lines: list[EquipmentLine] = []
    known = 0.0
    missing: list[str] = []
    oos: list[str] = []

    for spec in kit:
        if spec.basis == "per_station":
            needed = math.ceil(stations * spec.quantity)
        elif spec.basis == "per_participant":
            needed = math.ceil(participants * spec.quantity)
        else:
            needed = math.ceil(spec.quantity)

        line = EquipmentLine(
            key=spec.key, name=spec.name, basis=spec.basis, needed=needed,
            essential=spec.essential, note=spec.note,
        )

        price = prices.get(spec.key)
        if price is None:
            line.status = "PRICE_MISSING"
            line.pack_size = spec.pack_size
            if spec.essential:
                missing.append(spec.name)
            lines.append(line)
            continue

        # The shop's pack size wins over the spec's: what you can buy is decided
        # by the shop, not by what the kit list assumed.
        pack = price.pack_size or spec.pack_size or 1
        packs = math.ceil(needed / pack)
        line.pack_size = pack
        line.packs = packs
        line.units_bought = packs * pack
        line.price_per_pack = price.price_per_pack
        line.total = round(packs * price.price_per_pack, 2)
        line.product_name = price.product_name
        line.supplier = price.supplier
        line.in_stock = price.in_stock
        if not price.in_stock:
            line.status = "OUT_OF_STOCK"
            oos.append(spec.name)
        known += line.total
        lines.append(line)

    complete = not missing
    return EquipmentPlan(
        participants=participants,
        people_per_station=people_per_station,
        stations=stations,
        lines=lines,
        total_cost=round(known, 2) if complete else None,
        known_cost=round(known, 2),
        is_complete=complete,
        missing=missing,
        out_of_stock=oos,
    )


def plan_to_dict(plan: EquipmentPlan) -> dict:
    return {
        "participants": plan.participants,
        "people_per_station": plan.people_per_station,
        "stations": plan.stations,
        "total_cost": plan.total_cost,
        "known_cost": plan.known_cost,
        "is_complete": plan.is_complete,
        "missing": plan.missing,
        "out_of_stock": plan.out_of_stock,
        "lines": [
            {
                "key": l.key, "name": l.name, "basis": l.basis,
                "needed": l.needed, "packs": l.packs, "pack_size": l.pack_size,
                "units_bought": l.units_bought, "price_per_pack": l.price_per_pack,
                "total": l.total, "product_name": l.product_name,
                "supplier": l.supplier, "in_stock": l.in_stock,
                "essential": l.essential, "note": l.note, "status": l.status,
            }
            for l in plan.lines
        ],
    }
