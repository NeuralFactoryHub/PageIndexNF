"""Document normalization: Office → PDF, scanned-page detection, OCR.

Fork-owned module. Runs BEFORE tree building, because on scanned annexes the section headings
exist only as pixels: a tree built from the text layer loses the structural boundaries exactly
where the annexes begin.

This library never installs system binaries — it asserts them. See the README for the
Dockerfile lines the consumer must provide.
"""
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pypdfium2 as pdfium

from .errors import (
    ConversionError,
    MissingSystemDependencyError,
    UnsupportedFormatError,
)

OFFICE_EXTENSIONS = {".doc", ".docx", ".odt", ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".odp"}

# Resolution order matters: `libreoffice` and `soffice` are the Linux names, the third is the
# macOS app bundle, which is not on PATH.
_SOFFICE_CANDIDATES = (
    "libreoffice",
    "soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
)


def _find_soffice() -> str:
    for candidate in _SOFFICE_CANDIDATES:
        resolved = shutil.which(candidate) or (candidate if os.path.isfile(candidate) else None)
        if resolved:
            return resolved
    raise MissingSystemDependencyError(
        "LibreOffice not found. Install it in the runtime image: "
        "`apt-get install -y libreoffice`"
    )


def _require_tesseract() -> None:
    if shutil.which("tesseract") is None:
        raise MissingSystemDependencyError(
            "tesseract not found. Install it in the runtime image: "
            "`apt-get install -y tesseract-ocr tesseract-ocr-ita tesseract-ocr-osd`"
        )


_CONVERSION_TIMEOUT_SECONDS = 120


def _convert_to_pdf(data: bytes, suffix: str) -> bytes:
    """Render an Office document to PDF via LibreOffice headless.

    Conversion is needed for pagination, not fidelity: PageIndex cites by page number and a
    .docx has no pages until something lays it out.
    """
    soffice = _find_soffice()
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"input{suffix}"
        src.write_bytes(data)
        try:
            result = subprocess.run(
                # --norestore matters: without it a previously crashed instance hangs the
                # conversion on a recovery dialog nobody will ever answer.
                # -env:UserInstallation isolates the profile: warm Lambda invocations share
                # /tmp, and two concurrent conversions would otherwise contend for one profile.
                [soffice,
                 f"-env:UserInstallation=file://{tmp}/lo_profile",
                 "--headless", "--norestore", "--convert-to", "pdf",
                 "--outdir", tmp, str(src)],
                capture_output=True,
                timeout=_CONVERSION_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as e:
            raise ConversionError(
                f"LibreOffice timed out after {_CONVERSION_TIMEOUT_SECONDS}s"
            ) from e

        out = src.with_suffix(".pdf")
        # LibreOffice can exit 0 and produce nothing, so the return code alone is not evidence.
        if result.returncode != 0 or not out.exists():
            raise ConversionError(
                f"LibreOffice failed (exit {result.returncode}): "
                f"{result.stderr.decode(errors='replace')[:500]}"
            )
        return out.read_bytes()


MIN_CHARS_PER_PAGE = 50
# A page with an almost-full-page image AND little text is a scan carrying a stamped footer.
# The text gate is essential: without it, born-digital pages with full-page figures get sent to
# OCR, which then REPLACES their perfect text layer with degraded OCR output. Measured on
# examples/documents/PRML.pdf: 55 false positives without the gate, 0 with it.
SUSPICIOUS_CHARS_PER_PAGE = 250
IMAGE_AREA_RATIO = 0.5


def _page_is_image(page, text: str) -> bool:
    """Decide whether a page needs OCR.

    Character count alone cannot separate "page with 60 characters of real content" from
    "scanned page with a 60-character DMS footer stamped on top", and the corpus is full of the
    latter. The second signal — a near-full-page image on a text-poor page — catches it.
    """
    chars = len(text.strip())
    if chars < MIN_CHARS_PER_PAGE:
        return True
    if chars >= SUSPICIOUS_CHARS_PER_PAGE:
        return False
    page_area = page.get_width() * page.get_height()
    if page_area <= 0:
        return False
    # max_depth=4: scanned pages often nest the image inside form XObjects, below pypdfium2's
    # default depth of 2.
    for obj in page.get_objects(filter=(pdfium.raw.FPDF_PAGEOBJ_IMAGE,), max_depth=4):
        left, bottom, right, top = obj.get_pos()
        if abs(right - left) * abs(top - bottom) >= IMAGE_AREA_RATIO * page_area:
            return True
    return False


def _classify(pdf_bytes: bytes):
    """Return (pdfium document, [(ordinal, text, needs_ocr), ...]). Ordinals are 1-based.

    The document stays open: OCR renders from it afterwards. Per-page handles are closed as we
    go, because pypdfium2 holds native buffers that Python's GC does not release promptly — and
    a 36 MB scan is 51 of them.
    """
    doc = pdfium.PdfDocument(pdf_bytes)
    classified = []
    for i, page in enumerate(doc, start=1):
        textpage = page.get_textpage()
        try:
            # get_text_bounded(), not get_text_range(): the latter warns on default params in 4.30.
            text = textpage.get_text_bounded() or ""
            needs_ocr = _page_is_image(page, text)
        finally:
            textpage.close()
            page.close()
        classified.append((i, text, needs_ocr))
    return doc, classified
