"""Core analysis pipeline — the business logic of the SE layer.

WHY THIS FILE EXISTS
--------------------
This module wires together everything:

    validate → identify_ingredients → nutrition lookup → compute_totals → result

It is intentionally separate from cli.py and api.py so that both entry
points call the same logic. "Don't repeat yourself" for the actual work.

CONCURRENCY NOTE
----------------
Nutrition lookups are currently sequential (one after another).
When gulnur/service-cache-pipeline is merged, replace the sequential loop
with:

    from foodanalyzer.concurrency.pipeline import fetch_all_nutrition
    facts = await fetch_all_nutrition(names, cache, provider, max_parallel)

The function signature of `analyze()` is already async for this reason.

DEPENDENCY INJECTION
--------------------
`vlm` and `nutrition` parameters default to None = "use real providers from
env". Tests and the CLI `--offline` flag pass fake providers explicitly.
This avoids any network calls in tests.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ai import Ingredient, NutritionFacts, compute_totals, identify_ingredients
from ai.nutrition import NutritionProvider, get_nutrition_provider
from ai.providers.base import ProviderError

from foodanalyzer.models import AnalysisResult, IngredientOut, TotalsOut
from foodanalyzer.validation import ValidationError, validate_image_path
from foodanalyzer.config import get_settings

logger = logging.getLogger(__name__)


async def analyze(
    image_path: str | Path,
    *,
    vlm=None,
    nutrition: NutritionProvider | None = None,
) -> AnalysisResult:
    """Analyze a meal image and return structured nutrition results.

    Parameters
    ----------
    image_path:
        Path to a JPEG or PNG image file.
    vlm:
        Optional VLM provider override. None = use env-configured provider.
        Pass an offline fake in tests / CLI --offline mode.
    nutrition:
        Optional NutritionProvider override. None = use USDAProvider from env.
        Pass an offline fake in tests / CLI --offline mode.

    Returns
    -------
    AnalysisResult
        Always returns a structured result — never raises on "no meal found".

    Raises
    ------
    ValidationError
        If the image file is missing, wrong format, or too large.
    ProviderError
        If the VLM call fails after retries (wrapping added in ai_service PR).
    """
    settings = get_settings()
    str_path = str(image_path)

    # --- 1. Validate image ---------------------------------------------------
    # Raises ValidationError early — before any API call.
    validated = validate_image_path(image_path, settings.max_image_size_bytes)
    logger.info("Analyzing image: %s", validated.name)

    # --- 2. Identify ingredients via VLM ------------------------------------
    try:
        ingredients: list[Ingredient] = identify_ingredients(str(validated), vlm=vlm)
    except ProviderError as exc:
        logger.error("VLM failed for %s: %s", validated.name, exc)
        raise

    # --- 3. Unknown meal path -----------------------------------------------
    # The AI contract: empty list means meal not recognized.
    # Return structured response — no crash.
    if not ingredients:
        logger.info("No meal recognized in %s", validated.name)
        return AnalysisResult(
            meal_recognized=False,
            image_path=str_path,
        )

    # --- 4. Nutrition lookup (sequential for now) ----------------------------
    # TODO: replace with fetch_all_nutrition() once pipeline PR is merged.
    if nutrition is None:
        nutrition = get_nutrition_provider()

    facts_by_name: dict[str, NutritionFacts] = {}
    skipped: list[str] = []

    for ing in ingredients:
        try:
            facts_by_name[ing.name] = nutrition.lookup(ing.name)
            logger.debug("Nutrition found: %s", ing.name)
        except ProviderError as exc:
            logger.warning("Skipping %r — nutrition lookup failed: %s", ing.name, exc)
            skipped.append(ing.name)

    if skipped:
        logger.warning("Could not find nutrition for: %s", ", ".join(skipped))

    # --- 5. Compute totals ---------------------------------------------------
    ai_totals = compute_totals(ingredients, facts_by_name)

    # --- 6. Build output models ---------------------------------------------
    ingredient_rows: list[IngredientOut] = []
    for ing in ingredients:
        facts = facts_by_name.get(ing.name)
        if facts is None:
            per_ing_nutrition = TotalsOut()
        else:
            n = facts.for_grams(ing.estimated_grams)
            per_ing_nutrition = TotalsOut(
                kcal=n.kcal,
                protein_g=n.protein_g,
                carbs_g=n.carbs_g,
                fat_g=n.fat_g,
            )
        ingredient_rows.append(
            IngredientOut(
                name=ing.name,
                estimated_grams=ing.estimated_grams,
                confidence=ing.confidence,
                kcal=per_ing_nutrition.kcal,
                protein_g=per_ing_nutrition.protein_g,
                carbs_g=per_ing_nutrition.carbs_g,
                fat_g=per_ing_nutrition.fat_g,
            )
        )

    totals = TotalsOut(
        kcal=ai_totals.kcal,
        protein_g=ai_totals.protein_g,
        carbs_g=ai_totals.carbs_g,
        fat_g=ai_totals.fat_g,
    )

    logger.info(
        "Analysis complete: %d ingredients, %.0f kcal",
        len(ingredient_rows),
        totals.kcal,
    )

    return AnalysisResult(
        meal_recognized=True,
        image_path=str_path,
        ingredients=ingredient_rows,
        totals=totals,
    )
