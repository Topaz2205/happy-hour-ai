import uuid
from sqlalchemy import String, Boolean, Text, Numeric, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(255))
    ingredient_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ingredients.id"))
    package_size: Mapped[float | None] = mapped_column(Numeric(10, 2))
    package_unit: Mapped[str] = mapped_column(String(20), default="ml")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)

    ingredient: Mapped["Ingredient | None"] = relationship()  # type: ignore
    mappings: Mapped[list["IngredientProductMapping"]] = relationship(back_populates="product")
    supplier_listings: Mapped[list["SupplierProduct"]] = relationship(back_populates="product")  # type: ignore


class IngredientProductMapping(Base):
    __tablename__ = "ingredient_product_mapping"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingredients.id"), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    preferred: Mapped[bool] = mapped_column(Boolean, default=False)
    substitution_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    substitution_priority: Mapped[int] = mapped_column(Integer, default=99)
    notes: Mapped[str | None] = mapped_column(Text)

    ingredient: Mapped["Ingredient"] = relationship(back_populates="product_mappings")  # type: ignore
    product: Mapped["Product"] = relationship(back_populates="mappings")
