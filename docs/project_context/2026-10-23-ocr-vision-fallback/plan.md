# OCR quality gate + vision fallback — implementation plan

> **For Claude:** REQUIRED SUB-SKILL: use the nf:executing-plans skill to implement this plan task-by-task.

**Goal:** scanned pages whose text (embedded layer or Tesseract) is low-confidence get transcribed by a configurable vision model; everything else unchanged.
**Architecture:** all changes in `pageindex/preprocess.py`; additive params on `preprocess()`, additive fields on `PreprocessReport`; docs in `INTEGRATION.md` + `FORK_NOTES.md`.
**Services touched:** `pageindex` (skill `nf:backend-python`).
**Design:** `docs/plans/2026-10-23-ocr-vision-fallback/design.md`.
**Rules:** fork stays generic (no client/domain wording). No new deps. No tests unless asked (CLAUDE.md) — verification is the manual run in Task 7.

**Acceptance criteria**
- AC-1 A scanned page with an embedded text layer is still rasterised and scored by Tesseract (`is_scan` ignores char count).
- AC-2 `preprocess()` exposes `ocr_min_confidence`, `ocr_vision_model`, `ocr_vision_dpi`, `ocr_vision_prompt`, `ocr_vision_max_pages`; with `ocr_vision_model=None` page text is byte-identical to today's output.
- AC-3 With a vision model set, a page with `n_words > 0` and `mean_conf < ocr_min_confidence` gets the vision transcription; blank pages (`n_words == 0`) never trigger vision; failures fall back to the previous text and are listed in the report.
- AC-4 `PreprocessReport` carries `scan_pages`, `low_confidence_pages`, `vision_pages`, `vision_failed_pages`, `vision_seconds`, `vision_input_tokens`, `vision_output_tokens`.
- AC-5 `INTEGRATION.md` documents the new params/fields; `FORK_NOTES.md` gets a divergence entry.
- AC-6 `python -m pytest -q` still passes.

Verification fixtures (NOT committed, client documents):
"form" = handwritten scanned form (4 pages: 2 printed scans, 1 handwritten, 1 blank); "printed doc" = 40-page printed document with one scanned page. Both are provided by the consumer at verification time (not in this repo). Reference spike script for the vision call: a consumer-side spike script.

Commit after each task with a conventional message (no push — the developer pushes).

---

### Task 1: constants, signature, report fields — covers AC-2, AC-4

**Files:** Modify `pageindex/preprocess.py` (around L168-183 constants, L225-238 `PreprocessReport`, L255-262 `preprocess` signature)

**Step 1** Add after `_OCR_TIMEOUT_SECONDS`:
```python
OCR_MIN_CONFIDENCE = 70          # Tesseract mean word confidence (0-100) under which a page is "low confidence"
OCR_VISION_DPI = 150
OCR_VISION_MAX_PAGES = 10
OCR_VISION_MAX_TOKENS = 4096
OCR_VISION_PROMPT = (
    "Transcribe faithfully all text on this page, printed and handwritten, in the page's own "
    "language, preserving line order. Write [illegible] for words you cannot read. Output only "
    "the page text: no notes, comments or explanations."
)
```

**Step 2** Extend `PreprocessReport`:
```python
    scan_pages: int = 0
    low_confidence_pages: list[int] = field(default_factory=list)
    vision_pages: list[int] = field(default_factory=list)
    vision_failed_pages: list[int] = field(default_factory=list)
    vision_seconds: float = 0.0
    vision_input_tokens: int = 0
    vision_output_tokens: int = 0
```

**Step 3** Extend `preprocess()` signature (keep existing params and order):
```python
    ocr_min_confidence: int = OCR_MIN_CONFIDENCE,
    ocr_vision_model: str | None = None,
    ocr_vision_dpi: int = OCR_VISION_DPI,
    ocr_vision_prompt: str | None = None,
    ocr_vision_max_pages: int = OCR_VISION_MAX_PAGES,
```
Update the docstring (one line per param).

