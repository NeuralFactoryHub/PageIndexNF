# Document Preprocessing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: use executing-plans skill to implement this plan task-by-task.

**Goal:** Add a `preprocess()` stage to the fork that converts Office files to PDF, detects scanned pages, OCRs them, and hands page texts to `build_tree` — so non-searchable and non-PDF documents stop indexing as silently empty.

**Architecture:** Two explicit public calls. `preprocess()` normalizes any supported input into `Normalized(pages, doc_name, report)`; `build_tree(pages=...)` builds the tree from those texts. New code lives in fork-owned modules (`preprocess.py`, `errors.py`) so upstream merges stay clean; edits to upstream files are minimal and listed per task. Every failure mode that is currently silent becomes a typed exception.

**Tech Stack:** Python ≥3.10, `pypdfium2` (already present) for text extraction and rasterization, `pytesseract` + system `tesseract-ocr` for OCR, LibreOffice headless for Office→PDF, `Pillow` as the image bridge.

**Design:** `docs/plans/2026-08-19-preprocessing/design.md`
**Branch:** `feature/preprocessing` (already created, cut from `feature/customizations`)
**Reference skill:** @backend-python for Python patterns in this repo.

**Consumer runtime (confirmed from its `serverless.yml`):** container-image Lambda
(`provider.ecr.images.fastapi` → `backend/Dockerfile`), `memorySize: 4096` (~2.3 vCPU),
`timeout: 890`, `ephemeralStorageSize: 1024` (1 GB of `/tmp`), `HOME: /tmp`, Bedrock in
`eu-west-1`. The `HOME: /tmp` line is load-bearing for LibreOffice, which needs a writable home.

**Repo rules that apply to every task:**
- Do NOT write tests (project rule). Verification is via imports, `python -c` smoke checks, and manual runs.
- Commit after each task using `@gh-commit` (conventional commits).
- Never commit to `feature/customizations`.
- Code and comments in English. Comments explain *why*, sparingly.

---

## Task 1: Error taxonomy

**Files:**
- Create: `pageindex/errors.py`

**Step 1: Create the module**

```python
"""Typed errors for the fork.

Upstream raises bare `Exception` and, in the LLM retry loop, returns "" on exhaustion. Both
collapse unrelated causes into one indistinguishable symptom, so a caller cannot tell a broken
document from a throttled model and cannot decide whether retrying is sensible. These types make
that distinction part of the public contract: only `LLMUnavailableError` is worth a retry.
"""


class PageIndexError(Exception):
    """Base for every error raised by this library."""

    def __init__(self, message: str, doc_name: str = None, pages: list[int] = None):
        self.doc_name = doc_name
        self.pages = pages
        context = []
        if doc_name:
            context.append(f"doc={doc_name!r}")
        if pages:
            context.append(f"pages={pages}")
        super().__init__(f"{message} ({', '.join(context)})" if context else message)


# (a) The input itself cannot be read. Never retry; the caller must fix the document.
class UnreadableInputError(PageIndexError):
    pass


class UnsupportedFormatError(UnreadableInputError):
    pass


class ConversionError(UnreadableInputError):
    pass


class OCRError(UnreadableInputError):
    pass


class NotPreprocessedError(UnreadableInputError):
    pass


class MissingSystemDependencyError(PageIndexError):
    """A required system binary (tesseract, soffice) is absent from the runtime."""


# (b) The model call failed. Transport/throttling is retryable; misconfiguration never is.
class LLMUnavailableError(PageIndexError):
    """Throttling or transport failure. THIS IS THE ONLY ERROR A CALLER SHOULD RETRY."""


class LLMConfigError(PageIndexError):
    """Rejected key, missing model, forbidden access. No retry can fix it."""


# (c) The model answered but the structure could not be built from the answer.
class TreeParseError(PageIndexError):
    pass
```

**Step 2: Verify**

