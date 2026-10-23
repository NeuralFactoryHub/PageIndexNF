# QA Report — ocr-vision-fallback

## Verdict: PASS (1 minor note)

## Gates
- [x] `python -m pytest -q`: 18 passed. No linter configured.

## Acceptance Criteria
- [x] AC-1: scan detection independent of char count. Form fixture: scan_pages=4 (blank p4 included); 40-page fixture: scan_pages=2.
- [x] AC-2: params exposed (INTEGRATION.md signature matches code). Vision off: all pages of both fixtures byte-identical to pre-branch code (origin/feature/customizations), run on same fixtures with ocr_lang=ita.
- [x] AC-3: vision on (haiku, ita): form fixture low_confidence_pages=[3], vision_pages=[3], vision_failed_pages=[]; p3 contains the 3 reference phrases; blank p4 stays "" and was not sent to vision. 40-page fixture: no low-confidence pages, no vision calls. Failure fallback not exercised live (covered by unit tests only).
- [x] AC-4: report carries all 7 fields. Vision run: seconds 10.5, tokens in/out 2915/1959; off run: empty lists / zeros.
- [x] AC-5: INTEGRATION.md documents params, fields and defaults; FORK_NOTES.md has entry 13.
- [x] AC-6: pytest passes (above).

## Other checks
- [x] No client/domain wording in lines added by the branch (grep over added diff lines). Pre-existing FORK_NOTES.md lines contain such wording (rule at line 10, history entries ~221-315), not introduced here.
- Untracked, do NOT commit: `uv.lock`. Also untracked `plan-fix-1.md` (project artifact, fine to commit) and modified `validation/code_review.md` (artifact).

## Minor note (non-blocking)
- With vision ON, a page OCR'd by Tesseract but not sent to vision (40-page fixture p35) loses its trailing "\n" vs vision off (777 vs 778 chars). Content identical. Only affects vision-on mode; no AC violated.

## Summary
All ACs verified with real Bedrock calls on both fixtures. Vision-off output is identical to pre-branch.
