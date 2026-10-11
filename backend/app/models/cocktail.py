import uuid
from sqlalchemy import String, Boolean, Text, Numeric, Integer, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin


class Cocktail(Base, TimestampMixin):
    __tablename__ = "cocktails"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    alcoholic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    technique: Mapped[str | None] = mapped_column(Text)
    glass_type: Mapped[str | None] = mapped_column(String(100))
    garnish: Mapped[str | None] = mapped_column(String(255))
    instructions: Mapped[str | None] = mapped_column(Text)
    comments: Mapped[str | None] = mapped_column(Text)
    non_alc_variant: Mapped[str | None] = mapped_column(Text)
    theme: Mapped[str | None] = mapped_column(String(100))  # classic|seasonal|signature|etc
    complexity: Mapped[str] = mapped_column(String(20), default="medium")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    taste_profile: Mapped[dict[str, int] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    style_tags: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
    )

    strength: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    base_spirit: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )

    # Data lineage
    source_file: Mapped[str | None] = mapped_column(String(255))
    source_sheet: Mapped[str | None] = mapped_column(String(255))
    source_row: Mapped[int | None] = mapped_column(Integer)

    # Relationships
    ingredients: Mapped[list["CocktailIngredient"]] = relationship(
        back_populates="cocktail", cascade="all, delete-orphan", order_by="CocktailIngredient.sort_order"
    )
    event_menu_items: Mapped[list["EventMenuItem"]] = relationship(back_populates="cocktail")  # type: ignore


class CocktailIngredient(Base):
    __tablename__ = "cocktail_ingredients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cocktail_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cocktails.id", ondelete="CASCADE"), nullable=False
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingredients.id"), nullable=False
    )
    amount: Mapped[float | None] = mapped_column(Numeric(10, 4))
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="ml")
    optional: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    source_amount: Mapped[str | None] = mapped_column(String(50))
    source_file: Mapped[str | None] = mapped_column(String(255))

    cocktail: Mapped["Cocktail"] = relationship(back_populates="ingredients")
    ingredient: Mapped["Ingredient"] = relationship(back_populates="cocktail_ingredients")  # type: ignore
