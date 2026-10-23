# Code Review — ocr-vision-fallback

## Verdict: NEEDS_WORK

pytest: 18 passed (.venv python, PYTHONPATH=fork).

## Plan Compliance
- [x] Tasks 1-7 done, one commit each, journal present (journal entries thin: Tasks 1-2 not logged separately, only "start" and "Tasks 3-7").
- [x] AC-1 `is_scan` independent of chars (`_classify`)
- [ ] AC-2 byte-identical with `ocr_vision_model=None` — NOT met (see Major 1)
- [x] AC-3 gate: n_words==0 never vision, `mean_conf < min`, fallback to previous text, failures listed
- [x] AC-4 report fields present
- [x] AC-5 INTEGRATION.md + FORK_NOTES.md #13
- [x] AC-6 pytest passes

## Requirements / design
OK: text priority vision > Tesseract/text layer; OCRError only when every needs_ocr page fails (unchanged semantics for those pages); rendering stays on loop thread (vision re-render too); no temperature; lazy litellm import; no new deps; max_pages cap; no other callers of `_ocr_pages/_classify/_ocr_image/_page_is_image` outside preprocess.py (grep).

## Issues

### Critical
- none

### Major
1. **Vision-off output is not byte-identical for OCR'd pages.** `_ocr_image` now rebuilds text from `image_to_data` (words joined per (block,par,line), lines joined by `\n`) instead of `image_to_string`. Paragraph/blank-line separation and Tesseract's own whitespace are lost, so every `needs_ocr` page changes text for all consumers (tree/headings are built from it). Verification missed it: the only fixture OCR page was blank, and the 40-page doc had none. Fix: keep `image_to_string` for text and get confidence from a separate/second call, or emit the same paragraph breaks and diff against old output on a real scanned doc (e.g. a fully scanned 51-page fixture).
2. **New hard dependency/cost on scans with a text layer, even with vision off.** `ocr_ordinals` now includes every `is_scan` page and `_require_tesseract()` runs for them: a doc that used to preprocess without Tesseract (scanner-embedded text layer) now raises if Tesseract is missing, and OCR time is added per scan page for no output change. Fix: only score scans when `ocr_vision_model` is set (or document the behaviour change and keep default cost-free).
3. **Scope rule breach in committed docs.** `docs/project_context/.../plan.md` (lines ~20, 94, 132, 220, 237-238, 388-390) names client fixtures and content (sopralluogo, duvri_cm, BLOCCO B2, RICARICA LITIO, local consumer path). FORK_NOTES.md rule: no client/domain wording. Code diff itself is clean (pre-existing mentions in FORK_NOTES/preprocess.py comments are not from this branch). Genericise or drop from the committed plan; verification.md is clean.

### Minor
- Vision cap is racy by up to `concurrency` pages (acknowledged in a comment; acceptable).
- JPEG encoding (`_image_to_data_url`) runs on the event-loop thread; blocks other pages briefly. `asyncio.to_thread` would be safe (PIL image, not pdfium).
- `OCR_MIN_CONFIDENCE` line exceeds 100 cols; `_ocr_image`/`_OcrResult` lack docstring; `base64`/`io` imported inside function (stdlib, move to top).
- Journal/verification state `scan_pages=4` vs plan's 3 (blank page is a full-page image): fine, but `scan_pages` then counts blanks; note in INTEGRATION.md.
- Vision text "unchanged on re-run" not guaranteed (nondeterministic); noted in verification, ok.

## Summary
Design is implemented faithfully and gate/fallback/concurrency logic is sound. The `image_to_data` text rebuild breaks the byte-identical guarantee for ordinary OCR pages and scoring scans adds Tesseract requirement/cost with vision off; fix those two and genericise plan.md, then re-verify on a scanned-only document.

## Round 2

**Verdict: APPROVED**

- Major 1/2 resolved (code read): `_ocr_image(with_confidence=False)` uses `image_to_string` (preprocess.py:221); `with_confidence=bool(vision_model)` at the call site (:311); `ocr_ordinals` = needs_ocr, plus scans only when `ocr_vision_model` is set (:452-455). With vision off, only needs_ocr pages are OCR'd and no Tesseract requirement is added.
- Major 3: grep over branch-touched files hits only pre-existing lines (FORK_NOTES.md 10/221-316, preprocess.py 181-185); zero added lines match. Literal "must be empty" fails only because of that old content; this branch's changes are clean. (code_review.md itself quotes the words in Round 1.)
- F3 minors done: JPEG encode via `asyncio.to_thread` (:262), style fixes. pytest: 18 passed.
- `uv.lock`: untracked, not part of the fork (pyproject + requirements.txt, no uv); do not commit, delete or gitignore. `.venv` is git-ignored.
