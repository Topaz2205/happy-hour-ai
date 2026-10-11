import uuid
from datetime import date, datetime
from sqlalchemy import UniqueConstraint, func, String, Boolean, Text, Numeric, Integer, ForeignKey, Date, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin


class Event(Base, TimestampMixin):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    event_date: Mapped[date | None] = mapped_column(Date)
    location: Mapped[str | None] = mapped_column(String(255))
    guest_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # Nullable on purpose: plenty of real events are planned before anyone has
    # set a budget. The engine already treats a missing budget as "cost it, but
    # report no over/under status" — forcing a number here would mean inventing
    # one, which is the failure mode this whole system is built to avoid.
    budget: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    duration_hours: Mapped[float] = mapped_column(Numeric(5, 2), default=2.5)
    expected_drinks_per_guest: Mapped[float] = mapped_column(Numeric(5, 2), default=2.5)
    non_alcoholic_pct: Mapped[float] = mapped_column(Numeric(5, 4), default=0.25)
    theme: Mapped[str | None] = mapped_column(String(100))
    ai_request: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    waste_buffer_pct: Mapped[float] = mapped_column(Numeric(5, 4), default=0.08)

    # ── Workshop ──────────────────────────────────────────────────────────
    # A workshop is an event where the guests make the drinks, so it needs kit
    # as well as ingredients. Equipment scales with people and stations, not
    # with servings, which is why it is a flag rather than a menu setting.
    is_workshop: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # How many people share one set of tools. Topaz sets this per event: whether
    # people work alone or in pairs is a decision about the workshop, and it
    # halves or doubles the tool bill. Two is only the starting point.
    people_per_station: Mapped[int] = mapped_column(Integer, default=2, nullable=False)

    menu_items: Mapped[list["EventMenuItem"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    requirements: Mapped[list["EventRequirement"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    purchase_items: Mapped[list["EventPurchaseItem"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    product_overrides: Mapped[list["EventIngredientProductOverride"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    messages: Mapped[list["EventMessage"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class EventMenuItem(Base):
    __tablename__ = "event_menu_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"))
    cocktail_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cocktails.id"))
    allocation_pct: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    expected_servings: Mapped[int | None] = mapped_column(Integer)
    ai_rationale: Mapped[str | None] = mapped_column(Text)

    event: Mapped["Event"] = relationship(back_populates="menu_items")
    cocktail: Mapped["Cocktail"] = relationship(back_populates="event_menu_items")  # type: ignore


class EventRequirement(Base):
    __tablename__ = "event_requirements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"))
    ingredient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingredients.id"))
    required_amount: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    event: Mapped["Event"] = relationship(back_populates="requirements")
    ingredient: Mapped["Ingredient"] = relationship()  # type: ignore


class EventPurchaseItem(Base):
    __tablename__ = "event_purchase_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"))
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"))
    ingredient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingredients.id"))
    required_amount: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    required_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    packages_required: Mapped[int | None] = mapped_column(Integer)
    package_size: Mapped[float | None] = mapped_column(Numeric(10, 2))
    package_unit: Mapped[str | None] = mapped_column(String(20))
    unit_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    total_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(50), default="OK")
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"))
    product_url: Mapped[str | None] = mapped_column(String(1000))

    event: Mapped["Event"] = relationship(back_populates="purchase_items")
    ingredient: Mapped["Ingredient"] = relationship()  # type: ignore
    product: Mapped["Product | None"] = relationship()  # type: ignore
    supplier: Mapped["Supplier | None"] = relationship()  # type: ignore


class EventIngredientProductOverride(Base, TimestampMixin):
    """
    One event's choice of product for one ingredient.

    WHY A SEPARATE TABLE RATHER THAN A FLAG ON THE GLOBAL MAPPING
    -------------------------------------------------------------
    An HR person swapping to a cheaper tequila for their own party must not
    change what every other event buys. `IngredientProductMapping.preferred` is
    the house recommendation and stays the house recommendation; this table
    records a deviation that belongs to exactly one event and dies with it.

    The calculator's resolution order becomes:
        1. this table, if a row exists for (event, ingredient)
        2. the globally preferred IngredientProductMapping
        3. the existing missing-data behaviour — never a guess

    The unique constraint is what makes that first step unambiguous: one
    ingredient in one event resolves to one product, or to nothing.
    """
    __tablename__ = "event_ingredient_product_overrides"
    __table_args__ = (
        UniqueConstraint("event_id", "ingredient_id",
                         name="uq_event_ingredient_override"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingredients.id"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    # Why this event deviates from the recommendation. Free text, written by the
    # person or by the agent when it applies a saving on their behalf.
    reason: Mapped[str | None] = mapped_column(Text)

    event: Mapped["Event"] = relationship(back_populates="product_overrides")
    product: Mapped["Product"] = relationship()  # type: ignore


class EventMessage(Base):
    """
    One turn of one event's conversation.

    Deliberately minimal. The purpose is that event A's conversation is still
    there when you come back to event A, and that it is not event B's — not to
    build a messaging system. No threads, no read state, no editing: a role, the
    text, and when it was said.

    Tool calls are not stored. They are an implementation detail of how an
    answer was produced, they are large, and replaying them would mean promising
    that a stored tool result is still true — which it is not, because the event
    it described has since changed.
    """
    __tablename__ = "event_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)   # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Which tab the person was on. Kept so a returning conversation reads in
    # context — "make it cheaper" means something different from Shopping than
    # it does from Menu.
    tab: Mapped[str | None] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)

    event: Mapped["Event"] = relationship(back_populates="messages")
