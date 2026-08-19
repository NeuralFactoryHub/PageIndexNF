# End-to-end verification — `preprocess()` → `build_tree()`

**Date:** 2026-08-19
**Branch:** `feature/preprocessing`
**Model:** `bedrock/eu.anthropic.claude-haiku-4-5-20251001-v1:0` (`eu-west-1`)
**Run by:** Juan, from the fork's own checkout — the consumer repo was not modified and no package
was installed into it.

The code review and QA report validate the code. This document is the only evidence that the
feature does what it was built for: that text recovered by OCR reaches the tree and becomes
retrievable. Full terminal logs are outside the repo, in
`Documents/InternalServices/PageIndexFork/01_PreprocessingDocs/e2e-*.log`.

---

## 1. Result

| | `Lube Duvri.pdf` | `DUVRI Belbo Sugheri_Rev.02_2026_con allegati.pdf` |
|---|---|---|
| Pages / OCR'd | 36 / 4 | 29 / 1 |
| Failed pages | none | none |
| `preprocess` wall | 1.08s (classify 0.12s, OCR 0.96s) | 0.66s (classify 0.06s, OCR 0.60s) |
| `build_tree` wall | 61.58s | 32.96s |
| `doc_name` | `'Lube Duvri.pdf'` | `'DUVRI Belbo Sugheri_Rev.02_2026_con allegati.pdf'` |
| TOC path taken | `process_no_toc` | `process_toc_with_page_numbers` |
| Internal TOC accuracy | 100% | 100% |
| Top-level nodes | 7 | 10 |
| Langfuse callbacks | enabled | enabled |

Both tree-building routes — with and without an embedded table of contents — were exercised.

`doc_name` is correct on both runs. This is the direct confirmation of the reviewer's Critical §1
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
demonstrated by Belbo, not by Lube. Lube demonstrates something else worth having — that OCR'd
pages integrate with their neighbours instead of fragmenting the tree.

The extracted text also shows the expected OCR degradation (`Foomalie re)`, `secondolaprevisione`,
`sable`). Legible and sufficient for tree building and summarisation; not clean enough to quote
verbatim to an end user.

## 4. Incidental findings — for the consumer, not the fork

Both surfaced while getting the run to work, and both would have hit the Jungheinrich backend.

**`litellm 1.84.0` requires `langfuse<3`.** With `langfuse 4.14.4` installed, litellm's callback
initialisation raises `AttributeError: module 'langfuse' has no attribute 'version'`; with langfuse
absent entirely it raises `ModuleNotFoundError`. Either way the error propagates into the model
call and **indexing fails outright — not just telemetry**. `langfuse 2.60.10` works. The consumer
should pin it; an unpinned `pip install` resolves to 4.x.

**The fork's retry loop treats both as retryable.** They are permanent configuration errors, but
they carry no status code and no credential-shaped message, so `_is_unrecoverable` misses them and
the call retries 10 times against the 60s budget. The budget bounds the damage, which is the point
of having it — but two patterns should be added. Tracked as follow-up, not fixed here.

## 5. Reproducing

```bash
cd ~/CursorProjects/PageIndexNF
set -a; source <path to the backend .env>; set +a
export AWS_REGION_NAME="${AWS_REGION_NAME:-$AWS_REGION}"   # litellm/bedrock reads AWS_REGION_NAME

.venv/bin/python <e2e_check.py> "<pdf>" "bedrock/$ANALISTA_MAIN_MODEL"
```

The `bedrock/` prefix is required: an unprefixed model id is dispatched through the OpenAI SDK,
bypassing litellm — so neither Bedrock credentials, the callbacks, nor `llm_metadata` apply.

The verification script lives outside the repo, in the session scratchpad. If this check is to be
repeatable by someone else, it needs a home in `examples/` — currently it does not have one.

## 6. Still unverified

- Langfuse traces were emitted but the dashboard was not inspected, so per-document grouping via
  `llm_metadata` is confirmed only at the call site, not at the destination.
- `DUVRI DL01_Toffetti.pdf` (51 pages, fully scanned) has not been run end to end. It is the
  worst case for both OCR time (~21s) and tree building; the 890s Lambda timeout should be
  confirmed against it before production traffic.
- No Office document has been through the full path end to end; conversion was verified in
  isolation.
