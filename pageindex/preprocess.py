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
    UnreadableInputError,
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
            "`apt-get install -y tesseract-ocr tesseract-ocr-osd tesseract-ocr-<lang>` "
            "where <lang> matches every language you pass as ocr_lang"
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


def _has_full_page_image(page) -> bool:
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
    return _has_full_page_image(page)


def _classify(pdf_bytes: bytes, doc_name: str = None):
    """Return (pdfium document, [(ordinal, text, needs_ocr, is_scan), ...]). Ordinals are 1-based.

    The document stays open: OCR renders from it afterwards. Per-page handles are closed as we
    go, because pypdfium2 holds native buffers that Python's GC does not release promptly — and
    a 36 MB scan is 51 of them.
    """
    try:
        doc = pdfium.PdfDocument(pdf_bytes)
    except Exception as e:
        # Distinguish password-protected PDFs so consumers can act on the message rather than
        # treating all unreadable PDFs identically.
        msg_lower = str(e).lower()
        if "password" in msg_lower:
            msg = f"PDF is encrypted (password-protected); provide an unlocked copy: {e}"
        else:
            msg = f"Failed to load PDF: {e}"
        raise UnreadableInputError(msg, doc_name=doc_name) from e
    classified = []
    for i, page in enumerate(doc, start=1):
        textpage = page.get_textpage()
        try:
            # get_text_bounded(), not get_text_range(): the latter warns on default params in 4.30.
            text = textpage.get_text_bounded() or ""
            # Scanners embed their own OCR layer, so a scan must be detected even when it carries
            # plenty of text: that layer is what the confidence gate has to second-guess.
            is_scan = _has_full_page_image(page)
            needs_ocr = _page_is_image(page, text)
        finally:
            textpage.close()
            page.close()
        classified.append((i, text, needs_ocr, is_scan))
    return doc, classified


OCR_DPI = 150
OCR_LANG = "eng"
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
OCR_MIN_CONFIDENCE = 70          # Tesseract mean word confidence (0-100) under which a page is "low confidence"
OCR_VISION_DPI = 150
OCR_VISION_MAX_PAGES = 10
OCR_VISION_MAX_TOKENS = 4096
OCR_VISION_PROMPT = (
    "Transcribe faithfully all text on this page, printed and handwritten, in the page's own "
    "language, preserving line order. Write [illegible] for words you cannot read. Output only "
    "the page text: no notes, comments or explanations."
)


@dataclass
class _OcrResult:
    text: str
    mean_conf: float   # mean confidence of recognised words, 0-100; 0.0 when n_words == 0
    n_words: int


def _ocr_image(image, lang: str, psm: int) -> _OcrResult:
    data = pytesseract.image_to_data(
        image, lang=lang, config=f"--psm {psm}", timeout=_OCR_TIMEOUT_SECONDS,
        output_type=pytesseract.Output.DICT,
    )
    lines: dict[tuple, list[str]] = {}
    confs: list[float] = []
    for i, word in enumerate(data["text"]):
        if not word.strip():
            continue
        conf = float(data["conf"][i])
        if conf < 0:  # -1 marks non-word boxes
            continue
        confs.append(conf)
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)
    text = "\n".join(" ".join(w) for _, w in sorted(lines.items()))
    mean_conf = sum(confs) / len(confs) if confs else 0.0
    return _OcrResult(text=text, mean_conf=mean_conf, n_words=len(confs))


def _image_to_data_url(image, quality: int = 85) -> str:
    import base64
    import io
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


async def _vision_transcribe(image, model: str, prompt: str) -> tuple[str, int, int]:
    """Return (text, input_tokens, output_tokens). Raises on any failure; caller decides."""
    import litellm
    resp = await litellm.acompletion(
        model=model,
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": _image_to_data_url(image)}},
            {"type": "text", "text": prompt},
        ]}],
        max_tokens=OCR_VISION_MAX_TOKENS,
        # no temperature: some providers (Claude 5.x on Bedrock Converse) reject it
    )
    usage = getattr(resp, "usage", None)
    return (
        resp.choices[0].message.content or "",
        int(getattr(usage, "prompt_tokens", 0) or 0),
        int(getattr(usage, "completion_tokens", 0) or 0),
    )


