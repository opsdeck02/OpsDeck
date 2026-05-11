from __future__ import annotations

from dataclasses import dataclass, field
from textwrap import wrap

PAGE_WIDTH = 595.28
PAGE_HEIGHT = 841.89
MARGIN_X = 44
TOP_Y = 794
BOTTOM_Y = 48


Color = tuple[float, float, float]

NAVY: Color = (0.04, 0.09, 0.18)
STEEL: Color = (0.10, 0.28, 0.46)
MUTED: Color = (0.36, 0.42, 0.52)
LIGHT: Color = (0.94, 0.97, 0.99)
BORDER: Color = (0.82, 0.87, 0.93)
WHITE: Color = (1, 1, 1)
RED: Color = (0.78, 0.12, 0.15)
AMBER: Color = (0.86, 0.49, 0.08)
GREEN: Color = (0.05, 0.46, 0.27)
BLUE: Color = (0.06, 0.30, 0.51)
PALE_STEEL: Color = (0.88, 0.93, 0.97)


@dataclass
class PdfDocument:
    title: str
    pages: list[list[str]] = field(default_factory=list)
    page_number: int = 0

    def __post_init__(self) -> None:
        self.new_page()

    @property
    def commands(self) -> list[str]:
        return self.pages[-1]

    def new_page(self) -> None:
        self.page_number += 1
        self.pages.append([])
        self.footer()

    def footer(self) -> None:
        self.line(MARGIN_X, 34, PAGE_WIDTH - MARGIN_X, 34, BORDER, width=0.7)
        self.rect(MARGIN_X, 18, 10, 10, fill=BLUE)
        self.polygon(
            [
                (MARGIN_X + 6.2, 27.0),
                (MARGIN_X + 2.5, 22.3),
                (MARGIN_X + 5.1, 22.3),
                (MARGIN_X + 4.5, 19.0),
                (MARGIN_X + 8.2, 24.0),
                (MARGIN_X + 5.6, 24.0),
            ],
            fill=WHITE,
        )
        self.text("OpsDeck", MARGIN_X + 16, 22, size=8, color=MUTED, bold=True)
        self.text(
            "Generated from operational data available at report time",
            112,
            22,
            size=8,
            color=MUTED,
        )
        self.text(f"Page {self.page_number}", PAGE_WIDTH - 78, 22, size=8, color=MUTED)

    def set_fill(self, color: Color) -> None:
        self.commands.append(f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg")

    def set_stroke(self, color: Color) -> None:
        self.commands.append(f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} RG")

    def rect(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        fill: Color | None = None,
        stroke: Color | None = None,
        line_width: float = 0.8,
    ) -> None:
        if fill:
            self.set_fill(fill)
        if stroke:
            self.set_stroke(stroke)
            self.commands.append(f"{line_width:.2f} w")
        op = "B" if fill and stroke else "f" if fill else "S"
        self.commands.append(f"{x:.2f} {y:.2f} {width:.2f} {height:.2f} re {op}")

    def polygon(
        self,
        points: list[tuple[float, float]],
        *,
        fill: Color,
        stroke: Color | None = None,
        line_width: float = 0.8,
    ) -> None:
        if not points:
            return
        self.set_fill(fill)
        if stroke:
            self.set_stroke(stroke)
            self.commands.append(f"{line_width:.2f} w")
        first_x, first_y = points[0]
        parts = [f"{first_x:.2f} {first_y:.2f} m"]
        parts.extend(f"{x:.2f} {y:.2f} l" for x, y in points[1:])
        parts.append("h")
        parts.append("B" if stroke else "f")
        self.commands.append(" ".join(parts))

    def line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        color: Color = BORDER,
        width: float = 0.8,
    ) -> None:
        self.set_stroke(color)
        self.commands.append(f"{width:.2f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def text(
        self,
        value: object,
        x: float,
        y: float,
        *,
        size: float = 10,
        color: Color = NAVY,
        bold: bool = False,
    ) -> None:
        font = "F2" if bold else "F1"
        self.set_fill(color)
        self.commands.append(
            f"BT /{font} {size:.2f} Tf {x:.2f} {y:.2f} Td ({escape_pdf(str(value))}) Tj ET"
        )

    def wrapped_text(
        self,
        value: object,
        x: float,
        y: float,
        *,
        width_chars: int,
        size: float = 10,
        color: Color = NAVY,
        bold: bool = False,
        leading: float = 13,
        max_lines: int | None = None,
    ) -> float:
        lines = wrap(str(value), width=width_chars) or [""]
        if max_lines is not None:
            lines = lines[:max_lines]
        current_y = y
        for line in lines:
            self.text(line, x, current_y, size=size, color=color, bold=bold)
            current_y -= leading
        return current_y

    def ensure_space(self, y: float, required: float) -> float:
        if y - required < BOTTOM_Y:
            self.new_page()
            return TOP_Y
        return y

    def build(self) -> bytes:
        objects: list[bytes] = []
        objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")

        page_count = len(self.pages)
        kids = " ".join(f"{5 + i * 2} 0 R" for i in range(page_count))
        objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode())
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

        for index, commands in enumerate(self.pages):
            page_object = 5 + index * 2
            content_object = page_object + 1
            content = "\n".join(commands).encode("latin-1", errors="replace")
            objects.append(
                (
                    f"<< /Type /Page /Parent 2 0 R "
                    f"/MediaBox [0 0 {PAGE_WIDTH:.2f} {PAGE_HEIGHT:.2f}] "
                    f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
                    f"/Contents {content_object} 0 R >>"
                ).encode()
            )
            objects.append(
                f"<< /Length {len(content)} >>\nstream\n".encode()
                + content
                + b"\nendstream"
            )

        return assemble_pdf(objects)


def assemble_pdf(objects: list[bytes]) -> bytes:
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode())
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode()
    )
    return bytes(output)


def escape_pdf(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