**Step 4 Verify:** `python -c "from pageindex import preprocess; import inspect; print(inspect.signature(preprocess))"` shows the new params. `python -m pytest -q` passes.

---

### Task 2: scan detection independent of char count — covers AC-1

**Files:** Modify `pageindex/preprocess.py` `_page_is_image` (L112-133), `_classify` (L136-163)

**Step 1** Extract the full-page-image check:
```python
def _has_full_page_image(page) -> bool:
    page_area = page.get_width() * page.get_height()
    if page_area <= 0:
        return False
    for obj in page.get_objects(filter=(pdfium.raw.FPDF_PAGEOBJ_IMAGE,), max_depth=4):
        left, bottom, right, top = obj.get_pos()
        if abs(right - left) * abs(top - bottom) >= IMAGE_AREA_RATIO * page_area:
            return True
    return False
```
`_page_is_image(page, text)` keeps its exact semantics, now calling `_has_full_page_image` in the 50–250 branch.

**Step 2** `_classify` returns 4-tuples `(ordinal, text, needs_ocr, is_scan)`:
```python
            text = textpage.get_text_bounded() or ""
            is_scan = _has_full_page_image(page)
            needs_ocr = _page_is_image(page, text)
```
Comment why: scanners embed their own OCR layer; a scan must be scored even when it carries text.

**Step 3 Verify:** quick script on the form: p1-p3 `is_scan=True, needs_ocr=False`; p4 `needs_ocr=True`. On the printed doc: born-digital pages `is_scan=False`. Commit: `feat(preprocess): detect scanned pages independently of text-layer length`.

---

### Task 3: Tesseract with confidence — covers AC-3

**Files:** Modify `pageindex/preprocess.py` `_ocr_image` (L186-189)

**Step 1**
```python
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
        if conf < 0:          # -1 marks non-word boxes
            continue
        confs.append(conf)
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)
    text = "\n".join(" ".join(w) for _, w in sorted(lines.items()))
    mean_conf = sum(confs) / len(confs) if confs else 0.0
    return _OcrResult(text=text, mean_conf=mean_conf, n_words=len(confs))
```

**Step 2 Verify:** on the form p3 at 150 DPI, lang `ita`: `mean_conf` ≈ 60, `n_words` ≈ 218; p1 ≈ 86; p4 `n_words == 0`. On the printed doc p35 ≈ 83. Commit: `feat(preprocess): tesseract returns word confidence`.

---

### Task 4: vision fallback inside `_ocr_pages` — covers AC-3, AC-4

**Files:** Modify `pageindex/preprocess.py` `_ocr_pages` (L192-222)

**Step 1** Add the vision helper (module level, `litellm` imported lazily like the rest of the fork):
```python
def _image_to_data_url(image, quality: int = 85) -> str:
    import base64, io
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
```

**Step 2** `_ocr_pages` signature becomes
`_ocr_pages(doc, ordinals, dpi, lang, psm, concurrency, *, min_confidence, vision_model, vision_dpi, vision_prompt, vision_max_pages)` and returns `(results: dict[int, _OcrResult], vision: dict[int, str], stats: dict)` where `stats = {"low_confidence": [..], "vision_failed": [..], "vision_seconds": float, "in_tokens": int, "out_tokens": int}`.
Inside `run(ordinal)` after Tesseract:
```python
                res = results[ordinal]
                if res.n_words == 0 or res.mean_conf >= min_confidence:
                    return
                stats["low_confidence"].append(ordinal)
                if not vision_model or len(vision) + len(stats["vision_failed"]) >= vision_max_pages:
                    return
                try:
                    if vision_dpi != dpi:
                        image = doc[ordinal - 1].render(scale=vision_dpi / 72).to_pil()
                    t0 = time.perf_counter()
                    text, tin, tout = await _vision_transcribe(image, vision_model, vision_prompt or OCR_VISION_PROMPT)
                    stats["vision_seconds"] += time.perf_counter() - t0
                    stats["in_tokens"] += tin; stats["out_tokens"] += tout
                    if text.strip():
                        vision[ordinal] = text
                    else:
                        stats["vision_failed"].append(ordinal)
                except Exception as e:
                    stats["vision_failed"].append(ordinal)
                    logging.warning(f"Vision transcription failed on page {ordinal}: {e}", exc_info=True)
```
Keep pdfium rendering on the loop thread (existing comment explains why). The `vision_max_pages` check is racy under concurrency by at most `concurrency` pages — acceptable, note it in a comment.

