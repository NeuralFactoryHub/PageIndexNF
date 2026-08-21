"""Fork-owned default configuration.

The library defaults live in code (not a .yaml) so they always travel in the package:
setuptools packages .py files by default, a .yaml is package-data and does not. This removes
the post-`uv add` FileNotFoundError by construction. To change defaults, edit this dict or pass
kwargs to `build_tree` / CLI flags.

A model with no provider prefix uses the OpenAI SDK directly. Other providers use
"provider/model" (e.g. "anthropic/claude-sonnet-4-6", "bedrock/eu.anthropic.claude-...").
"""

DEFAULT_CONFIG = {
    "model": "gpt-4o-2024-11-20",
    "summary_model": None,   # falls back to `model` (page_index.py:1263)
    "retrieve_model": None,  # falls back to `model`
    "toc_check_page_num": 20,
    "max_page_num_each_node": 10,
    "max_token_num_each_node": 20000,
    "if_add_node_id": "yes",
    "if_add_node_summary": "yes",
    "if_add_doc_description": "no",
    "if_add_node_text": "no",
    # "yes" = when every TOC strategy fails, return a single node spanning the document instead
    # of raising TreeParseError. Correctly extracted text is worth more to a caller as a flat
    # index than as an exception. Set to "no" to restore the raising behaviour.
    "fallback_flat_tree": "yes",
    "log_dir": None,         # None = telemetry off; set a writable path to enable (e.g. "/tmp/pageindex")
    "llm_metadata": None,    # dict forwarded verbatim to litellm (e.g. Langfuse trace_id/tags)
}
