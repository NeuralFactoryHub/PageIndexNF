# Verification — OCR vision fallback

Model: bedrock/eu.anthropic.claude-haiku-5-5, ocr_lang=ita. Fixtures not committed.

| Check | Result |
|---|---|
| scanned form, vision on | vision_pages=[3], low_confidence_pages=[3], vision_failed=[], vision 7.5s, 2915 in / 839 out tokens |
| p3 keywords | BLOCCO B2, 4 MT, RICARICA LITIO, INTERFERENZIALI all found; no "Nota"/"Note:" trailer added (the page's own printed "NOTE" heading is source text) |
| blank p4 | "" and not in low_confidence_pages |
| p1-p2 | unchanged text layer |
| printed 40-page doc | vision_pages=[], low_confidence_pages=[]; runtime 1.4s vs 1.5s vision off (delta ~0) |
| vision off | same pages as before; scan_pages=4 on the form (blank p4 is also a full-page image; plan expected 3) |
| pytest | 18 passed |

Note: vision output is nondeterministic ("4MT" vs "4 MT" across runs).

## Fix 1 identity check (vision off)

`preprocess(..., ocr_lang="ita")` dumped at `origin/feature/customizations` (baseline worktree) and at HEAD: pages identical for both fixtures (4-page form: 4/4; 40-page printed doc: 40/40). With a vision model set, OCR text layout of `needs_ocr` pages may differ slightly (rebuilt from `image_to_data`).
