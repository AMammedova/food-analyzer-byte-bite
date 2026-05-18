"""CLI — implement analyze command in a follow-up PR."""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Food Analyzer CLI (SE layer — under construction).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser(
        "analyze",
        help="Analyze a meal image and print nutrition totals.",
    )
    analyze.add_argument("image", help="Path to a JPEG or PNG meal photo.")

    args = parser.parse_args()

    if args.command == "analyze":
        print(
            "CLI not implemented yet. Use the provided demo meanwhile:\n"
            "  python demo_ai.py --offline --image",
            args.image,
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