```bash
python -c "from pageindex.errors import LLMUnavailableError as E; \
e = E('throttled', doc_name='a.pdf', pages=[3]); print(e)"
```

Expected: `throttled (doc='a.pdf', pages=[3])`

---

## Task 2: Make the telemetry path configurable

`JsonLogger.__init__` calls `os.makedirs("./logs")` unconditionally on every `page_index_main` call. On Lambda the filesystem is read-only outside `/tmp`, so this crashes before a single page is processed.

**Files:**
- Modify: `pageindex/config.py`
- Modify: `pageindex/utils.py:346-355` (`get_pdf_name`), `:358-395` (`JsonLogger`)
- Modify: `pageindex/page_index.py:1237`

**Step 1: Add the config key**

In `pageindex/config.py`, add to `DEFAULT_CONFIG`:

```python
    "log_dir": None,         # None = telemetry off; set a writable path to enable (e.g. "/tmp/pageindex")
```

**Step 2: Make `get_pdf_name` total**

`pageindex/utils.py` — the function currently falls through to an unbound local when `pdf_path` is neither `str` nor `BytesIO`:

```python
def get_pdf_name(pdf_path):
    # Extract PDF name
    if isinstance(pdf_path, str):
        pdf_name = os.path.basename(pdf_path)
    elif isinstance(pdf_path, BytesIO):
        pdf_reader = PyPDF2.PdfReader(pdf_path)
        meta = pdf_reader.metadata
        pdf_name = meta.title if meta and meta.title else 'Untitled'
        pdf_name = sanitize_filename(pdf_name)
    else:
        pdf_name = 'Untitled'
    return pdf_name
```

**Step 3: Rewrite `JsonLogger` to honour `log_dir`**

Replace the class in `pageindex/utils.py`:

```python
class JsonLogger:
    def __init__(self, file_path, log_dir=None):
        # No log_dir means telemetry is off: keep the same API but never touch the filesystem,
        # which is read-only outside /tmp on Lambda.
        self.log_dir = log_dir
        self.log_data = []
        pdf_name = get_pdf_name(file_path)
        current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filename = f"{pdf_name}_{current_time}.json"
        if self.log_dir:
            os.makedirs(self.log_dir, exist_ok=True)

    def log(self, level, message, **kwargs):
        if isinstance(message, dict):
            self.log_data.append(message)
        else:
            self.log_data.append({'message': message})
        if not self.log_dir:
            return
        with open(self._filepath(), "w") as f:
            json.dump(self.log_data, f, indent=2)

    def info(self, message, **kwargs):
        self.log("INFO", message, **kwargs)

    def error(self, message, **kwargs):
        self.log("ERROR", message, **kwargs)

    def debug(self, message, **kwargs):
        self.log("DEBUG", message, **kwargs)

    def exception(self, message, **kwargs):
        kwargs["exception"] = True
        self.log("ERROR", message, **kwargs)

    def _filepath(self):
        return os.path.join(self.log_dir, self.filename)
```

**Step 4: Pass the config through**

In `pageindex/page_index.py`, line 1237:

```python
    logger = JsonLogger(doc, log_dir=getattr(opt, 'log_dir', None))
```

**Step 5: Verify no directory is created**

Make sure no `./logs` directory exists first (move it aside if it does), then:

```bash
python -c "
from pageindex.utils import JsonLogger
lg = JsonLogger('x.pdf'); lg.info({'a': 1}); print('ok', lg.log_data)
import os; print('logs dir created:', os.path.exists('./logs'))"
```

Expected: `ok [{'a': 1}]` and `logs dir created: False`

**Step 6: Verify it still writes when asked**

```bash
python -c "
from pageindex.utils import JsonLogger
lg = JsonLogger('x.pdf', log_dir='/tmp/pi-test'); lg.info({'a': 1})
import glob; print(glob.glob('/tmp/pi-test/*.json'))"
```

Expected: one JSON file listed.

---

