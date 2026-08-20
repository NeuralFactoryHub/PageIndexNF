# End-to-end verification — `preprocess()` → `build_tree()`

**Dates:** 2026-08-19 (initial), 2026-08-20 (Toffetti, docx, post-fix re-runs)
**Branch:** `feature/customizations`
**Model:** `bedrock/eu.anthropic.claude-haiku-4-5-20251001-v1:0` (`eu-west-1`)
**Run by:** Juan, from the fork's own checkout — the consumer repo was not modified and no package
was installed into it.

The code review and QA report validate the code. This document is the only evidence that the
feature does what it was built for: that text recovered by OCR reaches the tree and becomes
retrievable. Full terminal logs are outside the repo, in
`Documents/InternalServices/PageIndexFork/01_PreprocessingDocs/e2e-*.log`.

---

## 1. Results

| | `Lube Duvri.pdf` | `DUVRI Belbo Sugheri` | `DUVRI DL01_Toffetti.pdf` | `BRIVAPLAST.docx` |
|---|---|---|---|---|
| Source format | pdf | pdf | pdf | **docx** |
| Pages / OCR'd | 36 / 4 | 29 / 1 | **51 / 51** | 2 / 0 |
| Failed pages | none | none | none | none |
| Convert | — | — | — | **3.06s** |
| Classify | 0.12s | 0.06s | 1.36s | 0.01s |
| OCR | 0.96s | 0.60s | 20.35s | — |
| `preprocess` wall | 1.08s | 0.66s | 21.79s | 3.07s |
| `build_tree` wall | 61.58s | 32.96s | 97.13s | 17.93s |
| **Total wall** | 62.7s | 33.6s | **103s** | 26.0s |
| TOC path | `process_no_toc` | `process_toc_with_page_numbers` | `process_toc_with_page_numbers` | `process_no_toc` |
| Final accuracy | 100% | 100% | 100% (93.33% → `fix_incorrect_toc`) | 100% |
| Top-level nodes | 7 | 10 | 9 | 1 |
| `doc_name` | `'Lube Duvri.pdf'` | `'DUVRI Belbo…pdf'` | `'DUVRI DL01_Toffetti.pdf'` | `'BRIVAPLAST.docx'` |

All four coverage axes are exercised: both tree-building routes (with and without an embedded
table of contents), both source formats, and the full range from a born-digital document to a
fully-scanned one.

`doc_name` is correct on every run. This is the direct confirmation of the reviewer's Critical §1
finding: before that fix, the default config path (`if_add_doc_description: "no"`) returned
`get_pdf_name(None)` → `'Untitled'` for every document built through `build_tree(pages=...)`.
Nothing but a real run could have caught it.

## 2. The load-bearing evidence: OCR content reaches the tree

`DUVRI Belbo Sugheri` is the document that tests the premise. Its page 28 is a scanned annex whose
only extractable text was a 43-character stamped header, `BELBO SUGHERI srl Rev. 01/2026 ALLEGATO
4` — seven characters below the 50-character classification threshold. Its actual content, a
general emergency-evacuation floor plan, existed only as pixels.

The resulting tree carries a top-level `ALLEGATI` node spanning pages 24-29, and its generated
summary reads:

> Questa sezione presenta gli allegati del Documento Unico di Valutazione dei Rischi Interferenziali
> (DUVRI) della BELBO SUGHERI srl. Include: verbale di cooperazione e sopralluogo congiunto,
> verifica dell'idoneità tecnico-professionale dell'appaltatore, rischi introdotti dall'appaltatore,
> **planimetria di emergenza ed evacuazione**, e procedure di sicurezza per l'impianto fotovoltaico,
> con particolare attenzione ai rischi meccanici, elettrici, chimici e alle misure di prevenzione.

The emphasised phrase is page 28's content. It appears in the node summary — which is precisely
what the consumer's retrieval agent reads when deciding which part of a document to open. Before
this work that page contributed nothing, and the omission raised no error.

`DUVRI DL01_Toffetti.pdf` makes the same point at full scale: 51 of 51 pages scanned, 148,791
characters recovered, and a 9-node tree with 100% internal accuracy. Before this work the document
produced an empty tree in silence.

## 3. What `Lube Duvri` showed, and what it did not

