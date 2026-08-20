"""End-to-end check: preprocess() -> build_tree() against a real model.

Run from the repository root — this script prepends the working directory to sys.path so it
tests the checkout, not an installed copy of the package:

    set -a; source <backend .env>; set +a
    export AWS_REGION_NAME="${AWS_REGION_NAME:-$AWS_REGION}"   # litellm/bedrock reads this name
    .venv/bin/python examples/e2e_check.py "<document>" "bedrock/$ANALISTA_MAIN_MODEL"

The model id must carry a provider prefix (`bedrock/`, `anthropic/`, ...). An unprefixed id is
dispatched through the OpenAI SDK, bypassing litellm — so credentials, tracing callbacks and
llm_metadata would all silently not apply.

Environment:
    E2E_OCR_LANG    Tesseract language pack (default "ita"; the library's own default is "eng")
    E2E_TRACE_ID    override the generated trace id
    E2E_SESSION_ID  Langfuse session (default "e2e-check")
    E2E_OUT         where to write the resulting tree (default ./e2e_tree.json)
"""
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, os.getcwd())

from pageindex import build_tree, preprocess  # noqa: E402

DOC = sys.argv[1] if len(sys.argv) > 1 else None
MODEL = sys.argv[2] if len(sys.argv) > 2 else os.getenv("E2E_MODEL")

if not DOC or not MODEL:
    sys.exit("usage: e2e_check.py <document-path> <prefixed-model-id>")

# Optional: prove the Langfuse wiring works if the keys happen to be present. Tracing is enabled
# from outside the library on purpose — litellm's callbacks are process-global and the fork
# depends on no tracing vendor.
if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
    import litellm

    litellm.success_callback = ["langfuse"]
    litellm.failure_callback = ["langfuse"]
    print("langfuse: callbacks enabled")
else:
    print("langfuse: keys absent, skipping callback wiring")

TRACE_ID = os.getenv("E2E_TRACE_ID") or hashlib.sha1(
    f"{os.path.basename(DOC)}|{int(time.time())}".encode()
).hexdigest()

print(f"trace:   {TRACE_ID}")
print(f"model:   {MODEL}")
print(f"file:    {DOC}\n")

# ---------------------------------------------------------------- stage 1
t0 = time.perf_counter()
norm = preprocess(DOC, ocr_lang=os.getenv("E2E_OCR_LANG", "ita"))
r = norm.report
print("--- preprocess ---")
print(f"  format={r.source_format} pages={r.page_count} text={r.text_pages} "
      f"ocr={r.ocr_pages} failed={r.failed_pages}")
print(f"  chars={r.chars_extracted:,}  convert={r.convert_seconds:.2f}s "
      f"classify={r.classify_seconds:.2f}s ocr={r.ocr_seconds:.2f}s")
print(f"  wall={time.perf_counter() - t0:.2f}s\n")

# ---------------------------------------------------------------- stage 2
t1 = time.perf_counter()
tree = build_tree(
    pages=norm.pages,
    doc_name=norm.doc_name,
    model=MODEL,
    llm_metadata={
        # trace_id is THE grouping key: every generation carrying the same value lands in one
        # Langfuse trace. Without it litellm falls back to litellm_call_id — a new trace per
        # call, which is unreadable at ~40 calls per document.
        "trace_id": TRACE_ID,
        "session_id": os.getenv("E2E_SESSION_ID", "e2e-check"),
        "trace_name": f"index:{norm.doc_name}",
        "tags": ["e2e-check", "indexing"],
    },
)
print("--- build_tree ---")
print(f"  wall={time.perf_counter() - t1:.2f}s")
print(f"  doc_name={tree.get('doc_name')!r}   <-- must NOT be 'Untitled'")
print(f"  top-level nodes: {len(tree.get('structure', []))}\n")


def walk(nodes, depth=0):
    for n in nodes:
        span = f"{n.get('start_index')}-{n.get('end_index')}"
        print("  " + "  " * depth + f"[{span}] {n.get('title', '')[:70]}")
        if n.get("nodes"):
            walk(n["nodes"], depth + 1)


print("--- tree ---")
walk(tree.get("structure", []))

out = os.getenv("E2E_OUT", os.path.join(os.getcwd(), "e2e_tree.json"))
with open(out, "w", encoding="utf-8") as f:
    json.dump(tree, f, ensure_ascii=False, indent=2)
print(f"\nfull tree written to {out}")
