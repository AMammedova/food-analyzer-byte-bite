"""SE-layer data models.

WHY SEPARATE FROM ai/schemas.py
--------------------------------
`ai/schemas.py` defines the AI module's own types (Ingredient, NutritionFacts,
Nutrition). Those are frozen and cannot be changed (grading contract).

This file defines the SE layer's *output* types:

- IngredientOut  : what CLI and API return per ingredient (includes computed kcal etc.)
- AnalysisResult : full response for one image (meal_recognized + rows + totals)
- AnalysisRecord : what gets stored in PostgreSQL (adds id + timestamp)

Keeping these separate means the AI module and the SE layer can evolve
independently, and tests can use the SE models without importing ai/.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class IngredientOut(BaseModel):
    """One ingredient row as returned to the caller (CLI table / API JSON).

    Combines the AI module's Ingredient (name, grams, confidence) with the
    per-ingredient nutrition values already scaled to actual portion size.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    estimated_grams: float
    confidence: float
    kcal: float
    protein_g: float
    carbs_g: float
    fat_g: float


class TotalsOut(BaseModel):
    """Macro totals for the full meal."""

    model_config = ConfigDict(extra="forbid")

    kcal: float = 0.0
    protein_g: float = 0.0
    carbs_g: float = 0.0
    fat_g: float = 0.0


class AnalysisResult(BaseModel):
    """The complete result of analyzing one meal image.

    meal_recognized=False means the VLM did not find a meal in the image.
    In that case, ingredients and totals are empty — no crash, structured response.
    """

    model_config = ConfigDict(extra="forbid")

    meal_recognized: bool
    image_path: str
    ingredients: list[IngredientOut] = Field(default_factory=list)
    totals: TotalsOut = Field(default_factory=TotalsOut)

    @property
    def ingredient_count(self) -> int:
        return len(self.ingredients)


class AnalysisRecord(BaseModel):
    """Persisted history entry — one row in the PostgreSQL `analyses` table.

    id and created_at are set by the database on INSERT.
    ingredients / totals are stored as JSONB.
    """

    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    created_at: datetime | None = None
    image_path: str
    ingredients: list[IngredientOut] = Field(default_factory=list)
    totals: TotalsOut = Field(default_factory=TotalsOut)

    @classmethod
    def from_result(cls, result: AnalysisResult) -> "AnalysisRecord":
        """Build a record from an AnalysisResult (before DB insert)."""
        return cls(
            image_path=result.image_path,
            ingredients=result.ingredients,
            totals=result.totals,
        )
