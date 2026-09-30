#!/usr/bin/env python3
"""Generate a synthetic multi-page PDF with headings, paragraphs, tables, and images.

Default target: .cache/synthetic_1000p.pdf (1000 pages).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from fpdf import FPDF
from PIL import Image, ImageDraw


def create_sample_image(image_path: Path) -> Path:
    """Generate a small PNG diagram image."""
    image_path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (300, 150), color=(240, 244, 248))
    draw = ImageDraw.Draw(img)
    # Draw simple diagram boxes
    draw.rectangle(
        [20, 30, 100, 120], outline=(40, 80, 160), width=3, fill=(210, 225, 245)
    )
    draw.text((35, 70), "Client", fill=(20, 20, 20))

    draw.line([100, 75, 180, 75], fill=(40, 80, 160), width=2)

    draw.rectangle(
        [180, 30, 280, 120], outline=(40, 160, 80), width=3, fill=(215, 245, 225)
    )
    draw.text((200, 70), "Server", fill=(20, 20, 20))

    img.save(str(image_path), "PNG")
    return image_path


def generate_synthetic_pdf(
    output_path: Path,
    total_pages: int = 1000,
) -> Path:
    """Generate a synthetic multi-page document with rich structural elements."""
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Prepare small asset image
    tmp_img_path = output_file.parent / "_synthetic_diagram.png"
    create_sample_image(tmp_img_path)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font("Helvetica", size=11)

    t0 = time.time()
    print(f"[INFO] Generating {total_pages}-page synthetic PDF at: {output_file}...")

    for page_num in range(1, total_pages + 1):
        pdf.add_page()

        # Heading 1
        pdf.set_font("Helvetica", "B", 15)
        pdf.cell(
            w=0,
            h=9,
            text=f"Chapter {page_num}: High-Performance Architecture",
            new_x="LMARGIN",
            new_y="NEXT",
        )

        # Paragraph
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(
            w=0,
            h=5,
            text=(
                f"Page {page_num} describes core principles of scalable and distributed system engineering. "
                "Resilience patterns such as circuit breakers, exponential backoff, and idempotent consumers "
                "guarantee uninterrupted service availability under substantial workloads."
            ),
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.ln(3)

        # Table every 2 pages
        if page_num % 2 == 0:
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(50, 6, "Metric Name", border=1)
            pdf.cell(50, 6, "Configured Value", border=1, new_x="LMARGIN", new_y="NEXT")

            pdf.set_font("Helvetica", "", 9)
            pdf.cell(50, 5, "Connection Pool Max", border=1)
            pdf.cell(
                50,
                5,
                f"{page_num * 10} connections",
                border=1,
                new_x="LMARGIN",
                new_y="NEXT",
            )

            pdf.cell(50, 5, "Idle Timeout", border=1)
            pdf.cell(50, 5, "300 seconds", border=1, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)

        # Image every 5 pages
        if page_num % 5 == 0 and tmp_img_path.is_file():
            pdf.image(str(tmp_img_path), x=20, w=70)
            pdf.ln(3)

        # Additional paragraph
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(
            w=0,
            h=5,
            text=(
                f"Validation and continuous integration pipelines automate regression checks for page {page_num}. "
                "Deploying immutable artifacts mitigates drift across heterogeneous computing environments."
            ),
            new_x="LMARGIN",
            new_y="NEXT",
        )

        if page_num % 200 == 0:
            elapsed = time.time() - t0
            print(
                f"[INFO] ... generated {page_num}/{total_pages} pages ({elapsed:.1f}s)"
            )

    pdf.output(str(output_file))
    elapsed = time.time() - t0
    file_size_mb = output_file.stat().st_size / (1024 * 1024)
    print(
        f"[SUCCESS] Synthetic PDF generated: {total_pages} pages, {file_size_mb:.2f} MB in {elapsed:.2f}s"
    )

    # Cleanup temporary generator asset
    if tmp_img_path.is_file():
        tmp_img_path.unlink(missing_ok=True)

    return output_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate synthetic multi-page PDF for testing scalability and memory limits.",
    )
    parser.add_argument(
        "-p",
        "--pages",
        type=int,
        default=1000,
        help="Number of pages to generate (default: 1000)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(".cache/synthetic_1000p.pdf"),
        help="Target output path (default: .cache/synthetic_1000p.pdf)",
    )

    args = parser.parse_args(argv)
    generate_synthetic_pdf(output_path=args.output, total_pages=args.pages)
    return 0


if __name__ == "__main__":
    sys.exit(main())