## Task 3: Typed, backed-off LLM retries

Today both functions retry 10 times with a flat 1s sleep and **return `""`** on exhaustion. That empty string flows downstream until the tree parser gives up, so a transient throttle is reported as a broken document.

**Files:**
- Modify: `pageindex/utils.py:68-115` (`_is_unrecoverable`, `llm_completion`), `:119-160` (`llm_acompletion`)

**Step 1: Add imports and the backoff helper**

Near the top of `pageindex/utils.py`, add:

```python
import random
```

and, just below `_is_unrecoverable`:

```python
_MAX_BACKOFF_SECONDS = 30


def _backoff_seconds(attempt: int) -> float:
    """Exponential backoff with full jitter.

    A flat sleep sends N requests into the same congestion window; jitter spreads retries from
    concurrent page tasks so they stop arriving in lockstep.
    """
    return random.uniform(0, min(2 ** attempt, _MAX_BACKOFF_SECONDS))
```

**Step 2: Raise instead of returning `""` (sync)**

In `llm_completion`, replace the `except` block:

```python
        except Exception as e:
            if _is_unrecoverable(e):
                raise LLMConfigError(f"LLM rejected the request: {e}") from e
            logging.error(f"LLM call failed (attempt {i + 1}/{max_retries}): {e}")
            if i < max_retries - 1:
                time.sleep(_backoff_seconds(i))
            else:
                raise LLMUnavailableError(
                    f"LLM unavailable after {max_retries} attempts: {e}"
                ) from e
```

Delete the `return "", "error"` / `return ""` lines that followed, and drop the
`print('************* Retrying *************')` line.

**Step 3: Same change for `llm_acompletion`**

Identical block, with `await asyncio.sleep(_backoff_seconds(i))` instead of `time.sleep`.

**Step 4: Import the errors**

At the top of `pageindex/utils.py`:

```python
from .errors import LLMConfigError, LLMUnavailableError
```

**Step 5: Verify the raise path**

```bash
python -c "
import pageindex.utils as u
u._MAX_BACKOFF_SECONDS = 0
try:
    u.llm_completion('bedrock/nonexistent-model-xyz', 'hi')
except Exception as e:
    print(type(e).__name__, '-', e)"
```

Expected: `LLMConfigError` or `LLMUnavailableError` — **not** an empty string, and not a bare `Exception`.

> **Note for the engineer:** this is a deliberate breaking change. Documents that previously
> indexed badly-but-successfully will now fail loudly. Do not soften it.

---

## Task 4: Typed tree-parse failure

**Files:**
- Modify: `pageindex/page_index.py:1167`

**Step 1: Replace the bare exception**

The `raise` sits in the `else` of a fallback cascade (TOC-with-pages → TOC-without-pages →
no-TOC), so it means *all strategies exhausted*, not *bad input*. Say so:

```python
        else:
            raise TreeParseError(
                "Could not derive a document structure: exhausted all TOC strategies "
                "(process_toc_with_page_numbers, process_toc_no_page_numbers, process_no_toc)",
                doc_name=getattr(logger, 'filename', None),
            )
```

**Step 2: Import it**

At the top of `pageindex/page_index.py`:

```python
from .errors import TreeParseError
```

**Step 3: Verify the import graph still loads**

```bash
python -c "import pageindex; print('ok')"
```

Expected: `ok`

---

## Task 5: System dependency checks

**Files:**
- Create: `pageindex/preprocess.py`

**Step 1: Create the module skeleton with binary resolution**

```python
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
```

**Step 2: Verify resolution reports honestly on this machine**

```bash
python -c "
from pageindex.preprocess import _find_soffice, _require_tesseract
for fn in (_find_soffice, _require_tesseract):
    try: print(fn.__name__, '->', fn() or 'present')
    except Exception as e: print(fn.__name__, '-> MISSING:', e)"
```

