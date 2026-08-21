# Can consumers run Langfuse 3.x/4.x? — empirical findings

**Date:** 2026-08-21
**Trigger:** the consuming backend (Estratto) reported that `INTEGRATION.md` §1's `langfuse<3`
pin blocks them: they run `langfuse 4.0.1` and import `observe`, `get_client` and
`propagate_attributes`, none of which exist in v2. The pin does not degrade their telemetry —
their app fails to import.
**Status:** resolved. `INTEGRATION.md` §1 and §5 and `examples/e2e_check.py` updated.
The pin is gone; no fork code changed.

---

## Setup

Isolated venv: `langfuse 4.14.4` + the already-pinned `litellm 1.84.0`. A local HTTP server
stood in for Langfuse to capture and decode the raw OTLP protobuf, so the wire contents could be
inspected independently of what the Langfuse UI chooses to render. Cloud runs then went to the
real `jungheinrich-dev` project for ground truth on rendering.

Document under test: `DUVRI Belbo Sugheri` — 29 pages, 1 OCR'd, 56 model calls per run.
Model: `bedrock/eu.anthropic.claude-haiku-4-5`.

## Confirmed: the consumer's blocker is real

```
AttributeError: module 'langfuse' has no attribute 'version'
```

Reproduced with `success_callback = ["langfuse"]` under langfuse 4.14.4, raised from
`litellm/integrations/langfuse/langfuse.py:170`. `observe` / `get_client` /
`propagate_attributes` all import cleanly on 4.x.

## Confirmed: `langfuse_otel` needs no Langfuse SDK

`litellm/__init__.py:126-127` registers both `"langfuse"` and `"langfuse_otel"`.
`LangfuseOtelLogger` subclasses `OpenTelemetry` and imports no `langfuse` module; it POSTs OTLP
to `{LANGFUSE_HOST}/api/public/otel/v1/traces` with basic auth built from
`LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`. Its dependencies ship with litellm.

**Divergence worth documenting:** with no `LANGFUSE_HOST` set, `langfuse_otel` defaults to the
**US** cloud endpoint (`langfuse_otel.py:283`), whereas the v2 SDK defaults to **EU**
(`langfuse/client.py:292`). OTLP export failures do not propagate, so a consumer relying on the
old default would lose traces silently. The current consumer sets `LANGFUSE_HOST` explicitly and
is unaffected.

## Resolution

`langfuse_otel` + an enclosing span + **`USE_OTEL_LITELLM_REQUEST_SPAN=true`** gives grouping and
generation detail together. Verified end to end:

```
trace 35965e2bf2d4feaed52de95580d344c0: 113 observations  totalCost=0.133809
types: {'GENERATION': 56, 'SPAN': 57}
GENERATIONs with model: 56/56
total tokens: 95913
```

One trace per document, every call a `GENERATION` with model, usage and cost. The sections below
record how the apparent trade-off arose and why the flag dissolves it.

## The trade-off that was not one

Three wirings were run end to end against the real Langfuse project.

| Wiring | Traces per document | Observation type | Model / tokens / cost | Input / output |
|---|---|---|---|---|
| `trace_id` in `llm_metadata` | **56** | `GENERATION` + empty `SPAN` | present (3665/147 tok, $0.0044) | present |
| Parent span (OTEL context) | **1** (57 obs) | `SPAN` only | all zero | absent |
| Both together | **1** (57 obs) | `SPAN` only | all zero | absent |

Read alone, this says neither wiring matches the v2 callback and combining them does not help.
That conclusion was wrong — see *Why the context path loses generation detail* below.

### Why the metadata path does not group

The wire carries `langfuse.trace.id` correctly — one distinct value across all 56 calls — but
the OTLP payload also carries **56 distinct OTEL trace ids**. Langfuse builds the trace from the
OTEL trace id and ignores the attribute, so each call becomes its own trace. This is the direct
answer to the consumer's open question, and it is negative.

### Why the context path loses generation detail

With a Langfuse SDK span as parent, all 57 spans share one OTEL trace id and 56 carry a
`parent_span_id` — grouping is exact, and it survives `build_tree`'s asyncio concurrency. But
litellm emits one span per call instead of two in this configuration, and the surviving span is
the one without the generation attributes. Langfuse therefore renders plain `SPAN`s: no model
attribution, no token counts, `totalCost=0`, no input/output.

**Cause and fix.** This is a deliberate litellm behaviour, not an OTEL or Langfuse limitation.
`opentelemetry.py:1281-1284` skips the primary `litellm_request` span whenever a parent span
exists — "keep hierarchy shallow" (`:1302`) — and that primary span is the one carrying model,
usage and cost. Setting `USE_OTEL_LITELLM_REQUEST_SPAN=true` restores it. With the flag, the same
run produces 113 observations: 56 `GENERATION`s with full attribution plus the 57 structural
spans.

Generation naming (FORK_NOTES divergence #9, 2026-08-20) survives in **both** paths — 8 distinct
function-derived names observed.

## What this means

`langfuse_otel` unblocks the consumer but is not yet an equivalent replacement. The choice is
between a pin that blocks their application and a tracing path that costs either trace grouping
or per-call cost and token attribution.

Per-document cost was a reported delivery metric ($0.07/document); the context path would end
that measurement.

## Not established

* Whether a newer litellm changes any of the above. The whole investigation is scoped to the
  pinned `litellm==1.84.0`.
* Whether `USE_OTEL_LITELLM_REQUEST_SPAN` is stable across litellm versions. It is read via
  `get_secret_bool`, is undocumented upstream, and a rename would silently return every
  observation to `totalCost=0`. A consumer-side check that a freshly indexed document reports
  non-zero cost would catch it.

## Reproducing

The probe scripts are not committed — they hardcode a local capture server and consumer
credentials. The venv used is `.venv-lf4` (gitignored). Cloud evidence:

* metadata path — filter the `jungheinrich-dev` project by tag `otelcheck-metadata` (56 traces)
* context path — `traces/30a40e560688df974ef0c86481efce94`
* both — `traces/4b486fa23ef2c76f59fadaa066935a79`
* **adopted wiring** (`USE_OTEL_LITELLM_REQUEST_SPAN=true`) — `traces/35965e2bf2d4feaed52de95580d344c0`

`examples/e2e_check.py` was then rerun on the same document with the committed wiring and
completed normally (10 top-level nodes, 100% TOC accuracy).

Total Bedrock cost of the investigation: ~$0.55 across 7 document runs.
