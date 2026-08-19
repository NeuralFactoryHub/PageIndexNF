# Design — Document preprocessing in PageIndexNF

**Date:** 2026-08-19
**Branch:** `feature/preprocessing` (cut from `feature/customizations`, the internal prod branch)
**ClickUp:** [86cb7d412](https://app.clickup.com/t/86cb7d412) — *PageIndexNF | Aggiungere preprocessing* (urgent, due 2026-08-21)
**Source brief:** `preprocessing-brief-from-estratto-backend.md` (Estratto DUVRI backend, branch `pgindex`, 2026-08-18)

---

## 1. Problem

The fork indexes PDFs that already carry a text layer. Two classes of input fail, both silently:

1. **Non-searchable PDFs.** Scanned pages return an empty string from `extract_text()`. No OCR runs,
   nothing raises, and the document lands in the consumer's catalog looking valid. The agent then
   reports the document as uninformative rather than unreadable.
2. **Office formats.** The consumer's `upload_policy` admits `.doc`, `.docx`, `.xls`, `.xlsx`,
   `.pptx`, but the raw bytes reach the indexer and `pypdfium2` fails on them.

The consuming backend once had both capabilities (`pdf_parser.py`, `doc_converter.py`); commit
`7816d7b` orphaned them when indexing moved to PageIndex. This work does not add a feature — it
restores a capability that regressed, and relocates it to the layer that can act on it.

**Why the fork and not the consumer.** On scanned annexes, section headings exist only as pixels.
A tree built from the text layer loses the structural boundaries exactly where the annexes begin.
OCR must therefore happen *before* tree building, not as a downstream step.

## 2. Constraints

- **Runtime:** AWS Lambda, container image. Confirmed from the consumer's `serverless.yml`:
  `provider.ecr.images.fastapi` builds `backend/Dockerfile`, and `functions.api.image.name`
  points at it — there is no zip path. Operative limits from the same file:
  `memorySize: 4096` (~2.3 vCPU, since Lambda grants 1 vCPU per 1769 MB), `timeout: 890`,
  `ephemeralStorageSize: 1024` (so `/tmp` holds 1 GB), and `HOME: /tmp` — which is what makes
  LibreOffice viable at all, since it needs a writable home for its user profile.
  Bedrock runs in `eu-west-1`, the region the brief names as the throttling bottleneck.
- **Page numbers are source ordinals, never positions in a filtered list.** Trees reference pages by
  number and retrieval serves `get_page_content(page)`. Re-numbering after dropping failed pages
  would corrupt every downstream citation.
- **Classification is per page, not per document.** The corpus is full of mixed documents: a
  born-digital body with scanned annexes.
- **Absence of an exception is not evidence that a stage worked.** Every stage emits a structured
  signal the caller can assert on.
- **This fork is a library.** It never persists anything and never installs system binaries; it
  returns artefacts and asserts its requirements.

## 3. Public surface

Two calls, in sequence. `preprocess()` always runs — it decides internally, per page, whether any
work is needed; the caller never has to know in advance.

```python
norm = preprocess(raw_bytes, filename="Disposizioni ingresso.pdf")
tree = build_tree(pages=norm.pages, doc_name=norm.doc_name)
```

New module `pageindex/preprocess.py`, exported from `__init__.py`. Isolated like `build_tree.py`, so
upstream merges do not conflict.

```python
@dataclass
class PreprocessReport:
    source_format: str        # "pdf" | "docx" | ...
    page_count: int
    text_pages: int
    ocr_pages: int
    failed_pages: list[int]   # source ordinals
    chars_extracted: int

@dataclass
class Normalized:
    pages: list[str]          # index = source ordinal - 1; failed pages hold ""
    doc_name: str
    report: PreprocessReport

def preprocess(source, filename: str = None, **opts) -> Normalized: ...
```

`source` accepts `bytes`, `str` or `Path`. `filename` supplies `doc_name` and disambiguates the
format when raw bytes arrive with no extension to inspect.

`build_tree` gains a second, mutually exclusive entry path:

```python
build_tree(source=None, *, pages=None, doc_name=None, **kwargs)
```

- `pages` — skips PDF parsing and feeds the tree pipeline directly.
- `source` — the current path; validates that a text layer exists and raises `NotPreprocessedError`
  if it does not.

Passing both is an error.

### Why two calls rather than one

The consumer extracts page text a second time, independently of the tree, to build the catalog that
`get_page_content` serves. OCR hidden inside `build_tree` would produce a correct tree while the
backend kept serving blank pages — half the problem fixed, the same silent failure mode left in
place. Returning `pages` also removes that second read: one source of truth per document.

The cost is a caller who can forget the first call. That is mitigated by making the omission loud
(`NotPreprocessedError`) rather than silent — which is why `build_tree` must *never* preprocess
internally. The two behaviours are contradictory.

### Output shape: page texts, not a normalized PDF

An OCR-sandwich PDF would keep `build_tree`'s signature unchanged but costs an extra dependency
(`ocrmypdf`), image weight and runtime, to produce an intermediate artefact nobody reads. The tree
needs text per page and nothing else. Trade-off accepted: a consumer wanting a searchable PDF for
display does not get one from this API.

## 4. Pipeline

Fixed order, three stages.

**(a) Convert.** Non-PDF input goes through `soffice --headless --norestore --convert-to pdf`, 120s
timeout. Two guards carried from the brief: resolve the binary as `libreoffice` → `soffice` →
macOS bundle path; check *both* the exit code and the existence of the output file, because
LibreOffice exits 0 and produces nothing. PDF input is a no-op.

A third guard is added for Lambda specifically: warm invocations share `/tmp`, so two concurrent
conversions would contend for the same LibreOffice user profile. Each conversion therefore gets
its own via `-env:UserInstallation=file:///tmp/lo_<pid>_<counter>`.

LibreOffice is required for pagination, not fidelity: PageIndex cites by page number, and a `.docx`
has no pages until something lays it out. Direct `python-docx` text extraction was rejected for that
reason, and because the Jungheinrich documents carry embedded images that must reach OCR.

**(b) Classify.** Per page, via `pypdfium2` (already a dependency). Primary signal is the brief's
`< 50 chars` threshold. A second signal targets the brief's known failure direction — a scan
carrying a DMS-stamped footer crosses 50 characters and would never be OCR'd: a near-full-page
image on a page holding **fewer than 250 characters** also classifies as `image`.

The text gate on that second signal is not decoration. Measured on `examples/documents/PRML.pdf`
while designing: keying on image area alone flagged 55 pages, because a born-digital textbook is
full of full-page figures on pages that also carry perfectly good text. OCR does not augment a
page, it replaces it — so an over-eager classifier destroys text layers rather than repairing
them. With the gate, the same file flags 10 pages, all genuinely near-empty.

**(c) OCR.** Only pages classified `image`. Rasterized one page at a time with
`pypdfium2`'s `page.render(scale=...)` — not `pdf2image`, which rasterizes the whole document and
drags in poppler. 150 DPI (settled by experiment upstream; re-measure on dense tables, not prose,
before changing). Tesseract with configurable `lang` (default `ita` — the corpus is Italian and the
default English model returns plausible but wrong text) and `--psm 1`.

The brief proposed `--psm 6` ("single uniform block"). Two measurements on the real corpus
rejected it, and then rejected the obvious replacement as well:

- **Columns.** `DUVRI DL01_Toffetti.pdf` is bilingual in two columns. psm 6 and psm 4 interleave
  Italian and English line by line, producing mixed-language soup that would poison every node
  summary. psm 3 and psm 1 run layout analysis and emit each column as a contiguous block — 67
  lines against 38, at the same cost. psm 6 also mangled a page heading ("DUVRI DL01" → "x. -»
  DUVRI DLO1"), and headings are precisely what the tree is built from.
- **Rotation.** `Lube Duvri.pdf` pages 4-7 are scans rotated 270°, and `page.get_rotation()`
  reports `0` — the rotation is baked into the scanned image, not declared in PDF metadata, so
  nothing but Tesseract's orientation detection (OSD) can see it. psm 3 returns unreadable
  garbage there; psm 1 recovers the real heading, `DOCUMENTO UNICO DI VALUTAZIONE DEI RISCHI DA
  INTERFERENZE`. The cost is ~25% more time per page.

OSD needs `osd.traineddata`, so the runtime image must install `tesseract-ocr-osd` alongside the
language pack. Without it `psm 1` fails.

Concurrency via semaphore, with **only Tesseract** dispatched to threads. Rendering stays on the
event-loop thread: pdfium is a C library that is not thread-safe, and touching a `PdfDocument`
from another thread segfaults the interpreter outright — no exception, no traceback, a dead Lambda
invocation. This was found by measurement, not by reading: the first draft rendered inside the
worker and crashed the process on the first run against a real document.

The split costs nothing, because it parallelizes the expensive half: rendering is 0.042s per page
against ~0.4s for Tesseract. Rendering also happens *inside* the semaphore rather than before it,
which bounds live PIL images to the concurrency limit instead of holding the whole document in
memory (~6.5 MB per page at 150 DPI).

Default concurrency 3: the consumer's Lambda runs at 4096 MB ≈ 2.3 vCPU, so the brief's 4 oversubscribes
slightly while 2 leaves a core idle. Configurable, and still worth measuring on the real runtime.

**Partial failure.** A page that fails OCR yields `""` in its position and its source ordinal in
`report.failed_pages`. Only if *every* image page fails does the call raise `OCRError`.

## 5. Error taxonomy

New module `pageindex/errors.py`. Every error carries `doc_name` and, where applicable, a page range.

```python
class PageIndexError(Exception): ...

class UnreadableInputError(PageIndexError): ...      # (a) the input is broken
class UnsupportedFormatError(UnreadableInputError): ...
class ConversionError(UnreadableInputError): ...
class OCRError(UnreadableInputError): ...

class LLMUnavailableError(PageIndexError): ...       # (b) throttling / transport — RETRYABLE
class LLMConfigError(PageIndexError): ...            #     401/403/404 — never retry
class TreeParseError(PageIndexError): ...            # (c) model answered, structure unparseable

class NotPreprocessedError(PageIndexError): ...      # preprocess() was skipped
class MissingSystemDependencyError(PageIndexError): ...
```

**`LLMUnavailableError` is the only error a caller should retry.** That is the contract enabling the
consumer's differentiated retry.

Three changes to existing code:

1. `llm_completion` / `llm_acompletion` (`utils.py:79`, `:126`) currently retry 10 times with a flat
   1s sleep and, on exhaustion, **return `""`**. That empty string flows downstream, the TOC parser
   finds nothing, the fallback cascade exhausts, and the caller sees `Processing failed` — a
   transient throttle disguised as a broken document. Replace with exponential backoff plus jitter,
   and raise `LLMUnavailableError` on exhaustion. The existing 401/403/404 short-circuit becomes
   `LLMConfigError`.
2. `meta_processor` (`page_index.py:1167`): `Exception('Processing failed')` becomes
   `TreeParseError` carrying `doc_name` and the strategies that were exhausted. Note this branch is
   reached only after the full fallback cascade (TOC-with-pages → TOC-without-pages → no-TOC), so it
   means "all strategies exhausted", not "bad input".
3. `build_tree(source=...)` raises `NotPreprocessedError` when the PDF has no text layer.

**Behaviour change.** Change 1 turns today's silent degradations into exceptions. Documents that
currently index badly-but-successfully will start failing loudly. That is the intent, but it is a
breaking change for the consumer and must be documented as such.

## 6. Telemetry and dependencies

**Logging.** `JsonLogger.__init__` (`utils.py:365`) calls `os.makedirs("./logs")` unconditionally on
every `page_index_main` call — a crash on Lambda before a single page is processed. New config key
`log_dir: str | None = None`; telemetry defaults to off, `makedirs` runs only when a path is given.

**Report vs logs.** `PreprocessReport` is returned, not logged. The consumer decides whether it goes
to CloudWatch; observability is not the library's call.

**New Python dependencies:** `pytesseract`, `Pillow` (bridge from `pypdfium2.render()` to
`pytesseract`). Nothing else — `pypdfium2` is already present, `pdf2image`/poppler stay out.

**System binaries** — the consumer's Dockerfile, not the fork's concern:

```dockerfile
RUN apt-get install -y tesseract-ocr tesseract-ocr-ita tesseract-ocr-osd libreoffice
```

A library cannot install these, only assume them. `preprocess()` checks for the binaries at first
use — not at import, which would tax callers who never preprocess — and raises
`MissingSystemDependencyError` naming the missing binary and the exact `apt-get` command.

**README.** New consumer-facing section: the two calls, the required system binaries, which error is
retryable, and the breaking change in §5.

## 7. Scope

**In:** `preprocess()` (conversion, classification, OCR, report); `build_tree(pages=...)`; the error
taxonomy; backoff and raising in the LLM retry loop; explicit `doc_name`; configurable log path;
pass-through `llm_metadata` for consumer tracing.

On that last one: the consumer enables Langfuse from outside — litellm's callbacks are
process-global and the fork's calls run through litellm, so the fork imports nothing and holds no
keys. Observability vendor choice stays theirs, as with `PreprocessReport`. But metadata travels
per call and the calls are ours, so they cannot inject it from outside; the fork owns the
pass-through, not the instrumentation. It is carried on a `ContextVar` rather than threaded through
~20 upstream call sites that never receive `opt`.

One asymmetry to document rather than fix: a model identifier with no provider prefix goes through
the OpenAI SDK directly and bypasses litellm entirely, so neither callbacks nor metadata reach it.
The consumer uses `bedrock/...`, which is fine — but the failure mode is metrics silently
disappearing.

**Out:** the consumer's own `try/except` retry policy (we enable it, they implement it); `--psm`
tuning for table-heavy pages (measure after implementation); deleting the orphaned modules in the
consumer repo.

## 8. Corpus evidence

Measured 2026-08-19 against `Documents/Clients/Jungheinrich/11_FixOCR/01_InputProblematici/`
(client files, kept outside the repo):

| Document | Pages | Needs OCR | Shape |
|---|---|---|---|
| `DUVRI DL01_Toffetti.pdf` | 51 | 51 | Fully scanned; the brief's 36 MB baseline document |
| `Lube Duvri.pdf` | 36 | 4 | Hybrid — text 1-3, scan 4-7 (rotated 270°), text 8-36 |
| `DUVRI Belbo Sugheri_Rev.02_2026.pdf` | 29 | 1 | Text throughout; page 28 is a scanned annex |

Belbo page 28 is the brief's feared false negative made concrete: a scanned annex carrying the
stamped header `BELBO SUGHERI srl Rev. 01/2026 ALLEGATO 4` — **43 characters, seven below the
50-character threshold**. It is caught, but barely, which is the argument for keeping the second
(image-area) signal.

Classification of the 36-page Lube document takes 0.20s with `pypdfium2` — worth contrasting with
the brief's pre-swap baseline, where classification with `pypdf` was 47.92s and ~70% of total
runtime.

End-to-end OCR measured on macOS with tesseract 5.5.2, `DUVRI DL01_Toffetti.pdf` (51 scanned
pages), concurrency 3:

| Configuration | Wall clock | Per page | Peak RSS |
|---|---|---|---|
| psm 3 | 19.36s | 0.38s | — |
| **psm 1 (chosen)** | **21.01s** | **0.41s** | **469 MB** |

Orientation detection therefore costs 2.45s across the worst document in the corpus, against the
consumer's 890s Lambda timeout and 4096 MB of memory. Rendering alone is 0.042s per page.

## 9. Known limitations

**Office coverage is a contract, not an observation.** Only `.docx` has appeared alongside PDF in
practice, but the consumer's `upload_policy` admits `.doc`, `.docx`, `.xls`, `.xlsx` and `.pptx`,
and the client's staff have been told those are accepted. All five are therefore supported; four
of them ship without a corpus to validate against.

**Spreadsheets paginate unpredictably.** A wide `.xls`/`.xlsx` converted to PDF has its columns
split across pages by LibreOffice's layout engine, so the resulting tree reflects the print layout
rather than the content's structure. This is not a defect we can fix: pagination is invented at
conversion time for a format that has none. Flagged so the consumer can set expectations rather
than treat a strange tree as a bug.

## 10. Unresolved questions

- OCR concurrency default (3) is derived from `memorySize: 4096`, not measured. Confirm against
  the real Lambda before tuning further.
- OSD behaviour on pages rotated by amounts other than 270° is untested; the corpus only shows
  that one rotation.

Every other question from the first draft was closed by measurement on 2026-08-19 — see §8.