Expected: either a path/`present`, or a `MissingSystemDependencyError` naming the exact
`apt-get` command. Both outcomes are acceptable locally; record which ones are missing.

---

## Task 6: Office → PDF conversion

**Files:**
- Modify: `pageindex/preprocess.py`

**Step 1: Append the converter**

```python
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
```

**Step 2: Verify against a real Office file**

Requires LibreOffice installed. Create a throwaway `.docx` however is convenient, then:

```bash
python -c "
from pageindex.preprocess import _convert_to_pdf
pdf = _convert_to_pdf(open('/path/to/sample.docx','rb').read(), '.docx')
print('bytes:', len(pdf), 'header:', pdf[:5])"
```

Expected: a non-trivial byte count and header `b'%PDF-'`.

If LibreOffice is not installed locally, skip and record the step as unverified — do not stub it.

---

## Task 7: Per-page classification

**Files:**
- Modify: `pageindex/preprocess.py`

**Step 1: Append the classifier**

```python
import pypdfium2 as pdfium

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
```

**Step 2: Verify on a born-digital PDF**

```bash
python -c "
from pageindex.preprocess import _classify
for name in ('attention-residuals.pdf', 'PRML.pdf', 'q1-fy25-earnings.pdf'):
    doc, pages = _classify(open(f'examples/documents/{name}','rb').read())
    print(name, 'pages:', len(pages), 'needing OCR:', sum(1 for _,_,ocr in pages if ocr))"
```

Expected, measured against these exact files while writing this plan:

| File | Pages | Needing OCR |
|---|---|---|
| `attention-residuals.pdf` | 21 | 0 |
| `PRML.pdf` | 758 | 10 |
| `q1-fy25-earnings.pdf` | 22 | 0 |

PRML's 10 are genuinely near-empty pages (part titles, full-page figures with no caption) and are
correct. A materially higher count means the classifier is over-triggering and would destroy good
text layers — fix before continuing.

---

## Task 8: OCR of image pages

**Files:**
- Modify: `pageindex/preprocess.py`

**Step 1: Append the OCR stage**

```python
import asyncio
import logging
import time

import pytesseract

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
```

**Step 2: Verify Tesseract is reachable and speaks Italian**

```bash
tesseract --list-langs
```

Expected: the list includes `ita`. If it does not, install `tesseract-ocr-ita` before continuing —
the default English model returns plausible but wrong text and nothing raises.

**Step 3: Verify OCR against a real scanned client document**

```bash
python -c "
import pypdfium2 as pdfium, pytesseract
doc = pdfium.PdfDocument('<path to DUVRI DL01_Toffetti.pdf>')
img = doc[11].render(scale=150/72).to_pil()
txt = pytesseract.image_to_string(img, lang='ita', config='--psm 1', timeout=60)
print(len([l for l in txt.splitlines() if l.strip()]), 'non-empty lines')
print(txt[:400])"
```

Expected, measured while writing this plan (macOS, tesseract 5.5.2): ~67 non-empty lines, ~2.9k
characters, ~0.9s. The Italian column appears as a contiguous block before the English one. If
the two languages interleave line by line, `--psm` was not applied.

**Step 4: Verify concurrency does not segfault, and measure**

```bash
python -c "
import asyncio
from pageindex.preprocess import _classify, _ocr_pages
doc, pages = _classify(open('<path to DUVRI DL01_Toffetti.pdf>','rb').read())
ords = [o for o,_,ocr in pages if ocr]
import time; t0 = time.perf_counter()
out = asyncio.run(_ocr_pages(doc, ords, 150, 'ita', 1, 3))
print(len(out), 'pages OCRd in', round(time.perf_counter()-t0, 2), 's')"
```

Expected: `51 pages OCRd in ~22 s`. **A segmentation fault here means rendering leaked into a
worker thread** — pdfium is not thread-safe, and the process dies with no traceback. Measured
2026-08-19: psm 1 took 21.81s, psm 3 took 19.36s; the orientation detection costs 2.45s across
the whole document.

