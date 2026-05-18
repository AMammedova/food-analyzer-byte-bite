"""CLI entry point — `python -m foodanalyzer analyze <image>`.

WHY THIS FILE
-------------
Course requirement: `python -m foodanalyzer analyze <path>` must print a
nutrition table to stdout.

`--offline` flag passes fake providers (same as demo_ai.py) so the command
works without API keys. This is what graders will use during the demo.

The actual work is done by `core.analyzer.analyze()` — the CLI only handles
argument parsing, table rendering, and exit codes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from foodanalyzer.logging_config import setup_logging
from foodanalyzer.models import AnalysisResult
from foodanalyzer.validation import ValidationError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Offline fakes (same data as demo_ai.py — kept here so CLI works standalone)
# ---------------------------------------------------------------------------

def _make_offline_providers():
    """Return (vlm, nutrition) fake providers for --offline mode."""
    import json as _json

    from ai.providers.base import ProviderError, VLMProvider
    from ai.nutrition import NutritionProvider
    from ai.schemas import NutritionFacts

    class _OfflineVLM(VLMProvider):
        KNOWN = {
            "rice":     ("white rice (cooked)",    180.0),
            "chicken":  ("grilled chicken breast", 150.0),
            "broccoli": ("broccoli",                80.0),
            "salmon":   ("salmon, baked",          140.0),
            "potato":   ("baked potato",           200.0),
            "egg":      ("boiled egg",              50.0),
            "salad":    ("mixed green salad",      100.0),
            "pasta":    ("pasta, cooked",          220.0),
            "tomato":   ("tomato, raw",             70.0),
            "cheese":   ("cheddar cheese",          30.0),
            "avocado":  ("avocado",                100.0),
            "bread":    ("white bread",             60.0),
        }

        def describe(self, image_path: str, prompt: str, *, json_schema=None) -> str:
            stem = Path(image_path).stem.lower()
            rows = []
            for kw, (name, grams) in self.KNOWN.items():
                if kw in stem:
                    rows.append({"name": name, "estimated_grams": grams, "confidence": 0.85})
            if not rows:
                return _json.dumps({"meal_recognized": False, "ingredients": []})
            return _json.dumps({"meal_recognized": True, "ingredients": rows})

    def _nf(name, kcal, protein, carbs, fat):
        return NutritionFacts(
            name=name, kcal_per_100g=kcal, protein_g_per_100g=protein,
            carbs_g_per_100g=carbs, fat_g_per_100g=fat, source="offline",
        )

    class _OfflineNutrition(NutritionProvider):
        DB = {
            "white rice (cooked)":    _nf("Rice",    130, 2.7, 28,   0.3),
            "grilled chicken breast": _nf("Chicken", 165, 31,   0,   3.6),
            "broccoli":               _nf("Broccoli", 34, 2.8,  7,   0.4),
            "salmon, baked":          _nf("Salmon",  206, 22,   0,  13.0),
            "baked potato":           _nf("Potato",   93, 2.5, 21,   0.1),
            "boiled egg":             _nf("Egg",     155, 13,   1.1, 11.0),
            "mixed green salad":      _nf("Salad",    15, 1.4,  2.9, 0.2),
            "pasta, cooked":          _nf("Pasta",   158, 5.8, 31,   0.9),
            "tomato, raw":            _nf("Tomato",   18, 0.9,  3.9, 0.2),
            "cheddar cheese":         _nf("Cheese",  403, 25,   1.3, 33.0),
            "avocado":                _nf("Avocado", 160,  2,   9,  15.0),
            "white bread":            _nf("Bread",   265,  9,  49,   3.2),
        }

        def lookup(self, ingredient_name: str) -> NutritionFacts:
            if ingredient_name not in self.DB:
                raise ProviderError(f"offline: unknown ingredient {ingredient_name!r}")
            return self.DB[ingredient_name]

    return _OfflineVLM(), _OfflineNutrition()


# ---------------------------------------------------------------------------
# Table rendering
# ---------------------------------------------------------------------------

def _render_table(result: AnalysisResult) -> str:
    """Format AnalysisResult as an aligned text table."""
    headers = ("ingredient", "g", "kcal", "protein", "carbs", "fat")
    body = []
    for ing in result.ingredients:
        body.append((
            ing.name,
            f"{ing.estimated_grams:.0f}",
            f"{ing.kcal:.0f}",
            f"{ing.protein_g:.1f}",
            f"{ing.carbs_g:.1f}",
            f"{ing.fat_g:.1f}",
        ))
    t = result.totals
    total_g = sum(i.estimated_grams for i in result.ingredients)
    body.append(("TOTAL", f"{total_g:.0f}", f"{t.kcal:.0f}",
                 f"{t.protein_g:.1f}", f"{t.carbs_g:.1f}", f"{t.fat_g:.1f}"))

    widths = [max(len(headers[i]), max((len(r[i]) for r in body), default=0))
              for i in range(len(headers))]

    sep = "-" * (sum(widths) + 2 * (len(widths) - 1))

    def fmt(row: tuple[str, ...]) -> str:
        return "  ".join(c.ljust(widths[i]) for i, c in enumerate(row))

    lines = [fmt(headers), sep]
    lines += [fmt(r) for r in body[:-1]]
    lines += [sep, fmt(body[-1])]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="foodanalyzer",
        description="Analyze a meal photo and print nutrition totals.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    analyze_cmd = sub.add_parser("analyze", help="Analyze a meal image.")
    analyze_cmd.add_argument("image", help="Path to a JPEG or PNG meal photo.")
    analyze_cmd.add_argument(
        "--offline",
        action="store_true",
        help="Use fake providers — no API keys or network required.",
    )
    analyze_cmd.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Output raw JSON instead of a table.",
    )

    args = parser.parse_args()

    setup_logging(level="INFO")

    if args.command == "analyze":
        _run_analyze(args.image, offline=args.offline, as_json=args.as_json)


def _run_analyze(image: str, *, offline: bool, as_json: bool) -> None:
    from foodanalyzer.core.analyzer import analyze

    vlm, nutrition = _make_offline_providers() if offline else (None, None)

    try:
        result: AnalysisResult = asyncio.run(
            analyze(image, vlm=vlm, nutrition=nutrition)
        )
    except ValidationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        logger.error("Analysis failed: %s", exc)
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if not result.meal_recognized:
        print("No meal recognized in the image.")
        sys.exit(0)

    if as_json:
        print(result.model_dump_json(indent=2))
    else:
        mode = "offline" if offline else "online"
        print(f"\nAnalyzing: {Path(image).name}  (mode={mode})\n")
        print(_render_table(result))


if __name__ == "__main__":
    main()