**Step 3 Verify:** `python -m pytest -q` passes. Commit: `feat(preprocess): vision fallback for low-confidence OCR pages`.

---

### Task 5: final page assembly + report — covers AC-2, AC-3, AC-4

**Files:** Modify `pageindex/preprocess.py` `preprocess()` body (L300-343)

**Step 1** OCR set = `needs_ocr or is_scan`. Keep the existing `OCRError` only when **every `needs_ocr` page** failed (scans with a good text layer must not raise).

**Step 2** Per-page text priority:
```python
        for ordinal, text, needs_ocr, is_scan in classified:
            if ordinal in vision_text:
                pages.append(vision_text[ordinal]); continue
            if needs_ocr:
                if ordinal in ocr_results: pages.append(ocr_results[ordinal].text)
                else: pages.append(""); failed.append(ordinal)
            else:
                pages.append(text)        # scans with a text layer keep it (AC-2: identical output when vision is off)
```

**Step 3** Fill the report: `scan_pages`, `low_confidence_pages`, `vision_pages=sorted(vision_text)`, `vision_failed_pages`, `vision_seconds`, token counters. `ocr_pages`/`text_pages` semantics unchanged (count `needs_ocr` pages only).

**Step 4 Verify:** run `preprocess(form_bytes, filename="form.pdf", ocr_lang="ita")` (vision off): `pages` identical to current `feature/customizations` output for all 4 pages (diff against a dump taken before Task 2), `report.scan_pages == 3`, `report.low_confidence_pages == [3]`. Commit: `feat(preprocess): report scan/low-confidence/vision pages`.

---

### Task 6: docs — covers AC-5

**Files:** Modify `INTEGRATION.md` (§ `preprocess(...)` table + `PreprocessReport` fields), `FORK_NOTES.md` (new divergence entry "OCR quality gate + vision fallback": why, do, status DONE).

Document: params, defaults, "vision disabled by default", the no-`temperature` note, and the consumer's measured model table (generic wording: "a handwritten scanned form").

Commit: `docs: document OCR confidence gate and vision fallback`.

---

### Task 7: end-to-end verification — covers AC-1..AC-6

**Step 1** Script (not committed, in the scratch dir) running `preprocess` with `ocr_vision_model="bedrock/eu.anthropic.claude-haiku-5-5"`, `ocr_lang="ita"`, AWS creds from the consumer backend `.env` (the consumer backend `.env`), on both fixtures. Expected:
- the form: `vision_pages == [3]`, page 3 text contains the 4 reference phrases supplied by the consumer; no "Nota"/"Note:" trailer added by the model; p4 → `""`, not in `low_confidence_pages`; p1-p2 unchanged text layer.
- the printed doc: `vision_pages == []`, `low_confidence_pages == []`, total runtime within +5 s of the pre-change run.
- `python -m pytest -q` → all pass.

**Step 2** Paste the numbers into `docs/project_context/2026-10-23-ocr-vision-fallback/validation/verification.md`. Commit: `docs(ocr): verification run`.

---

## Unresolved questions
- Threshold 70 validated on one handwritten sample; consumer to re-check on more forms.
- `ocr_vision_max_pages` default 10 — adjust if real documents have more handwritten pages.