async def _ocr_pages(
    doc, ordinals, dpi, lang, psm, concurrency, *,
    min_confidence, vision_model, vision_dpi, vision_prompt, vision_max_pages,
):
    """OCR the given ordinals concurrently.

    Returns (results {ordinal: _OcrResult}, vision {ordinal: text}, stats). Failures are omitted.
    Pages with words but mean confidence under `min_confidence` go to the vision model when set.

    Rendering stays on the event-loop thread and ONLY Tesseract is dispatched to threads.
    pdfium is a C library that is not thread-safe: touching a PdfDocument from a thread other
    than the one that created it segfaults the interpreter — no exception, no traceback, a dead
    Lambda invocation. Measured, this costs nothing: rendering is 0.042s/page against ~0.4s for
    Tesseract, so the expensive half is still the parallel one.
    """
    _require_tesseract()
    semaphore = asyncio.Semaphore(concurrency)
    results = {}
    vision = {}
    stats = {"low_confidence": [], "vision_failed": [], "vision_seconds": 0.0,
             "in_tokens": 0, "out_tokens": 0}

    async def run(ordinal):
        async with semaphore:
            try:
                # Render inside the semaphore, not before it: otherwise every coroutine rasterizes
                # up front and the whole document sits in memory as PIL images (~6.5 MB per page at
                # 150 DPI). This bounds it to `concurrency` images. Rendering blocks the loop for
                # ~0.042s, which is why it can stay here.
                image = doc[ordinal - 1].render(scale=dpi / 72).to_pil()
                results[ordinal] = await asyncio.to_thread(_ocr_image, image, lang, psm)
                res = results[ordinal]
                if res.n_words == 0 or res.mean_conf >= min_confidence:
                    return
                stats["low_confidence"].append(ordinal)
                # Cap check is racy by at most `concurrency` pages; acceptable for a cost guard.
                if not vision_model or len(vision) + len(stats["vision_failed"]) >= vision_max_pages:
                    return
                try:
                    if vision_dpi != dpi:
                        image = doc[ordinal - 1].render(scale=vision_dpi / 72).to_pil()
                    t0 = time.perf_counter()
                    text, tin, tout = await _vision_transcribe(
                        image, vision_model, vision_prompt or OCR_VISION_PROMPT
                    )
                    stats["vision_seconds"] += time.perf_counter() - t0
                    stats["in_tokens"] += tin
                    stats["out_tokens"] += tout
                    if text.strip():
                        vision[ordinal] = text
                    else:
                        stats["vision_failed"].append(ordinal)
                except Exception as e:
                    stats["vision_failed"].append(ordinal)
                    logging.warning(f"Vision transcription failed on page {ordinal}: {e}", exc_info=True)
            except Exception as e:
                # Broad on purpose: one page must never take the document down — covers both
                # render failures (pdfium) and OCR failures (tesseract). exc_info keeps the
                # traceback so a systematic bug is still diagnosable from the logs.
                logging.warning(f"Render/OCR failed on page {ordinal}: {e}", exc_info=True)

    await asyncio.gather(*(run(o) for o in ordinals))
    stats["low_confidence"].sort()
    return results, vision, stats


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
    scan_pages: int = 0
    low_confidence_pages: list[int] = field(default_factory=list)
    vision_pages: list[int] = field(default_factory=list)
    vision_failed_pages: list[int] = field(default_factory=list)
    vision_seconds: float = 0.0
    vision_input_tokens: int = 0
    vision_output_tokens: int = 0


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
    ocr_min_confidence: int = OCR_MIN_CONFIDENCE,
    ocr_vision_model: str | None = None,
    ocr_vision_dpi: int = OCR_VISION_DPI,
    ocr_vision_prompt: str | None = None,
    ocr_vision_max_pages: int = OCR_VISION_MAX_PAGES,
) -> Normalized:
    """Normalize any supported document into per-page text.

    Always call this before `build_tree`. It decides internally, per page, whether any work is
    needed — a born-digital PDF costs one text-extraction pass and rasterizes nothing.

    source:   raw bytes, a filesystem path str, or a pathlib.Path
    filename: supplies doc_name and disambiguates the format when bytes arrive with no extension
    ocr_lang: passed verbatim to Tesseract's -l flag; the matching tesseract-ocr-<lang> pack must
              be installed in the runtime image. A wrong value degrades OCR silently — Tesseract
              returns plausible text in the correct alphabet rather than raising.
    ocr_min_confidence: Tesseract mean word confidence (0-100) under which a scanned page counts
              as low confidence (reported; sent to vision when a model is set).
    ocr_vision_model: litellm model id for the vision fallback; None (default) disables it.
    ocr_vision_dpi: render resolution for the vision call.
    ocr_vision_prompt: transcription prompt; None uses OCR_VISION_PROMPT.
    ocr_vision_max_pages: cap on vision calls per document (cost guard).

    Returns Normalized(pages, doc_name, report). `pages` is indexed by source ordinal minus one;
    a page whose OCR failed holds "" and its ordinal is listed in report.failed_pages. Page
    positions are never compacted: downstream citations reference source ordinals.

    Calls asyncio.run() internally for OCR concurrency; must not be called from inside a running
    event loop. Async callers (e.g. FastAPI routes) must offload to a thread — see client.py's
    ThreadPoolExecutor pattern.
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
    doc, classified = _classify(data, doc_name=name)
    classify_seconds = time.perf_counter() - started

    try:
        needs_ordinals = [o for o, _, needs_ocr, _ in classified if needs_ocr]
        scan_ordinals = [o for o, _, _, is_scan in classified if is_scan]
        # Scans are OCR'd too (to score them) even when their own text layer is kept.
        ocr_ordinals = [o for o, _, needs_ocr, is_scan in classified if needs_ocr or is_scan]
        ocr_results, vision_text, stats = {}, {}, None
        ocr_seconds = 0.0
        if ocr_ordinals:
            started = time.perf_counter()
            ocr_results, vision_text, stats = asyncio.run(
                _ocr_pages(
                    doc, ocr_ordinals, ocr_dpi, ocr_lang, ocr_psm, ocr_concurrency,
                    min_confidence=ocr_min_confidence, vision_model=ocr_vision_model,
                    vision_dpi=ocr_vision_dpi, vision_prompt=ocr_vision_prompt,
                    vision_max_pages=ocr_vision_max_pages,
                )
            )
            ocr_seconds = time.perf_counter() - started
            if needs_ordinals and not any(o in ocr_results for o in needs_ordinals):
                raise OCRError(
                    f"OCR failed on every one of {len(needs_ordinals)} scanned page(s)",
                    doc_name=name,
                    pages=needs_ordinals,
                )

        pages = []
        failed = []
        for ordinal, text, needs_ocr, _ in classified:
            if ordinal in vision_text:
                pages.append(vision_text[ordinal])
            elif needs_ocr:
                if ordinal in ocr_results:
                    pages.append(ocr_results[ordinal].text)
                else:
                    pages.append("")
                    failed.append(ordinal)
            else:
                pages.append(text)  # scans with a text layer keep it: output unchanged without vision

        report = PreprocessReport(
            source_format=source_format,
            page_count=len(pages),
            text_pages=len(pages) - len(needs_ordinals),
            ocr_pages=len(needs_ordinals) - len(failed),
            failed_pages=failed,
            chars_extracted=sum(len(p) for p in pages),
            convert_seconds=convert_seconds,
            classify_seconds=classify_seconds,
            ocr_seconds=ocr_seconds,
            scan_pages=len(scan_ordinals),
            low_confidence_pages=stats["low_confidence"] if stats else [],
            vision_pages=sorted(vision_text),
            vision_failed_pages=sorted(stats["vision_failed"]) if stats else [],
            vision_seconds=stats["vision_seconds"] if stats else 0.0,
            vision_input_tokens=stats["in_tokens"] if stats else 0,
            vision_output_tokens=stats["out_tokens"] if stats else 0,
        )
        return Normalized(pages=pages, doc_name=name, report=report)
    finally:
        doc.close()
