import uuid
from sqlalchemy import String, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin


class Ingredient(Base, TimestampMixin):
    __tablename__ = "ingredients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # spirit|liqueur|syrup|juice|mixer|garnish|bitters|wine|beer|other
    unit_type: Mapped[str] = mapped_column(String(20), nullable=False, default="ml")
    alcoholic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text)

    # What else could fill this slot — "white_rum", "gin", "sweet_vermouth".
    #
    # `category` above is too coarse for substitution: it says "spirit", and a
    # gin does not stand in for a rum. Without a finer grouping the only
    # alternative the system could offer was another product already mapped to
    # this exact ingredient — so a shop stocking four good white rums, none of
    # them the Havana Club the recipe names, reported "not stocked here" and its
    # buy link led to an empty search.
    #
    # Topaz's rule: any rum will do. The brand in a recipe is a preference.
    # Null means genuinely unsubstitutable — nothing else is a Fernet Branca.
    substitute_group: Mapped[str | None] = mapped_column(String(50), index=True)

    # Relationships
    aliases: Mapped[list["IngredientAlias"]] = relationship(back_populates="ingredient", cascade="all, delete-orphan")
    cocktail_ingredients: Mapped[list["CocktailIngredient"]] = relationship(back_populates="ingredient")  # type: ignore
    product_mappings: Mapped[list["IngredientProductMapping"]] = relationship(back_populates="ingredient")  # type: ignore


class IngredientAlias(Base):
    __tablename__ = "ingredient_aliases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ingredient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ingredients.id", ondelete="CASCADE"))
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_file: Mapped[str | None] = mapped_column(String(255))
    confidence: Mapped[str] = mapped_column(String(20), default="confirmed")  # confirmed|uncertain

    ingredient: Mapped["Ingredient"] = relationship(back_populates="aliases")
