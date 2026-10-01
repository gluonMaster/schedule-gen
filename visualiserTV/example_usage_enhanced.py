"""CLI entry point for the TV schedule visualizer."""

import argparse
import os
import sys

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from schedule_visualizer_enhanced import main


DEFAULT_INPUT = os.path.join("..", "visualiser", "optimized_schedule.xlsx")
DEFAULT_OUTPUT = "enhanced_schedule_visualization_tv.pdf"
LESSON_TYPE_CHOICES = ["all", "group", "individual", "nachhilfe", "trial", "non-group"]


def _register_fonts():
    try:
        pdfmetrics.registerFont(TTFont("Arial-Bold", r"c:\Windows\Fonts\arialbd.ttf"))
    except Exception:
        pass


def _parse_args():
    parser = argparse.ArgumentParser(description="Generate TV schedule visualization")
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT,
        help=f"Schedule Excel file (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Output TV PDF file (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--lesson-type",
        default="group",
        choices=LESSON_TYPE_CHOICES,
        help="Filter lessons by type (default: group)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    _register_fonts()
    args = _parse_args()

    excel_file = os.path.normpath(args.input)
    pdf_file = os.path.normpath(args.output)

    if not os.path.exists(excel_file):
        print(f"Error: input file not found: {excel_file}")
        sys.exit(1)

    try:
        main(
            excel_file,
            pdf_file,
            export_html=False,
            lesson_type_filter=args.lesson_type,
        )
        print("TV schedule visualization generated successfully.")
        print(f"Input: {excel_file}")
        print(f"Output PDF: {pdf_file}")
        print(f"Lesson type filter: {args.lesson_type}")
    except Exception as exc:
        print(f"Error while generating TV visualization: {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
