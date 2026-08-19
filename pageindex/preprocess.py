"""Document normalization: Office → PDF, scanned-page detection, OCR.

Fork-owned module. Runs BEFORE tree building, because on scanned annexes the section headings
exist only as pixels: a tree built from the text layer loses the structural boundaries exactly
where the annexes begin.

This library never installs system binaries — it asserts them. See the README for the
Dockerfile lines the consumer must provide.
"""
import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import pypdfium2 as pdfium
import pytesseract

from .errors import (
    ConversionError,
    MissingSystemDependencyError,
    OCRError,
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


OCR_DPI = 150
OCR_LANG = "ita"
# psm 1 (layout analysis + orientation detection), NOT the brief's psm 6. Two measurements on
# real client documents forced this:
#   - Columns: `DUVRI DL01_Toffetti.pdf` p12 is bilingual in two columns. psm 6 and 4 interleave
#     Italian and English line by line (38-41 lines of mixed-language soup); psm 1 and 3 emit
#     each column as a block (67 lines) at the same cost. psm 6 also mangled the heading
#     "DUVRI DL01" into "x. -» DUVRI DLO1", and headings are what the tree is built from.
#   - Rotation: `Lube Duvri.pdf` pages 4-7 are scans rotated 270 degrees. `page.get_rotation()`
#     reports 0 — the rotation lives in the scanned image, not in PDF metadata — so only
#     Tesseract's OSD sees it. psm 3 returns unreadable garbage on those pages; psm 1 recovers
#     "DOCUMENTO UNICO DI VALUTAZIONE DEI RISCHI DA INTERFERENZE". Cost is ~25% more time.
# OSD requires osd.traineddata: the runtime image MUST install tesseract-ocr-osd.
OCR_PSM = 1
OCR_CONCURRENCY = 3
_OCR_TIMEOUT_SECONDS = 60


def _ocr_image(image, lang: str, psm: int) -> str:
    return pytesseract.image_to_string(
        image, lang=lang, config=f"--psm {psm}", timeout=_OCR_TIMEOUT_SECONDS
    )


async def _ocr_pages(doc, ordinals, dpi, lang, psm, concurrency):
    """OCR the given ordinals concurrently. Returns {ordinal: text} for successes only.

    Rendering stays on the event-loop thread and ONLY Tesseract is dispatched to threads.
    pdfium is a C library that is not thread-safe: touching a PdfDocument from a thread other
    than the one that created it segfaults the interpreter — no exception, no traceback, a dead
    Lambda invocation. Measured, this costs nothing: rendering is 0.042s/page against ~0.4s for
    Tesseract, so the expensive half is still the parallel one.
    """
    _require_tesseract()
    semaphore = asyncio.Semaphore(concurrency)
    results = {}

    async def run(ordinal):
        async with semaphore:
            # Render inside the semaphore, not before it: otherwise every coroutine rasterizes
            # up front and the whole document sits in memory as PIL images (~6.5 MB per page at
            # 150 DPI). This bounds it to `concurrency` images. Rendering blocks the loop for
            # ~0.042s, which is why it can stay here.
            image = doc[ordinal - 1].render(scale=dpi / 72).to_pil()
            try:
                results[ordinal] = await asyncio.to_thread(_ocr_image, image, lang, psm)
            except Exception as e:
                # Broad on purpose: one page must never take the document down. exc_info keeps
                # the traceback so a systematic bug is still diagnosable from the logs.
                logging.warning(f"OCR failed on page {ordinal}: {e}", exc_info=True)

    await asyncio.gather(*(run(o) for o in ordinals))
    return results


@dataclass
class PreprocessReport:
    source_format: str
    page_count: int
    text_pages: int
    ocr_pages: int
    failed_pages: list[int] = field(default_factory=list)
    chars_extracted: int = 0
    # Per-stage wall-clock. The consumer's own baseline found classification was ~70% of runtime
    # — a stage that produces no output, only a routing decision. Without these numbers that is
    # invisible.
    convert_seconds: float = 0.0
    classify_seconds: float = 0.0
    ocr_seconds: float = 0.0


@dataclass
class Normalized:
    pages: list[str]
    doc_name: str
    report: PreprocessReport


def _read_source(source) -> bytes:
    if isinstance(source, bytes):
        return source
    if isinstance(source, (str, Path)):
        return Path(source).read_bytes()
    raise TypeError(f"source must be bytes, str, or Path, got {type(source).__name__}")


def preprocess(
    source,
    filename: str = None,
    ocr_lang: str = OCR_LANG,
    ocr_dpi: int = OCR_DPI,
    ocr_psm: int = OCR_PSM,
    ocr_concurrency: int = OCR_CONCURRENCY,
) -> Normalized:
    """Normalize any supported document into per-page text.

    Always call this before `build_tree`. It decides internally, per page, whether any work is
    needed — a born-digital PDF costs one text-extraction pass and rasterizes nothing.

    source:   raw bytes, a filesystem path str, or a pathlib.Path
    filename: supplies doc_name and disambiguates the format when bytes arrive with no extension

    Returns Normalized(pages, doc_name, report). `pages` is indexed by source ordinal minus one;
    a page whose OCR failed holds "" and its ordinal is listed in report.failed_pages. Page
    positions are never compacted: downstream citations reference source ordinals.
    """
    data = _read_source(source)
    name = filename or (os.path.basename(str(source)) if not isinstance(source, bytes) else "Untitled")
    suffix = os.path.splitext(name)[1].lower()

    convert_seconds = 0.0
    if suffix in OFFICE_EXTENSIONS:
        source_format = suffix.lstrip(".")
        started = time.perf_counter()
        data = _convert_to_pdf(data, suffix)
        convert_seconds = time.perf_counter() - started
    elif suffix == ".pdf" or data[:5] == b"%PDF-":
        source_format = "pdf"
    else:
        raise UnsupportedFormatError(
            f"Unsupported format {suffix or '<unknown>'}; expected PDF or one of "
            f"{sorted(OFFICE_EXTENSIONS)}",
            doc_name=name,
        )

    started = time.perf_counter()
    doc, classified = _classify(data)
    classify_seconds = time.perf_counter() - started

    ocr_ordinals = [ordinal for ordinal, _, needs_ocr in classified if needs_ocr]
    ocr_text = {}
    ocr_seconds = 0.0
    if ocr_ordinals:
        started = time.perf_counter()
        ocr_text = asyncio.run(
            _ocr_pages(doc, ocr_ordinals, ocr_dpi, ocr_lang, ocr_psm, ocr_concurrency)
        )
        ocr_seconds = time.perf_counter() - started
        if not ocr_text:
            raise OCRError(
                f"OCR failed on every one of {len(ocr_ordinals)} scanned page(s)",
                doc_name=name,
                pages=ocr_ordinals,
            )

    pages = []
    failed = []
    for ordinal, text, needs_ocr in classified:
        if needs_ocr:
            if ordinal in ocr_text:
                pages.append(ocr_text[ordinal])
            else:
                pages.append("")
                failed.append(ordinal)
        else:
            pages.append(text)

    report = PreprocessReport(
        source_format=source_format,
        page_count=len(pages),
        text_pages=len(pages) - len(ocr_ordinals),
        ocr_pages=len(ocr_ordinals) - len(failed),
        failed_pages=failed,
        chars_extracted=sum(len(p) for p in pages),
        convert_seconds=convert_seconds,
        classify_seconds=classify_seconds,
        ocr_seconds=ocr_seconds,
    )
    doc.close()
    return Normalized(pages=pages, doc_name=name, report=report)
