"""Photo processing: check it is a real image, strip all metadata, resize, re-encode as
WebP, and compute perceptual hashes for duplicate detection.

This is the Python reference implementation. STACK-001's Rust module replaces it only
if the plan's §16 trigger fires (photo processing p95 over 2 s after tuning)."""

import io
from dataclasses import dataclass

import imagehash
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.errors import InvalidInput

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_EDGE = 1600

Image.MAX_IMAGE_PIXELS = MAX_PIXELS


@dataclass(frozen=True)
class ProcessedPhoto:
    webp: bytes
    width: int
    height: int
    phash: str
    dhash: str


def process_photo(raw: bytes) -> ProcessedPhoto:
    if len(raw) > MAX_UPLOAD_BYTES:
        raise InvalidInput("Photo is larger than 15 MB.")
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            probe.verify()
        image = Image.open(io.BytesIO(raw))
        image = ImageOps.exif_transpose(image)  # respect camera rotation before metadata is dropped
        image = image.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise InvalidInput("File is not a readable photo.") from exc

    image.thumbnail((MAX_EDGE, MAX_EDGE))
    # Copying only the pixels drops EXIF, GPS and every other metadata block, so a
    # landlord's location or phone model is never published.
    clean = Image.new("RGB", image.size)
    clean.paste(image)

    out = io.BytesIO()
    clean.save(out, format="WEBP", quality=82, method=4)
    return ProcessedPhoto(
        webp=out.getvalue(),
        width=clean.width,
        height=clean.height,
        phash=str(imagehash.phash(clean)),
        dhash=str(imagehash.dhash(clean)),
    )


def hamming(hex_a: str, hex_b: str) -> int:
    return bin(int(hex_a, 16) ^ int(hex_b, 16)).count("1")