**Step 5: Verify orientation detection on a rotated scan**

```bash
python -c "
import pypdfium2 as pdfium, pytesseract
doc = pdfium.PdfDocument('<path to Lube Duvri.pdf>')
img = doc[3].render(scale=150/72).to_pil()
print('pdf rotation metadata:', doc[3].get_rotation())
print(pytesseract.image_to_string(img, lang='ita', config='--psm 1', timeout=60)[:120])"
```

Expected: PDF metadata reports rotation `0` while the text comes out readable, beginning
`DOCUMENTO UNICO DI VALUTAZIONE DEI ... RISCHI DA INTERFERENZE`. Unreadable output such as
`9£ IP p euised IZIAIOS` means OSD is not running — check that `osd.traineddata` is installed.

---

## Task 9: Assemble `preprocess()`

**Files:**
- Modify: `pageindex/preprocess.py`

**Step 1: Append the dataclasses and the public function**

```python
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
```

Add `OCRError` to the imports from `.errors` at the top of the module.

**Step 2: Verify end to end on a born-digital PDF**

```bash
python -c "
from pageindex.preprocess import preprocess
n = preprocess('examples/documents/attention-residuals.pdf')
print(n.doc_name); print(n.report); print(repr(n.pages[0][:120]))"
```

Expected: `source_format='pdf'`, `ocr_pages=0`, `failed_pages=[]`, a non-zero `chars_extracted`,
and readable text from page 1.

**Step 3: Verify the format guard**

```bash
python -c "
from pageindex.preprocess import preprocess
try: preprocess(b'not a document', filename='x.txt')
except Exception as e: print(type(e).__name__, '-', e)"
```

Expected: `UnsupportedFormatError`.

---

## Task 10: `build_tree` accepts page texts

**Files:**
- Modify: `pageindex/page_index.py:1236-1281` (`page_index_main`)
- Modify: `pageindex/build_tree.py`

**Step 1: Teach `page_index_main` the pages path**

Replace the head of the function (`pageindex/page_index.py:1236`):

```python
def page_index_main(doc, opt=None, pages=None, doc_name=None):
    logger = JsonLogger(doc_name or doc, log_dir=getattr(opt, 'log_dir', None))

    if pages is not None:
        import litellm
        page_list = [
            (text, litellm.token_counter(model=opt.model, text=text)) for text in pages
        ]
    else:
        is_valid_pdf = (
            (isinstance(doc, str) and os.path.isfile(doc) and doc.lower().endswith(".pdf")) or
            isinstance(doc, BytesIO)
        )
        if not is_valid_pdf:
            raise ValueError("Unsupported input type. Expected a PDF file path or BytesIO object.")

        print('Parsing PDF...')
        page_list = get_page_tokens(doc, model=opt.model)

        # A PDF with no extractable text indexes as an empty-but-valid tree, which is the exact
        # silent failure this fork exists to remove. Make the omission loud instead.
        if not any(text.strip() for text, _ in page_list):
            raise NotPreprocessedError(
                "PDF has no extractable text layer. Call preprocess() first and pass "
                "build_tree(pages=...)",
                doc_name=get_pdf_name(doc),
            )
```

Then, in both `return` dicts inside `page_index_builder`, replace `get_pdf_name(doc)` with:

```python
                    'doc_name': doc_name or get_pdf_name(doc),
```

Add to the imports at the top of the file:

```python
from .errors import NotPreprocessedError, TreeParseError
```

**Step 2: Widen `build_tree`**

Replace `pageindex/build_tree.py`'s function:

