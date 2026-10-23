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
