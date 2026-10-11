import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Text, Numeric, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin


class Supplier(Base, TimestampMixin):
    __tablename__ = "suppliers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    website: Mapped[str | None] = mapped_column(String(500))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    # A retailer is a shop you can actually place an order with, as opposed to
    # a price-book record imported from a spreadsheet.
    is_retailer: Mapped[bool] = mapped_column(Boolean, default=False)

    # The shop's own search endpoint, with {query} where the term goes.
    # Verified against each live site — never guessed, because a wrong template
    # produces dead links, which is worse than showing no link at all.
    search_url_template: Mapped[str | None] = mapped_column(String(500))

    # Prefer Hebrew search terms; Israeli shops index local trade names.
    prefers_hebrew_query: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── Delivery ──────────────────────────────────────────────────────────
    # All three are nullable, and that is the point. One shop publishes its
    # threshold but not its fee; another adds an unpublished per-case surcharge
    # above twelve bottles — which an event order passes routinely. A cost model
    # that filled those gaps with a plausible number would be inventing the one
    # figure the buyer is trying to compare.
    free_delivery_over: Mapped[float | None] = mapped_column(Numeric(10, 2))
    delivery_fee: Mapped[float | None] = mapped_column(Numeric(10, 2))
    # The smallest order the shop will accept at all.
    #
    # Not the same question as delivery, and it bites hardest on the small
    # baskets: the juice supplier will not deliver under ₪200, and an event
    # needing ₪38 of lime juice cannot order it however cheap it looks. A
    # comparison that showed the ₪38 and stopped there would be quoting a
    # price for an order that cannot be placed.
    minimum_order: Mapped[float | None] = mapped_column(Numeric(10, 2))
    # Anything that stops delivery cost being a simple threshold, in words.
    delivery_note: Mapped[str | None] = mapped_column(Text)

    products: Mapped[list["SupplierProduct"]] = relationship(back_populates="supplier")


class SupplierProduct(Base):
    __tablename__ = "supplier_products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    supplier_sku: Mapped[str | None] = mapped_column(String(100))

    # The size THIS shop sells, when it differs from the product's nominal size.
    #
    # Discovered the hard way: Aperol and Campari are not sold in 700ml by
    # either Israeli shop researched — both stock only 1L — while our product
    # record said 700ml. A single size on the Product cannot describe a market
    # where the same drink comes in different bottles at different shops, and
    # costing 1L of Aperol as though it were 700ml overstates the per-ml price
    # by about 30%.
    #
    # Null means "same as the product's own size", so every existing row keeps
    # its current meaning and nothing has to be backfilled.
    package_size: Mapped[float | None] = mapped_column(Numeric(10, 2))
    package_unit: Mapped[str | None] = mapped_column(String(20))
    product_url: Mapped[str | None] = mapped_column(String(1000))
    price_before_vat: Mapped[float | None] = mapped_column(Numeric(10, 2))
    price_after_vat: Mapped[float | None] = mapped_column(Numeric(10, 2))
    vat_rate: Mapped[float] = mapped_column(Numeric(5, 4), default=0.18)
    is_historical: Mapped[bool] = mapped_column(Boolean, default=False)
    source_file: Mapped[str | None] = mapped_column(String(255))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available: Mapped[bool] = mapped_column(Boolean, default=True)

    supplier: Mapped["Supplier"] = relationship(back_populates="products")
    product: Mapped["Product"] = relationship(back_populates="supplier_listings")  # type: ignore
