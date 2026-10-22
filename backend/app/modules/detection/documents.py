"""Signs that an ownership or authority document was edited (build plan §7).

Heuristics only, for a reviewer to weigh: editing software in the metadata, a file changed
long after it was made, several saved revisions in one PDF, text boxes typed on top.
A high score never rejects a document; it asks a person to look harder."""

import io
import re
from datetime import datetime

from PIL import Image

EDITORS = re.compile(
    rb"(photoshop|gimp|canva|ilovepdf|smallpdf|sejda|pdfescape|foxit phantom|nitro|pixlr|snapseed|picsart|"
    rb"inkscape|affinity|paint\.net|pdf-xchange|pdfelement|wondershare|microsoft\W+word)",
    re.IGNORECASE,
)
_DATE = re.compile(rb"/(CreationDate|ModDate)\s*\(D:(\d{8})")
_EOF = re.compile(rb"%%EOF")
_FREETEXT = re.compile(rb"/Subtype\s*/FreeText")
_EDITING_SOFTWARE_TAG = 305  # EXIF "Software"
_MAKE_TAG = 271


def _pdf_signals(data: bytes) -> list[tuple[float, str]]:
    signals: list[tuple[float, str]] = []
    if m := EDITORS.search(data[:200_000]) or EDITORS.search(data[-200_000:]):
        signals.append((0.45, f"Made or edited with {m.group(1).decode(errors='replace')}"))
    dates = {k.decode(): v for k, v in _DATE.findall(data)}
    if "CreationDate" in dates and "ModDate" in dates and dates["CreationDate"] != dates["ModDate"]:
        try:
            made = datetime.strptime(dates["CreationDate"].decode(), "%Y%m%d")
            changed = datetime.strptime(dates["ModDate"].decode(), "%Y%m%d")
            days = (changed - made).days
            if days > 30:
                signals.append((0.3, f"Changed {days} days after it was made"))
        except ValueError:
            pass
    revisions = len(_EOF.findall(data))
    if revisions > 1:
        signals.append((0.2 + min(revisions - 2, 3) * 0.05, f"Saved {revisions} times as edits on top of the original"))
    if _FREETEXT.search(data):
        signals.append((0.35, "Has typed text boxes placed on top of the page"))
    return signals


def _image_signals(data: bytes) -> list[tuple[float, str]]:
    signals: list[tuple[float, str]] = []
    try:
        exif = Image.open(io.BytesIO(data)).getexif()
    except Exception:  # noqa: BLE001 - unreadable images are a reviewer matter, not a crash
        return [(0.2, "The image couldn't be read")]
    software = str(exif.get(_EDITING_SOFTWARE_TAG, ""))
    if software and EDITORS.search(software.encode()):
        signals.append((0.5, f"Edited with {software[:40]}"))
    if not exif.get(_MAKE_TAG) and not software:
        signals.append((0.1, "No camera details (screenshot or re-saved copy)"))
    return signals


def tamper_score(data: bytes) -> tuple[int, list[str]]:
    """0-100, and the reasons. Signals combine like independent probabilities."""
    signals = _pdf_signals(data) if data[:5] == b"%PDF-" else _image_signals(data)
    clean = 1.0
    for weight, _ in signals:
        clean *= 1 - weight
    return round((1 - clean) * 100), [reason for _, reason in signals]