Its four OCR'd pages (4-7, scanned and rotated 270°) landed inside the existing
`Aree di lavoro dove saranno svolte le attività oggetto dell'appalto` node (pages 3-8). Inspecting
their text explains why: they are continuation pages carrying the same repeated document header as
the born-digital pages around them, not annexes with headings of their own.

```
[text p3]  DOCUMENTO UNICO DI VALUTAZIONE DEI RISCHI DA INTERFERENZE secondo la previsione...
[OCR  p4]  DOCUMENTO UNICO DI VALUTAZIONE DEI Foomalie re) RISCHI DA INTERFERENZE 03/07/2019...
[text p8]  DOCUMENTO UNICO DI VALUTAZIONE DEI RISCHI DA INTERFERENZE secondo la previsione...
```

So on this document OCR closed a content hole rather than recovering a structural boundary. Stated
plainly because the distinction matters: the design's argument for OCR-before-tree-building is
demonstrated by Belbo and Toffetti, not by Lube. Lube demonstrates something else worth having —
that OCR'd pages integrate with their neighbours instead of fragmenting the tree.

The extracted text also shows the expected OCR degradation (`Foomalie re)`, `secondolaprevisione`,
`sable`). Legible and sufficient for tree building and summarisation; not clean enough to quote
verbatim to an end user.

## 4. Office conversion

`BRIVAPLAST.docx` is the only document that exercises the LibreOffice path end to end, and its
timings show where the cost sits: conversion 3.06s, classification 0.01s, OCR none. On a native
PDF preprocessing is nearly free; on an Office file what is paid for is starting LibreOffice, and
that cost is per cold container, not per document.

Two behaviours confirmed here and nowhere else:

- `pages=2`. A `.docx` has no pages until something lays it out. The count comes from the render,
  which is the entire reason conversion happens before indexing rather than after.
- `doc_name='BRIVAPLAST.docx'` keeps the **original** extension, not the intermediate PDF's. A
  user who uploaded a Word file sees a Word file in the catalog.

`ocr_pages=0` also confirms the classifier does not mistake a born-digital document for a scanned
one, which would have replaced good text with worse.

## 5. Deployment envelope

`DUVRI DL01_Toffetti.pdf` is the worst case available: 36 MB, 51 pages, every one of them scanned.
**Total 103s against the consumer's 890s Lambda timeout.** OCR is 20.35s of that; the remaining
~80% is tree building, which is LLM-bound and scales with document length rather than with page
images. Cold-start LibreOffice initialisation (~3s, see §4) applies only to Office inputs.

Langfuse reports **$0.071821** for one Toffetti indexing run.

## 6. Two defects found only by running these documents

Both were reached only because preprocessing made fully-scanned documents indexable for the first
time. Both are pre-existing upstream defects, not regressions introduced by this work.

**The TOC continuation loop ran on responses that were never truncated.** `toc_transformer` asks
a model to convert the raw TOC to JSON, then a second call judges completeness. When the model
finished normally but the judge said "no", the code asked it to *continue* an already-complete
JSON — producing a second, separate JSON object which was concatenated onto the first. The judge
then correctly reported a broken structure, forever. Measured across 6 calls: `finish_reason` was
`'finished'` every time and responses degenerated 2365 → 1414 → 141 → 41 → 41 → 41 characters, the
last being `{"table_of_contents": []}`. Fixed by splitting the paths: truncated responses keep the
stream continuation; finished-but-rejected responses get fresh single-shot retries. The two bare
`raise Exception(...)` statements became `TreeParseError`, so the failure is now distinguishable
from a library bug.

**The transformer prompt excluded unnumbered TOC entries.** With the loop fixed, Toffetti still
failed: five clean retries, all rejected. The judge's own words identified it — the
`Allegati /Annex` entry was "completely missing from the cleaned TOC". The prompt described
`structure` as "the numeric system which represents the index of the hierarchy", so the model
scoped its task to numbered sections and dropped the one bare label, even though the schema
already allowed `structure: null`. One sentence added to the prompt resolved it. The pattern —
a trailing unnumbered `Allegati` / `Moduli` / `Riferimenti` — is common in Italian safety
documents, so this is generic, not document-specific.