```python
def build_tree(source=None, *, pages=None, doc_name=None, **kwargs):
    """Build a PageIndex tree.

    Two mutually exclusive input paths:

      build_tree(pages=norm.pages, doc_name=norm.doc_name)   # preferred — see preprocess()
      build_tree(source)                                     # PDF bytes / path, must have text

    source:   PDF as raw bytes, a filesystem path str, or a pathlib.Path. bytes are handled in
              memory; nothing is written to disk.
    pages:    per-page text from preprocess(). Skips PDF parsing entirely.
    doc_name: explicit document name. Without it a bytes source falls back to PDF metadata,
              which client documents frequently lack — several docs all named "Untitled" make
              the consumer's retrieval catalog unusable.
    kwargs:   any valid config key (model, summary_model, log_dir, ...). Invalid keys raise
              ValueError (validated against DEFAULT_CONFIG).

    Returns the tree structure (dict). Does NOT persist — the caller decides.
    """
    if (source is None) == (pages is None):
        raise ValueError("Pass exactly one of `source` or `pages`.")

    opt = ConfigLoader().load(kwargs or None)

    if pages is not None:
        return page_index_main(None, opt, pages=pages, doc_name=doc_name)

    if isinstance(source, bytes):
        doc = BytesIO(source)
    elif isinstance(source, Path):
        doc = str(source)
    elif isinstance(source, str):
        doc = source
    else:
        raise TypeError(
            f"source must be bytes, str, or Path, got {type(source).__name__}"
        )
    return page_index_main(doc, opt, doc_name=doc_name)
```

**Step 3: Verify the argument guard without spending an LLM call**

```bash
python -c "
from pageindex import build_tree
for kwargs in ({}, {'source': 'a.pdf', 'pages': ['x']}):
    try: build_tree(**kwargs)
    except Exception as e: print(type(e).__name__, '-', e)"
```

Expected: `ValueError - Pass exactly one of \`source\` or \`pages\`.` twice.

**Step 4: Verify the full path on a real document**

Requires model credentials. Run it once — this is the only end-to-end proof the plan has:

```bash
python -c "
from pageindex import preprocess, build_tree
n = preprocess('examples/documents/attention-residuals.pdf')
tree = build_tree(pages=n.pages, doc_name=n.doc_name)
print(tree['doc_name']); print(len(tree['structure']), 'top-level nodes')"
```

Expected: the filename as `doc_name` (not `Untitled`) and a non-empty structure.

---

## Task 11: Exports and dependencies

**Files:**
- Modify: `pageindex/__init__.py`
- Modify: `pyproject.toml`

**Step 1: Export the new surface**

Append to `pageindex/__init__.py`:

```python
from .preprocess import preprocess, Normalized, PreprocessReport
from .errors import (
    PageIndexError,
    UnreadableInputError,
    UnsupportedFormatError,
    ConversionError,
    OCRError,
    NotPreprocessedError,
    MissingSystemDependencyError,
    LLMUnavailableError,
    LLMConfigError,
    TreeParseError,
)
```

**Step 2: Declare the new dependencies**

In `pyproject.toml`, add to `dependencies`:

```toml
    "pytesseract==0.3.13",
    "Pillow>=10.0.0",
```

**Step 3: Verify the package imports cleanly**

```bash
python -c "
import pageindex
for name in ('preprocess', 'build_tree', 'Normalized', 'LLMUnavailableError'):
    assert hasattr(pageindex, name), name
print('ok')"
```

Expected: `ok`

> Do **not** run `uv add` / `uv run` here: they regenerate `uv.lock`, which this library does not
> commit. Edit `pyproject.toml` by hand.

---

## Task 12: Consumer documentation

**Files:**
- Modify: `README.md`
- Modify: `FORK_NOTES.md`

**Step 1: Add a consumer section to `README.md`**

````markdown
## Preprocessing (fork addition)

Documents are normalized before indexing. Always call `preprocess()` first:

```python
from pageindex import preprocess, build_tree

norm = preprocess(raw_bytes, filename="Disposizioni ingresso.pdf")
tree = build_tree(pages=norm.pages, doc_name=norm.doc_name)

norm.pages    # per-page text; index = page number - 1
norm.report   # source_format, page_count, text_pages, ocr_pages, failed_pages, chars_extracted
```

