# Engineer Journal — ocr-vision-fallback
## Skill: nf:backend-python
## Service: pageindex (pageindex/preprocess.py)
## Plan: docs/project_context/2026-10-23-ocr-vision-fallback/plan.md

### Work Log

#### [start] Setup
**What:** Journal created, plan and source read. Env: consumer venv with PYTHONPATH pointing at this fork, so no new venv is needed.
**Why:** The consumer venv already has all deps (pypdfium2, pytesseract, litellm), which avoids a slow install.
**Alternatives considered:** Fresh venv; rejected for time.
**Files touched:** this journal.

#### [now] Tasks 3-7
**What:** Implemented tesseract confidence (`_OcrResult`), vision fallback inside `_ocr_pages`, final assembly and report fields, docs in INTEGRATION.md and FORK_NOTES.md, then ran the end-to-end verification (validation/verification.md). One commit per task.
**Why:** Followed the plan literally; scans are OCR'd for scoring only, and keep their text layer unless vision replaces it, so output without a model is unchanged. OCRError is raised only when every needs_ocr page fails.
**Alternatives considered:** none beyond the plan.
**Open points:** scan_pages=4 on the form (blank p4 is a full-page image), plan said 3; vision output varies between runs; the plan's .env path (jh-prmocr) was used for creds. No tests added (project rule); existing 18 pass.
**Files touched:** pageindex/preprocess.py, INTEGRATION.md, FORK_NOTES.md, validation/verification.md.

#### [fix-1] F1-F3 after code review
**What:** F1: `_ocr_image` takes `with_confidence`; vision off uses `image_to_string` exactly as before and only needs_ocr pages are OCR'd, so no new Tesseract dependency or cost; scoring (`image_to_data`, text rebuilt with blank lines between paragraphs) only when a vision model is set. F2: plan.md and verification.md rewritten with generic wording and no fixture paths. F3: JPEG encoding moved to `asyncio.to_thread`, stdlib imports hoisted, long line wrapped, docstrings added; the vision-cap race already had its why-comment.
**Why:** The review showed byte-identical output and zero extra cost are the contract when the feature is off; the cheapest way to guarantee it is to keep the legacy code path literally untouched.
**Alternatives considered:** a second `image_to_string` call alongside `image_to_data` for confidence (doubles OCR time); rejected in favour of the plan's single-pass rebuild only when vision is on.
**Verification:** vision-off pages identical to origin/feature/customizations on both fixtures (recorded in validation/verification.md). The only OCR'd page in the fixtures is blank, so real text identity rests on the code path being unchanged. Pre-existing client wording in older docs and in preprocess.py comments (not from this branch) was left alone.
**Files touched:** pageindex/preprocess.py, INTEGRATION.md, plan.md, verification.md, this journal.
