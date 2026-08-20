# Integration guide — PageIndexNF

The single document a consuming backend needs. `README.md` is upstream's and describes a
different, script-oriented workflow; ignore it.

---

## 1. Install

```bash
uv add "git+https://github.com/NeuralFactoryHub/PageIndexNF.git@feature/customizations"
```

`feature/customizations` is this fork's production branch and the only ref to pin. Feature
branches are merged into it; they are never installed directly.

### System binaries

The library asserts these at call time and raises `MissingSystemDependencyError` if absent. It
cannot install them. They are too heavy for a zip Lambda layer — use a container image.

```dockerfile
RUN apt-get install -y tesseract-ocr tesseract-ocr-osd tesseract-ocr-eng libreoffice
```

Add one `tesseract-ocr-<lang>` pack per language you intend to OCR. For Italian documents:
`tesseract-ocr-ita`.

### Python dependency to pin

```
langfuse<3
```

`litellm 1.84.0` initialises its Langfuse callback against the v2 SDK. With langfuse 4.x it
raises `AttributeError: module 'langfuse' has no attribute 'version'`; with the package absent,
`ModuleNotFoundError`. Either error propagates out of the model call, so **indexing fails, not
just telemetry**. An unpinned install resolves to 4.x. Verified working: `langfuse==2.60.10`.

---

## 2. The two calls

Indexing is two steps, in this order, on every document.

```python
from pageindex import preprocess, build_tree

norm = preprocess(raw_bytes, filename="Disposizioni ingresso.pdf", ocr_lang="ita")
tree = build_tree(pages=norm.pages, doc_name=norm.doc_name, model="bedrock/...")
```

`preprocess()` normalises the document; `build_tree()` turns page text into the hierarchical
index. They are separate on purpose: `norm.pages` is the same text the tree was built from, so a
catalog, a snippet store or a full-text search can reuse it without parsing the document twice.

### `preprocess(source, filename=None, ocr_lang="eng", ocr_dpi=150, ocr_psm=1, ocr_concurrency=3)`

| Parameter | Notes |
|---|---|
| `source` | raw `bytes`, a path `str`, or a `pathlib.Path` |
| `filename` | supplies `doc_name`, and identifies the format when bytes arrive with no extension. **Always pass it when passing bytes.** |
| `ocr_lang` | Tesseract's `-l` flag. **Pass `"ita"` for Italian documents** — the default is `"eng"`. |

Accepted formats: PDF, and `.doc .docx .odt .xls .xlsx .ods .ppt .pptx .odp` (converted to PDF
via LibreOffice first — PageIndex cites by page number, and an Office file has no pages until it
is laid out). Anything else raises `UnsupportedFormatError`.

Returns `Normalized(pages, doc_name, report)`:

```python
norm.pages      # list[str], one entry per page; index = page number - 1
norm.doc_name   # carried through to tree["doc_name"]
norm.report     # PreprocessReport
```

**Page positions are never compacted.** A page whose OCR failed holds `""` and its number is
listed in `report.failed_pages`. Page *n* of the source is always `pages[n-1]`, so citations
stay aligned with what the user sees in the original file.

`PreprocessReport` fields — worth logging per document:

```
source_format  page_count  text_pages  ocr_pages  failed_pages  chars_extracted
convert_seconds  classify_seconds  ocr_seconds
```

`failed_pages` non-empty means the tree was built with holes in it. Nothing raises. Decide
whether that is acceptable for your use case, and surface it if it is not.

### `build_tree(pages=..., doc_name=..., **config)`

Any valid config key can be passed as a kwarg — `model`, `summary_model`, `retrieve_model`,
`log_dir`, feature toggles. An invalid key raises `ValueError` immediately.

Returns the tree as a `dict`. It does **not** persist anything; storing it is the caller's job.

---

## 3. Calling from async code

Both functions are synchronous. `preprocess()` additionally runs its own event loop internally
(`asyncio.run`), so calling it from inside a running loop — an `async def` FastAPI route —
raises `RuntimeError: asyncio.run() cannot be called from a running event loop`.