`preprocess()` converts Office files to PDF, detects scanned pages, and OCRs only those.
Page positions are never compacted: a page whose OCR failed holds `""` and its number appears
in `report.failed_pages`, so page numbers stay aligned with the source document.

### Required system binaries

The library asserts these; it cannot install them.

```dockerfile
RUN apt-get install -y tesseract-ocr tesseract-ocr-ita tesseract-ocr-osd libreoffice
```

Both are too heavy for a zip Lambda layer. Use a container-image Lambda.

### Which errors to retry

| Error | Retry? |
|---|---|
| `LLMUnavailableError` | **Yes** — throttling or transport. Exponential backoff. |
| `LLMConfigError` | No — bad key or missing model. |
| `TreeParseError` | No — deterministic; retrying only spends time. |
| `UnreadableInputError` and subclasses | No — the document must be fixed or re-uploaded. |
| `MissingSystemDependencyError` | No — fix the runtime image. |

### Breaking changes

- The LLM retry loop used to return `""` after exhausting its attempts; it now raises
  `LLMUnavailableError`. Documents that previously indexed badly-but-successfully will start
  failing loudly. **This is the intent.**
- `build_tree(source=...)` now raises `NotPreprocessedError` for a PDF with no text layer
  instead of producing an empty tree.
- Telemetry no longer writes to `./logs` by default. Pass `log_dir="/tmp/pageindex"` to
  re-enable it.
````

**Step 2: Record the divergences in `FORK_NOTES.md`**

Add entries under *Divergences from upstream* for: the `preprocess()` module, the error
taxonomy, the LLM retry behaviour change, the configurable `log_dir`, and `build_tree(pages=...)`.
Each one gets a sentence on *why*, in the style of the existing entries.

**Step 3: Verify**

```bash
git diff --stat
```

Expected: the twelve tasks' files, and nothing else.

---

## Task 13: Pass-through LLM metadata for consumer tracing

The consumer enables Langfuse from outside, via litellm's process-global callbacks — the fork
never imports Langfuse and never sees the keys. But metadata travels *per call*, and the calls are
ours, so the consumer cannot inject it from outside. Without it every span arrives unattributed:
40 anonymous model calls per document, with no way to ask what indexing one document cost.

**Files:**
- Modify: `pageindex/config.py`
- Modify: `pageindex/utils.py` (module-level ContextVar + both litellm call sites)
- Modify: `pageindex/page_index.py` (`page_index_main` sets the context)
- Modify: `README.md`

**Step 1: Add the config key**

In `pageindex/config.py`, add to `DEFAULT_CONFIG`:

```python
    "llm_metadata": None,    # dict forwarded verbatim to litellm (e.g. Langfuse trace_id/tags)
```

**Step 2: Add the context variable**

`llm_completion` is called from ~20 sites with only `model=` and `prompt=`; none of them carry
`opt`. Threading a new argument through all of them would mean editing upstream code everywhere,
which is exactly what this fork avoids. A ContextVar carries the value implicitly instead, and is
asyncio-safe: concurrent node tasks each see their own value rather than racing on a global.

Near the top of `pageindex/utils.py`:

```python
from contextvars import ContextVar

# Set once per document by page_index_main, read by the litellm call sites. A ContextVar rather
# than a module global because tree building runs many nodes concurrently under asyncio, and each
# task must see the metadata of its own document.
_llm_metadata: ContextVar[dict | None] = ContextVar("llm_metadata", default=None)


def set_llm_metadata(metadata: dict | None) -> None:
    _llm_metadata.set(metadata)
```

**Step 3: Forward it at both litellm call sites**

In `llm_completion`, the `litellm.completion(...)` call gains:

```python
                    metadata=_llm_metadata.get() or {},
```

Same for `litellm.acompletion(...)` in `llm_acompletion`.

