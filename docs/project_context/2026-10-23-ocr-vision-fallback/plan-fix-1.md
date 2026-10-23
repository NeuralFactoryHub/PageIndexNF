# Fix plan 1 — after code review (NEEDS_WORK)

Source: `validation/code_review.md`. One commit per fix. No push.

## F1 — Vision off ⇒ byte-identical behaviour (review Major 1 + 2, AC-2)

Rule: **when `ocr_vision_model is None`, the code path is exactly today's**: `ocr_ordinals` = `needs_ocr` pages only, `_ocr_image` uses `pytesseract.image_to_string` as before, no confidence scoring, `scan_pages` still counted (cheap, from `_classify`), `low_confidence_pages == []`.

When `ocr_vision_model` is set:
- `ocr_ordinals` = `needs_ocr or is_scan`.
- One Tesseract pass per page via `image_to_data`; text rebuilt from it with layout: lines joined by `\n`, a blank line between paragraphs/blocks (sorted by block, par, line). Document in the docstring that OCR text layout for `needs_ocr` pages may differ slightly from `image_to_string` in this mode.
- Scans that keep their text layer are unaffected by that difference (their text comes from the layer unless vision replaces it).

Implementation sketch: `_ocr_image(image, lang, psm, *, with_confidence: bool) -> _OcrResult`; `with_confidence=False` → `image_to_string`, `mean_conf=100.0`, `n_words=-1` (unknown). `_ocr_pages` receives `vision_model` and passes `with_confidence=bool(vision_model)`.

Verify: dump `preprocess(...).pages` for both fixtures with the branch at `origin/feature/customizations` (use `git stash`/`git worktree` or `git show origin/feature/customizations:pageindex/preprocess.py > /tmp/pre.py` and import it) and with HEAD, `ocr_vision_model=None` → identical lists. Record in `validation/verification.md`.

## F2 — Generic wording in docs (review Major 3, FORK_NOTES scope rule)

`plan.md`, `validation/verification.md`, `journals/engineer.md`, `INTEGRATION.md`, `FORK_NOTES.md`: remove client/domain words and fixture names (`sopralluogo`, `duvri`, `BLOCCO B2`, `RICARICA LITIO`, `INTERFERENZIALI`, `C&M`, `Jungheinrich`, `Myo`, `Stradella`). Replace with: "handwritten scanned form (4 pages: 2 printed scans, 1 handwritten, 1 blank)", "40-page printed document with one scanned page", "the 4 reference phrases supplied by the consumer". Fixture paths: "provided by the consumer at verification time (not in this repo)". `grep -rniE "duvri|jungheinrich|sopralluogo|stradella|myo|c&m|blocco b2" docs INTEGRATION.md FORK_NOTES.md pageindex` → no hits.

## F3 — Minor

- JPEG encoding of the page image (`_image_to_data_url`) → `await asyncio.to_thread(...)`.
- Vision cap race: keep, but add the one-line "why acceptable" comment if missing.
- Address the style items listed in `code_review.md` (short ones only).

## Done when
`python -m pytest -q` passes; F1 identity check recorded; grep in F2 returns nothing; journal updated.