Worth recording: `Allegati` still does not appear as a node in Toffetti's tree, and that is
**correct**. The document ends at page 51 with cost tables and signature blocks; annexes A1, A2,
B, C and D are separate files the TOC merely references. The entry has no page number because
there are no pages behind it. Belbo, whose annexes *are* bound into the document, does get its
`[24-29] ALLEGATI` node.

Both fixes were re-verified against Belbo and BRIVAPLAST before merging: identical trees, identical
accuracy. The prompt is used by every document, so a gain on one that cost another would have been
a net loss.

## 7. Observability, confirmed at the destination

Traces were previously confirmed only at the emitting call site. Inspected in the Langfuse
dashboard (`jungheinrich-dev`):

- The session `e2e-check` holds **one** trace named `index:DUVRI DL01_Toffetti.pdf`, "Total traces:
  1" — `trace_id` groups a document's ~40 calls as designed, rather than producing 40 unrelated
  traces.
- Per-document cost is visible: $0.071821.

Every generation was named `litellm-completion`, litellm's default, making individual calls
indistinguishable. Since the fork passes a single `llm_metadata` dict shared by all calls of a
document, naming them individually would have required a parameter at ~15 upstream call sites.
Instead `llm_completion` derives the name from its calling frame (`sys._getframe(1)`), which costs
zero lines in upstream files and names any call site upstream adds later. Verified by intercepting
the real litellm calls on a BRIVAPLAST run — 34 calls, 5 distinct names, `trace_id` intact on all
of them:

```
15x  check_title_appearance
15x  check_title_appearance_in_start
 2x  toc_detector_single_page
 1x  generate_toc_init
 1x  generate_node_summary
```

## 8. Incidental findings — for the consumer, not the fork

**`litellm 1.84.0` requires `langfuse<3`.** With `langfuse 4.14.4` installed, litellm's callback
initialisation raises `AttributeError: module 'langfuse' has no attribute 'version'`; with langfuse
absent entirely it raises `ModuleNotFoundError`. Either way the error propagates into the model
call and **indexing fails outright — not just telemetry**. `langfuse 2.60.10` works. Documented in
`INTEGRATION.md`; an unpinned `pip install` resolves to 4.x.

**The fork's retry loop treated both as retryable**, burning the full 60s budget on a permanent
error. Fixed: `_is_unrecoverable` now short-circuits on `ImportError`, `AttributeError` and
`TypeError` by type rather than by message — an absent module, an attribute that will not
materialise and a signature that will not change are never fixed by waiting, and matching by type
keeps the check independent of how litellm reformats the text. Verified that throttling, timeouts
and rate limits are still classified as retryable.

## 9. Reproducing

```bash
cd ~/CursorProjects/PageIndexNF
set -a; source <path to the backend .env>; set +a
export AWS_REGION_NAME="${AWS_REGION_NAME:-$AWS_REGION}"   # litellm/bedrock reads AWS_REGION_NAME

.venv/bin/python examples/e2e_check.py "<document>" "bedrock/$ANALISTA_MAIN_MODEL"
```

Run from the repo root: the script prepends `os.getcwd()` to `sys.path`, so from anywhere else it
would import an installed `pageindex` instead of the checkout under test.

The `bedrock/` prefix is required: an unprefixed model id is dispatched through the OpenAI SDK,
bypassing litellm — so neither Bedrock credentials, the callbacks, nor `llm_metadata` apply.

The script lives at `examples/e2e_check.py`. `E2E_OCR_LANG` defaults to `"ita"` there — it
emulates a consumer passing its own language, since the library's default is `"eng"`.

## 10. Still unverified

- Only `.docx` has been through the Office path. The other eight accepted extensions
  (`.doc .odt .xls .xlsx .ods .ppt .pptx .odp`) are handled by the same LibreOffice call, but none
  has been run.
- Everything was measured on macOS against Bedrock in `eu-west-1`. Nothing has been run inside the
  consumer's Lambda container image, so the system-binary assertions
  (`tesseract`, `tesseract-ocr-osd`, the language pack, `soffice`) are verified locally only.
- One SIGSEGV was observed during QA on the 51-page document and was not reproducible in four
  subsequent attempts. Cause unidentified. `pypdfium2` handles are not thread-safe and the code
  keeps every pdfium call on the event-loop thread, which is the known hazard; whether this was a
  different one is unknown.
