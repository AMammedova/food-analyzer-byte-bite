"""Tests for SE-layer data models (foodanalyzer.models)."""

from __future__ import annotations

from foodanalyzer.models import AnalysisRecord, AnalysisResult, IngredientOut, TotalsOut


def _make_ingredient(**kwargs) -> IngredientOut:
    defaults = dict(
        name="rice",
        estimated_grams=180.0,
        confidence=0.9,
        kcal=234.0,
        protein_g=4.86,
        carbs_g=50.4,
        fat_g=0.54,
    )
    return IngredientOut(**(defaults | kwargs))


def test_ingredient_out_fields():
    ing = _make_ingredient()
    assert ing.name == "rice"
    assert ing.estimated_grams == 180.0
    assert ing.confidence == 0.9


def test_totals_out_defaults():
    t = TotalsOut()
    assert t.kcal == 0.0
    assert t.protein_g == 0.0


def test_analysis_result_meal_not_recognized():
    result = AnalysisResult(meal_recognized=False, image_path="test.jpg")
    assert result.ingredients == []
    assert result.ingredient_count == 0
    assert result.totals.kcal == 0.0


def test_analysis_result_with_ingredients():
    ing = _make_ingredient()
    totals = TotalsOut(kcal=234.0, protein_g=4.86, carbs_g=50.4, fat_g=0.54)
    result = AnalysisResult(
        meal_recognized=True,
        image_path="rice.png",
        ingredients=[ing],
        totals=totals,
    )
    assert result.ingredient_count == 1
    assert result.totals.kcal == 234.0


def test_analysis_record_from_result():
    ing = _make_ingredient()
    totals = TotalsOut(kcal=234.0, protein_g=4.86, carbs_g=50.4, fat_g=0.54)
    result = AnalysisResult(
        meal_recognized=True,
        image_path="rice.png",
        ingredients=[ing],
        totals=totals,
    )
    record = AnalysisRecord.from_result(result)
    assert record.id is None
    assert record.created_at is None
    assert record.image_path == "rice.png"
    assert len(record.ingredients) == 1
    assert record.totals.kcal == 234.0