```python
# async def route
norm = await asyncio.to_thread(preprocess, raw_bytes, filename=name, ocr_lang="ita")
tree = await asyncio.to_thread(build_tree, pages=norm.pages, doc_name=norm.doc_name)
```

A plain `def` route needs no wrapper — FastAPI already runs it in a threadpool. Either way,
offload: `build_tree()` blocks for tens of seconds on a real document.

---

## 4. Errors

Every error inherits from `PageIndexError`.

| Error | Retry? | Meaning |
|---|---|---|
| `LLMUnavailableError` | **Yes** | Throttling or transport. The only error worth retrying. |
| `LLMConfigError` | No | Bad key, missing model, permanent environment fault. |
| `TreeParseError` | No | Deterministic — the same input fails the same way. |
| `UnsupportedFormatError` | No | Not a PDF or a supported Office format. |
| `ConversionError` | No | LibreOffice could not convert the file. |
| `OCRError` | No | Tesseract failed on the whole document. |
| `NotPreprocessedError` | No | A PDF with no text layer reached `build_tree` directly. Call `preprocess()` first. |
| `MissingSystemDependencyError` | No | Fix the container image. |

`UnsupportedFormatError`, `ConversionError`, `OCRError` and `NotPreprocessedError` all inherit
from `UnreadableInputError` — catch that one to mean "this document cannot be indexed as
submitted", and report it to whoever uploaded it.

The library retries `LLMUnavailableError` internally with exponential backoff, capped at 60s
total per call. When it gives up, it raises rather than returning empty text.

---

## 5. Observability

The fork depends on no tracing vendor. litellm's callbacks are process-global and every model
call goes through litellm, so enable tracing from your side:

```python
import litellm
litellm.success_callback = ["langfuse"]
litellm.failure_callback = ["langfuse"]
```

One document produces ~40 model calls. To collect them into a single trace instead of 40
unrelated ones, pass metadata through:

```python
tree = build_tree(
    pages=norm.pages,
    doc_name=norm.doc_name,
    llm_metadata={
        "trace_id": case_id,          # the grouping key
        "session_id": user_session,
        "trace_name": f"index:{norm.doc_name}",
        "tags": ["indexing"],
    },
)
```

**Known gap:** a model id with no provider prefix (`gpt-4o-2024-11-20`) is dispatched through
the OpenAI SDK directly, bypassing litellm — so neither the callbacks nor `llm_metadata` apply.
Prefixed ids (`bedrock/...`, `anthropic/...`) are fully traced. This is silent: metrics simply
stop appearing.

---

## 6. Changes from the pre-preprocessing version

If you are upgrading an existing integration:

1. **`preprocess()` is now required.** Passing a PDF straight to `build_tree(source=...)` still
   works for born-digital files, but a scanned PDF now raises `NotPreprocessedError` instead of
   returning an empty tree.
2. **The LLM retry loop raises instead of returning `""`.** Documents that previously indexed
   badly-but-successfully will start failing loudly. This is intended: an empty string was
   indistinguishable from a legitimately empty page.
3. **Telemetry no longer writes to `./logs`.** Pass `log_dir="/tmp/pageindex"` to re-enable it.
   Lambda's filesystem is read-only outside `/tmp`.
4. **`doc_name` is honoured.** Previously trees built from page text were all named `Untitled`.

---

## 7. Known limitations

- A document whose table of contents spans more than one page can fail with
  `Failed to complete TOC transformation after maximum retries`. This is an upstream defect in
  the TOC continuation loop, reachable now that fully-scanned documents are indexable. Fix in
  progress.
- OCR output is good enough to build a tree and summarise from, not clean enough to quote
  verbatim to an end user. Expect artefacts (`secondolaprevisione`, mangled dot leaders).
- OCR replaces a page's text rather than augmenting it, and only runs on pages classified as
  scanned. A born-digital page with a bad text layer is not repaired.
