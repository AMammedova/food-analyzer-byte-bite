"""Core analysis pipeline — the business logic of the SE layer.

WHY THIS FILE EXISTS
--------------------
This module wires together everything:

    validate → AIService.identify_ingredients → NutritionPipeline → compute_totals → result

It is intentionally separate from cli.py and api.py so that both entry
points call the same logic. "Don't repeat yourself" for the actual work.

CONCURRENCY
-----------
Nutrition lookups run concurrently via `NutritionPipeline.fetch_all_nutrition`
(asyncio.gather + bounded Semaphore + per-call retry + cache). A meal with
N ingredients takes roughly the time of a single USDA call instead of N
sequential calls.

VLM calls go through `AIService.identify_ingredients` which adds
exponential backoff retries and a per-call timeout — provider hiccups
don't blow up a request.

DEPENDENCY INJECTION
--------------------
Every collaborator is overridable via a keyword argument:

    vlm / nutrition        — provider stubs (used by CLI --offline and tests)
    ai_service / pipeline  — full service objects (used by the API to share
                             a process-wide NutritionCache across requests)

Defaults build fresh, single-request instances. That keeps the CLI and
tests simple while letting the API singleton-share cache state.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ai import Ingredient, NutritionFacts, compute_totals
from ai.nutrition import NutritionProvider, get_nutrition_provider
from ai.providers.base import ProviderError

from foodanalyzer.concurrency.pipeline import NutritionPipeline
from foodanalyzer.config import get_settings
from foodanalyzer.models import AnalysisResult, IngredientOut, TotalsOut
from foodanalyzer.services.ai_service import AIService
from foodanalyzer.services.nutrition_cache import NutritionCache
from foodanalyzer.validation import ValidationError, validate_image_path

logger = logging.getLogger(__name__)


async def analyze(
    image_path: str | Path,
    *,
    vlm=None,
    nutrition: NutritionProvider | None = None,
    ai_service: AIService | None = None,
    pipeline: NutritionPipeline | None = None,
    max_parallel: int | None = None,
) -> AnalysisResult:
    """Analyze a meal image and return structured nutrition results.

    Parameters
    ----------
    image_path:
        Path to a JPEG or PNG image file.
    vlm:
        Optional VLM provider override forwarded to the AI service.
        Pass an offline fake in tests / CLI --offline mode.
    nutrition:
        Optional NutritionProvider override. None = use USDAProvider from env.
        Pass an offline fake in tests / CLI --offline mode. Ignored when
        `pipeline` is supplied (the pipeline already owns a provider).
    ai_service:
        Optional pre-built AIService — pass one to share retry / timeout
        config across requests. Defaults to a fresh AIService().
    pipeline:
        Optional pre-built NutritionPipeline — pass one to share a
        process-wide NutritionCache across requests (the API does this in
        its lifespan handler). Defaults to a fresh pipeline with a fresh
        cache, sized by `max_parallel`.
    max_parallel:
        Maximum concurrent USDA calls when building a default pipeline.
        Defaults to `settings.max_parallel`. Ignored when `pipeline` is given.

    Returns
    -------
    AnalysisResult
        Always returns a structured result — never raises on "no meal found".

    Raises
    ------
    ValidationError
        If the image file is missing, wrong format, or too large.
    ProviderError
        If the VLM call fails after retries.
    """
    settings = get_settings()
    str_path = str(image_path)

    # --- 1. Validate image ---------------------------------------------------
    # Raises ValidationError early — before any API call.
    validated = validate_image_path(image_path, settings.max_image_size_bytes)
    logger.info("analysis_started", extra={"image_path": validated.name})

    # --- 2. Identify ingredients via VLM (retries + timeout) -----------------
    if ai_service is None:
        ai_service = AIService()

    try:
        ingredients: list[Ingredient] = await ai_service.identify_ingredients(
            str(validated), vlm=vlm
        )
    except ProviderError as exc:
        logger.error(
            "vlm_failed",
            extra={"image_path": validated.name, "error": str(exc)},
        )
        raise

    # --- 3. Unknown meal path ------------------------------------------------
    # The AI contract: empty list means meal not recognized.
    # Return structured response — no crash.
    if not ingredients:
        logger.info("no_meal_recognized", extra={"image_path": validated.name})
        return AnalysisResult(
            meal_recognized=False,
            image_path=str_path,
        )

    # --- 4. Concurrent nutrition lookup (cache + semaphore + retry) ----------
    if pipeline is None:
        provider = nutrition if nutrition is not None else get_nutrition_provider()
        cache = NutritionCache()
        pipeline = NutritionPipeline(
            provider=provider,
            cache=cache,
            max_parallel=max_parallel if max_parallel is not None else settings.max_parallel,
        )

    ingredient_names = [ing.name for ing in ingredients]
    facts_by_name_raw = await pipeline.fetch_all_nutrition(ingredient_names)

    facts_by_name: dict[str, NutritionFacts] = {
        name: facts for name, facts in facts_by_name_raw.items() if facts is not None
    }
    skipped = [name for name, facts in facts_by_name_raw.items() if facts is None]
    if skipped:
        logger.warning(
            "nutrition_missing_for_ingredients",
            extra={"ingredients": skipped, "count": len(skipped)},
        )

    # --- 5. Compute totals ---------------------------------------------------
    ai_totals = compute_totals(ingredients, facts_by_name)

    # --- 6. Build output models ----------------------------------------------
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
        "analysis_complete",
        extra={
            "image_path": validated.name,
            "ingredient_count": len(ingredient_rows),
            "kcal": round(totals.kcal),
            "missing_nutrition": len(skipped),
        },
    )

    return AnalysisResult(
        meal_recognized=True,
        image_path=str_path,
        ingredients=ingredient_rows,
        totals=totals,
    )
