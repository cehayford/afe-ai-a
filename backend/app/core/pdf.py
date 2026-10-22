"""A minimal, dependency-free PDF writer. Two kinds of page, both A4 and in the PDF standard fonts
(Helvetica, Helvetica-Bold, Courier), so no font files are embedded:

- `text_pdf`: plain running text (tenancy agreements and summaries), wrapped onto as many pages
  as it needs.
- `document_pdf`: a one-page receipt or invoice laid out as the "Afe Missing Features" canvas draws
  them: the Afe mark and document number, an amber rule, a facts row with a status stamp, the two
  parties, a table of items, the totals, a note, and a footer.

Money is written "GHS 3,500.00": the cedi sign isn't in the standard fonts' character set.
"""

import re
import textwrap
from dataclasses import dataclass, field

_WIDTH, _HEIGHT = 595, 842  # A4 in points
_MARGIN = 56
_LEADING = 14
_CHARS = 92  # characters per line at 10pt Helvetica


def _pdf_text(s: str) -> str:
    """Text as the standard fonts' WinAnsi encoding takes it, escaped for a PDF string."""
    s = str(s).replace("GH₵", "GHS ").replace("₵", "GHS ").replace("GHS  ", "GHS ")
    s = s.encode("cp1252", "replace").decode("latin-1")
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _write(objects: list[tuple[int, bytes]]) -> bytes:
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for oid, body in sorted(objects):
        offsets.append(len(out))
        out += f"{oid} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def text_pdf(title: str, paragraphs: list[str]) -> bytes:
    lines: list[tuple[str, int]] = [(title, 14), ("", 10)]
    for para in paragraphs:
        if not para:
            lines.append(("", 10))
            continue
        for chunk in textwrap.wrap(para, _CHARS) or [""]:
            lines.append((chunk, 10))
        lines.append(("", 10))

    per_page = (_HEIGHT - 2 * _MARGIN) // _LEADING
    pages = [lines[i : i + per_page] for i in range(0, len(lines), per_page)]

    objects: list[tuple[int, bytes]] = []
    page_ids = []
    next_id = 4
    for page in pages:
        stream = ["BT", f"/F1 10 Tf {_MARGIN} {_HEIGHT - _MARGIN} Td {_LEADING} TL"]
        for text, size in page:
            stream.append(f"/F1 {size} Tf ({_pdf_text(text)}) Tj T*")
        stream.append("ET")
        body = "\n".join(stream).encode("latin-1")
        content_id, page_id = next_id, next_id + 1
        next_id += 2
        objects.append((content_id, b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream"))
        objects.append((page_id, (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_WIDTH} {_HEIGHT}] "
                                  f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>").encode()))
        page_ids.append(page_id)
    objects += [
        (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
        (2, f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {len(page_ids)} >>".encode()),
        (3, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"),
    ]
    return _write(objects)


# --- Receipts and invoices ------------------------------------------------------------------------------

# Glyph widths (1/1000 em) of the standard fonts for printable ASCII, from their AFM files, so text can
# be right-aligned and wrapped to a width. Anything else counts as an average glyph.
_ASCII = "".join(chr(c) for c in range(32, 127))
_HELV = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556, 556,
         556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278,
         500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469,
         556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500,
         278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]
_HELV_BOLD = [278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556,
              556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611, 975, 722, 722, 722, 722, 667, 611, 778, 722,
              278, 556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333,
              584, 556, 333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389,
              556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584]
_WIDTHS = {"F1": dict(zip(_ASCII, _HELV, strict=True)), "F2": dict(zip(_ASCII, _HELV_BOLD, strict=True))}

# The design's colours (tokens from the website's app.css).
BRAND = (0x0E, 0x4A, 0x3E)
AMBER = (0xD9, 0x96, 0x1A)
INK = (0x15, 0x21, 0x1E)
MUTED = (0x56, 0x66, 0x5F)
LINE = (0xD5, 0xDF, 0xDB)
TINT = (0xE7, 0xF0, 0xEC)
WHITE = (0xFF, 0xFF, 0xFF)
TONES = {  # status stamp: (background, text)
    "ok": ((0xE3, 0xF4, 0xEA), (0x16, 0x79, 0x4C)),
    "warn": ((0xFD, 0xF3, 0xDE), (0x9A, 0x62, 0x00)),
    "bad": ((0xFD, 0xEC, 0xEA), (0xB4, 0x23, 0x18)),
    "quiet": (TINT, MUTED),
}


def text_width(text: str, size: float, font: str = "F1", spacing: float = 0.0) -> float:
    """Width in points of `text` in Helvetica (F1), Helvetica-Bold (F2) or Courier (F3)."""
    text = _pdf_text(text).replace("\\(", "(").replace("\\)", ")").replace("\\\\", "\\")
    if font == "F3":
        return len(text) * 0.6 * size + spacing * len(text)
    table = _WIDTHS[font]
    return sum(table.get(ch, 556) for ch in text) * size / 1000 + spacing * len(text)


def wrap(text: str, size: float, width: float, font: str = "F1") -> list[str]:
    lines: list[str] = []
    for para in str(text).split("\n"):
        line = ""
        for word in para.split():
            trial = f"{line} {word}".strip()
            if line and text_width(trial, size, font) > width:
                lines.append(line)
                line = word
            else:
                line = trial
        lines.append(line)
    return lines


@dataclass
class DocItem:
    description: str
    amount: str
    detail: str = ""  # a smaller second line under the description
    middle: str = ""  # the middle column (months, quantity, or when and a reference)


@dataclass
class Document:
    """One receipt or invoice page. `kind` is RECEIPT or INVOICE."""

    kind: str
    number: str
    facts: list[tuple[str, str]]  # up to three (label, value) cells before the status
    status: tuple[str, str]  # (text, tone: ok | warn | bad | quiet)
    parties: list[tuple[str, str, str]]  # two (label, name, detail)
    middle_label: str
    items: list[DocItem]
    total: tuple[str, str]  # (label, amount)
    total_tone: str = "brand"  # brand (paid) or amber (due)
    summary: list[tuple[str, str]] = field(default_factory=list)
    note_title: str = ""
    note: str = ""
    footer: str = ""
    middle_width: float = 60


class _Canvas:
    """Drawing operations for one page, with y measured from the top of the page like the design."""

    def __init__(self) -> None:
        self.ops: list[str] = []

    @staticmethod
    def _rgb(c: tuple[int, int, int]) -> str:
        return " ".join(f"{v / 255:.4f}" for v in c)

    def rect(self, x: float, y: float, w: float, h: float, fill: tuple[int, int, int]) -> None:
        self.ops.append(f"{self._rgb(fill)} rg {x:.2f} {_HEIGHT - y - h:.2f} {w:.2f} {h:.2f} re f")

    def line(self, x1: float, y1: float, x2: float, y2: float, color=LINE, width: float = 0.75) -> None:
        self.ops.append(f"{self._rgb(color)} RG {width} w {x1:.2f} {_HEIGHT - y1:.2f} m {x2:.2f} {_HEIGHT - y2:.2f} l S")

    def round_rect(self, x: float, y: float, w: float, h: float, r: float, fill) -> None:
        k = 0.5523 * r
        top, bottom = _HEIGHT - y, _HEIGHT - y - h
        self.ops.append(
            f"{self._rgb(fill)} rg {x + r:.2f} {top:.2f} m {x + w - r:.2f} {top:.2f} l "
            f"{x + w - r + k:.2f} {top:.2f} {x + w:.2f} {top - r + k:.2f} {x + w:.2f} {top - r:.2f} c "
            f"{x + w:.2f} {bottom + r:.2f} l {x + w:.2f} {bottom + r - k:.2f} {x + w - r + k:.2f} {bottom:.2f} {x + w - r:.2f} {bottom:.2f} c "
            f"{x + r:.2f} {bottom:.2f} l {x + r - k:.2f} {bottom:.2f} {x:.2f} {bottom + r - k:.2f} {x:.2f} {bottom + r:.2f} c "
            f"{x:.2f} {top - r:.2f} l {x:.2f} {top - r + k:.2f} {x + r - k:.2f} {top:.2f} {x + r:.2f} {top:.2f} c f"
        )

    def polyline(self, points: list[tuple[float, float]], color, width: float) -> None:
        path = " ".join(f"{x:.2f} {_HEIGHT - y:.2f} {'m' if i == 0 else 'l'}" for i, (x, y) in enumerate(points))
        self.ops.append(f"{self._rgb(color)} RG {width} w 1 J 1 j {path} S 0 J 0 j")

    def text(self, x: float, baseline: float, text: str, size: float, font: str = "F1", color=INK,
             align: str = "left", spacing: float = 0.0) -> None:
        w = text_width(text, size, font, spacing)
        if align == "right":
            x -= w
        elif align == "center":
            x -= w / 2
        tc = f" {spacing} Tc" if spacing else ""
        reset = " 0 Tc" if spacing else ""
        self.ops.append(f"BT {self._rgb(color)} rg /{font} {size} Tf{tc} {x:.2f} {_HEIGHT - baseline:.2f} Td ({_pdf_text(text)}) Tj{reset} ET")

    def mark(self, x: float, y: float, size: float) -> None:
        """The Afe mark: a brand tile, an amber roof and a white "a" (the design's variant c)."""
        s = size / 100
        self.round_rect(x, y, size, size, 24 * s, BRAND)
        self.polyline([(x + 28 * s, y + 34 * s), (x + 50 * s, y + 22 * s), (x + 72 * s, y + 34 * s)], AMBER, 7 * s)
        self.text(x + 50 * s, y + 81 * s, "a", 58 * s, "F2", WHITE, align="center")


def document_pdf(doc: Document) -> bytes:
    c = _Canvas()
    left, right = _MARGIN, _WIDTH - _MARGIN
    label = dict(size=6.75, spacing=0.7, color=MUTED)

    # Header: the mark and wordmark, the document kind and number.
    c.mark(left, 42, 33)
    c.text(left + 42, 62, "afe", 21, "F2")
    c.text(left + 42, 74, "Verified rentals in Accra", 8.25, color=MUTED)
    c.text(right, 62, doc.kind, 19.5, "F2", BRAND, align="right", spacing=0.8)
    c.text(right, 76, doc.number, 9.75, "F3", align="right")
    c.rect(left, 90, right - left, 3, AMBER)

    # Facts row: up to three facts, then the status stamp; hairlines between cells.
    cell = (right - left) / 4
    for i, (name, value) in enumerate(doc.facts[:3]):
        x = left + i * cell + (9 if i else 0)
        c.text(x, 115, name.upper(), **label)
        c.text(x, 131, value, 10.5, "F2")
    sx = left + 3 * cell + 9
    c.text(sx, 115, "STATUS", **label)
    bg, fg = TONES.get(doc.status[1], TONES["quiet"])
    stamp = doc.status[0].upper()
    c.round_rect(sx, 120, text_width(stamp, 9, "F2") + 12, 16, 3, bg)
    c.text(sx + 6, 131.5, stamp, 9, "F2", fg)
    for i in range(1, 4):
        c.line(left + i * cell, 104, left + i * cell, 140)
    c.line(left, 148, right, 148)

    # Parties.
    half = (right - left) / 2
    for i, (name, who, detail) in enumerate(doc.parties[:2]):
        x = left + i * (half + 9)
        c.text(x, 170, name.upper(), **label)
        c.text(x, 186, who, 11.25, "F2")
        for j, part in enumerate(wrap(detail, 9, half - 12)[:2]):
            c.text(x, 199 + j * 11, part, 9, color=MUTED)

    # Items table.
    y = 226
    amount_w, middle_w = 105, doc.middle_width
    mid_x = right - amount_w - middle_w
    c.rect(left, y, right - left, 21, TINT)
    c.line(left, y, right, y)
    c.line(left, y + 21, right, y + 21)
    c.text(left + 7.5, y + 13.5, "DESCRIPTION", **label)
    c.text(mid_x + 7.5, y + 13.5, doc.middle_label.upper(), **label)
    c.text(right - 7.5, y + 13.5, "AMOUNT", **label, align="right")
    y += 21
    for item in doc.items[:12]:
        lines = wrap(item.description, 9.75, mid_x - left - 15)
        details = wrap(item.detail, 8.25, mid_x - left - 15) if item.detail else []
        middle = item.middle.splitlines() or [""]
        height = max(12 + 12 * len(lines) + 11 * len(details), 12 + 11 * len(middle)) + 4
        for j, part in enumerate(lines):
            c.text(left + 7.5, y + 18 + j * 12, part, 9.75)
        for j, part in enumerate(details):
            c.text(left + 7.5, y + 18 + 12 * len(lines) + j * 11 - 1, part, 8.25, color=MUTED)
        for j, part in enumerate(middle[:3]):
            reference = re.fullmatch(r"[A-Z0-9][A-Z0-9-]{4,}", part) is not None
            c.text(mid_x + 7.5, y + 18 + j * 11, part, 9.75 if len(middle) == 1 else 8.25, "F3" if reference else "F1",
                   MUTED if j else INK)
        c.text(right - 7.5, y + 18, item.amount, 9.75, align="right")
        y += height
        c.line(left, y, right, y)

    # Totals: summary lines, then the total bar (brand when paid, amber when due).
    y += 14
    box_x = right - 240
    for name, value in doc.summary:
        c.text(box_x + 7.5, y + 10, name, 9.75)
        c.text(right - 7.5, y + 10, value, 9.75, align="right")
        y += 17
    y += 4
    fill, ink = (BRAND, WHITE) if doc.total_tone == "brand" else (AMBER, INK)
    c.rect(box_x, y, 240, 30, fill)
    c.text(box_x + 7.5, y + 19.5, doc.total[0], 12, "F2", ink)
    c.text(right - 7.5, y + 19.5, doc.total[1], 12, "F2", ink, align="right")
    y += 30

    # Note.
    if doc.note:
        y += 26
        c.text(left, y, doc.note_title.upper(), **label)
        for j, part in enumerate(wrap(doc.note, 9, right - left)[:8]):
            c.text(left, y + 16 + j * 13.5, part, 9)

    # Footer.
    c.line(left, _HEIGHT - 58, right, _HEIGHT - 58)
    c.text(left, _HEIGHT - 44, doc.footer, 7.5, color=MUTED)
    c.text(right, _HEIGHT - 44, "Page 1 of 1", 7.5, color=MUTED, align="right")

    body = "\n".join(c.ops).encode("latin-1")
    fonts = "<< /F1 5 0 R /F2 6 0 R /F3 7 0 R >>"
    return _write([
        (1, b"<< /Type /Catalog /Pages 2 0 R >>"),
        (2, b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>"),
        (3, b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream"),
        (4, (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {_WIDTH} {_HEIGHT}] "
             f"/Resources << /Font {fonts} >> /Contents 3 0 R >>").encode()),
        (5, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"),
        (6, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"),
        (7, b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>"),
    ])


def ghs(pesewas: int) -> str:
    """Money for documents: 350000 -> "GHS 3,500.00"."""
    cedis, rem = divmod(int(pesewas), 100)
    return f"GHS {cedis:,}.{rem:02d}"
