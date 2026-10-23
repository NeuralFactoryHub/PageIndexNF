# OCR quality gate + vision fallback — design

**Date:** 2026-10-23 · **Branch:** `feature/ocr-vision-fallback` (from `feature/customizations`)
**Consumer evidence:** downstream backend, `docs/project_context/2026-10-23-prompt-ocr-quality/validation/spike-findings.md`

## Problem

`preprocess()` decides per page between "trust the PDF text layer" and "run Tesseract" using
character count alone (`_page_is_image`). Two silent failure modes:

1. **Scanner-embedded OCR layers.** Scanners (ABBYY FineReader via Ricoh Streamline NX, etc.)
   embed their own OCR text. A handwritten page gets a ≥250-char layer of garbage
   (`jy 4'ut 4 ^OiRie4…`), passes the `chars >= SUSPICIOUS_CHARS_PER_PAGE` short-circuit and is
   never rasterised. The garbage enters the tree as valid text.
2. **No OCR quality signal.** Tesseract output is accepted as-is. Handwriting yields noise with
   no flag for the consumer.

Measured on a real scanned 4-page form: the handwritten page has text-layer chars=646,
forced-Tesseract `mean_conf=60.4`; printed scanned pages score 80.7–85.7; printed born-digital
pages 83+. Margin ≈ 20 points.

## Non-goals

- Handwriting recognition inside Tesseract (not feasible).
- Changing `build_tree`, tree shape, or `Normalized.pages` type (`list[str]`).
- Domain wording of any kind (fork stays generic — see FORK_NOTES scope rule).
- New dependencies (`litellm`, `Pillow`, `pypdfium2`, `pytesseract` already present).

## Approach (chosen of three)

| option | verdict |
|---|---|
| A. Text-layer garbage ratio on every page | marginal signal (0.435 vs 0.252 printed), rejected |
| **B. Scan detection → forced Tesseract confidence → vision fallback** | chosen: clean margin, cost only on scanned pages |
| C. Vision on every OCR page | simple but slow/expensive on 40-page scans, rejected |

### Flow per page (new)

```
text layer ──► is_scan? (full-page image object, any char count)
   │ no  ──► keep text layer (unchanged behaviour)
   │ yes ──► Tesseract image_to_data ──► (text, mean_conf, n_words)
               │ n_words == 0              ──► keep text layer or "" (blank page, never call vision)
               │ mean_conf >= threshold    ──► keep text layer if it had one, else Tesseract text
               │ mean_conf <  threshold    ──► vision model (if configured) ──► its transcription
                                                 │ failure/timeout ──► Tesseract text, page listed in report
```

`needs_ocr` pages (chars < 50, or 50–250 with full-page image) behave as today plus the
confidence branch.

### Public API (additive, backwards compatible)

```python
preprocess(source, filename=None, ocr_lang="eng", ocr_dpi=150, ocr_psm=1, ocr_concurrency=3,
           ocr_min_confidence=70, ocr_vision_model=None, ocr_vision_dpi=150,
           ocr_vision_prompt=None, ocr_vision_max_pages=10)
```

- `ocr_vision_model=None` → vision disabled; only the confidence measurement and report fields
  change. Rollback = leave it unset.
- `ocr_vision_model` is a LiteLLM model string (`bedrock/eu.anthropic.claude-haiku-5-5`…).
- `ocr_vision_prompt=None` → built-in generic prompt (English, "transcribe faithfully in the
  page's language, no commentary"). Consumer may pass its own.
- `ocr_vision_max_pages` caps vision calls per document (cost guard on long scanned docs).

`PreprocessReport` gains: `scan_pages: int`, `low_confidence_pages: list[int]`,
`vision_pages: list[int]`, `vision_failed_pages: list[int]`, `vision_seconds: float`,
`vision_input_tokens: int`, `vision_output_tokens: int`.

### Vision call

- Same PIL image already rendered for Tesseract (re-rendered at `ocr_vision_dpi` only if it
  differs from `ocr_dpi`), JPEG quality 85, base64 `image_url` content block.
- `litellm.acompletion(model, messages=[{"role":"user","content":[image, text]}],
  max_tokens=4096)`. **No `temperature`** (Claude 5.x on Bedrock Converse rejects it).
- Runs inside the existing OCR semaphore; one failure never fails the document.

### Measured model choice (consumer-side spike, handwritten Italian form)

| model | critical-block accuracy | stable | $/page | latency |
|---|---|---|---|---|
| Claude Haiku 5.5 @150 DPI | 1.000 (3/3) | yes | 0.0015 | ~11 s |
| Claude Sonnet 4.5 @200 DPI | 1.000 (3/3) | yes | 0.015 | ~16 s |
| Nova 2 Lite | 0.927 | yes | 0.0014 | ~4 s (hallucinates on blank pages) |
| Ministral 3 14B | errors in all reps | no | 0.0007 | ~4 s |
| Haiku 4.5 | number/term errors | — | 0.005 | ~9 s |

Default stays `None` in the library; the consumer picks the model.

## Risks

- Printed scans with heavy noise could dip under 70 → one unnecessary vision call per such
  page; cost-bounded by `ocr_vision_max_pages`. Threshold is a parameter.
- `image_to_data` vs `image_to_string`: same Tesseract run, same text; verified text output
  is assembled from `image_to_data` words grouped by block/par/line to keep line breaks.
- Lambda wall-clock: +~11 s per vision page. Acceptable for 1–3 pages; cap handles outliers.

## Open questions

- None blocking. Threshold validated on one handwritten sample; consumer re-validates on more
  forms before raising the default.