Do NOT add it to the two OpenAI-SDK branches — that SDK has no `metadata` parameter and would
raise. See Step 5.

**Step 4: Set the context once per document**

In `pageindex/page_index.py`, at the top of `page_index_main`, right after the logger:

```python
    set_llm_metadata(getattr(opt, 'llm_metadata', None))
```

**Step 5: Document the gap in `README.md`**

Add to the preprocessing section:

````markdown
### Observability

The fork does not depend on any tracing vendor. Enable one from the outside — litellm's callbacks
are process-global, and the fork's model calls go through litellm:

```python
import litellm
litellm.success_callback = ["langfuse"]
litellm.failure_callback = ["langfuse"]
```

To group the many calls of one document into a single trace, pass metadata through:

```python
tree = build_tree(
    pages=norm.pages,
    doc_name=norm.doc_name,
    llm_metadata={"trace_id": case_id, "trace_name": f"index:{norm.doc_name}", "tags": ["indexing"]},
)
```

**Known gap:** a model identifier with no provider prefix (e.g. `gpt-4o-2024-11-20`) is dispatched
through the OpenAI SDK directly, bypassing litellm — so neither the callbacks nor `llm_metadata`
apply to it. Prefixed models (`bedrock/...`, `anthropic/...`, `litellm/...`) go through litellm and
are fully traced. This is silent: metrics simply stop appearing.
````

**Step 6: Verify the metadata reaches litellm without credentials**

```bash
python -c "
import logging; logging.disable(logging.CRITICAL)
import pageindex.utils as u
seen = {}
import litellm
orig = litellm.completion
def spy(**kw):
    seen.update(kw)
    raise RuntimeError('stop')
litellm.completion = spy
u.set_llm_metadata({'trace_id': 'abc123'})
try: u.llm_completion('bedrock/some-model', 'hi')
except Exception: pass
litellm.completion = orig
print('metadata forwarded:', seen.get('metadata'))"
```

Expected: `metadata forwarded: {'trace_id': 'abc123'}`

**Step 7: Verify the config key is accepted and defaults to empty**

```bash
python -c "
from pageindex.utils import ConfigLoader
print(ConfigLoader().load({'llm_metadata': {'trace_id': 'x'}}).llm_metadata)
print(ConfigLoader().load(None).llm_metadata)"
```

Expected: `{'trace_id': 'x'}` then `None`.

---

## Unresolved questions

- `ocr_concurrency=3` is derived from `memorySize: 4096` (~2.3 vCPU), not measured. Confirm on
  the real Lambda.
- ~~`--psm` choice~~ — **resolved 2026-08-19.** Measured on real client documents; default is
  `psm 1`, driven by rotated scans in `Lube Duvri.pdf`. See Task 8.
- ~~No scanned PDF available to verify OCR~~ — **resolved 2026-08-19.** Verified against
  `11_FixOCR/01_InputProblematici/`: `DUVRI DL01_Toffetti.pdf` (51/51 scanned),
  `Lube Duvri.pdf` (hybrid, pages 4-7 scanned), `DUVRI Belbo Sugheri…pdf` (page 28 only).
  These files are outside the repo; keep them out of git and reference them by path.
- ~~Which Office formats actually occur~~ — **resolved 2026-08-19.** Only `.docx` has been seen
  in practice, but all five formats in the consumer's `upload_policy` are contractually supported
  and the client's staff were told so. Implement all five; expect no corpus for four of them.
  Spreadsheet pagination is a known limitation, not a bug — see the design's §9.
- ~~`page.get_objects()` API surface~~ — **resolved 2026-08-19.** Verified against pypdfium2
  4.30.0: `get_objects(filter=..., max_depth=...)`, `obj.get_pos()`, and
  `pdfium.raw.FPDF_PAGEOBJ_IMAGE` all behave as the plan assumes. The first draft of the
  classifier was measured and corrected — see Task 7.
