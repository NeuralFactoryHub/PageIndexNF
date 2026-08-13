# Plan — `build_tree` usable without a packaged `config.yaml`

> **For Claude:** REQUIRED SUB-SKILL: use `executing-plans` skill to implement task-by-task.

**Goal:** make `from pageindex import build_tree` work after `uv add` without the `config.yaml`
crash, and let `build_tree` accept any valid config key (incl. `summary_model`) via its public
API — without touching `page_index.py`.

**Architecture:** Three causes (design §4). (#1) defaults move from `config.yaml` to a Python
module `pageindex/config.py` (packaged because it is a `.py`); `ConfigLoader` imports it. (#2)
`build_tree` builds `opt` via `ConfigLoader().load(kwargs)` → `page_index_main`, instead of
delegating to the restrictive signature of `page_index()`. (#3) log the resolved LLM provider
once per model for observability. Thin fork: `page_index.py` and the ~5 importers of
`ConfigLoader` are not touched.

**Tech Stack:** Python ≥3.10, setuptools, LiteLLM→Bedrock.

**Reference:** `@backend-python`. Design: `docs/plans/2026-08-13-build-tree-config-fix/design.md`.

---

### Task 1: Defaults as a Python module (`pageindex/config.py`)

**Files:**
- Create: `pageindex/config.py`

**Step 1: Create the module with today's default values**

Same values as the current `config.yaml` (verified against the live file):

```python
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
}
```

> Imports nothing → no circular-import risk with `utils.py`.

**Step 2: Verify key parity with the current yaml**

```bash
python -c "import yaml; y=set(yaml.safe_load(open('pageindex/config.yaml'))); \
from pageindex.config import DEFAULT_CONFIG as d; \
print('MATCH' if y==set(d) else f'DIFF y-only={y-set(d)} d-only={set(d)-y}')"
```

Expected: `MATCH`.

---

### Task 2: `ConfigLoader` reads from `DEFAULT_CONFIG` (not YAML)

**Files:**
- Modify: `pageindex/utils.py` (`ConfigLoader`, L933-957; import L15)

**Step 1: Import `DEFAULT_CONFIG`**

Add near the internal imports of `utils.py` (after existing `from .` imports, or alongside the
top-level stdlib imports if none):

```python
from .config import DEFAULT_CONFIG
```

**Step 2: Simplify `ConfigLoader.__init__` and drop `_load_yaml`**

Replace the current block:

```python
class ConfigLoader:
    def __init__(self, default_path: str = None):
        if default_path is None:
            default_path = Path(__file__).parent / "config.yaml"
        self._default_dict = self._load_yaml(default_path)

    @staticmethod
    def _load_yaml(path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
```

with:

```python
class ConfigLoader:
    def __init__(self, defaults: dict = None):
        self._default_dict = dict(DEFAULT_CONFIG if defaults is None else defaults)
```

> `_validate_keys` and `load` stay **unchanged** (they still use `self._default_dict`).
> All call sites do `ConfigLoader()` with no args → compatible.

**Step 3: Remove the `yaml` import if now orphaned**

```bash
grep -n "yaml" pageindex/utils.py
```

If the only remaining occurrence is `import yaml` (L15), delete it. If `yaml` is used elsewhere,
keep it.

**Step 4: Verify**

```bash
python -c "from pageindex.utils import ConfigLoader; \
o=ConfigLoader().load({'summary_model':'x'}); print(o.model, o.summary_model)"
```

Expected: prints the default `model` and `x` — reading no file.

---

### Task 3: `build_tree` builds `opt` and calls `page_index_main`

**Files:**
- Modify: `pageindex/build_tree.py`

**Step 1: Rewrite the wrapper**

```python
"""Public library entry point for the fork.

Isolated in its own module (not page_index.py) so the fork stays thin and upstream merges do
not conflict. `build_tree` is the stable seam the consuming backend imports.

Routes through ConfigLoader + page_index_main (not page_index's restrictive signature) so ANY
valid config key — model, summary_model, retrieve_model, toggles — can be passed as a kwarg
without editing upstream page_index.py.
"""
from io import BytesIO
from pathlib import Path

from .utils import ConfigLoader
from .page_index import page_index_main


def build_tree(source, **kwargs):
    """Build a PageIndex tree from a PDF.

    source: PDF as raw bytes, a filesystem path str, or a pathlib.Path.
            bytes are handled in memory; nothing is written to disk.
    kwargs: any valid config key (model, summary_model, retrieve_model,
            toc_check_page_num, if_add_node_summary, ...). Invalid keys raise
            ValueError (validated against DEFAULT_CONFIG).

    Returns the tree structure (dict). Does NOT persist — the caller decides.
    """
    if isinstance(source, bytes):
        doc = BytesIO(source)
    elif isinstance(source, Path):
        doc = str(source)
    elif isinstance(source, str):
        doc = source
    else:
        raise TypeError(
            f"source must be bytes, str, or Path, got {type(source).__name__}"
        )
    opt = ConfigLoader().load(kwargs or None)
    return page_index_main(doc, opt)
```

> `page_index_main` (page_index.py:1236) accepts a path or `BytesIO` and returns the tree
> (`{'doc_name', 'structure'}`) — the same return `page_index` gives today.

**Step 2: Verify import + rejection of an invalid key**

```bash
python -c "from pageindex import build_tree; print(build_tree)"
python -c "from pageindex import build_tree
try:
    build_tree(b'x', bogus_key=1)
except Exception as e:
    print(type(e).__name__, e)"
```

Expected: prints the function; then `ValueError Unknown config keys: {'bogus_key'}` (validation
runs before PDF parsing).

---

### Task 4: Log the resolved LLM provider (observability)

**Files:**
- Modify: `pageindex/utils.py` (`llm_completion` L57, `llm_acompletion` L103; new helper)

**Step 1: Add the helper** (near `_is_openai_model`, ~L40)

```python
_logged_models = set()

def _log_provider_once(model, use_openai_sdk):
    """Log the resolved LLM provider once per distinct model per process.

    The fork routes by model-string prefix (see _is_openai_model); this makes the
    actual provider visible without enabling LiteLLM verbose logging. Guarded so a
    tree's hundreds of calls do not spam the log.
    """
    if model in _logged_models:
        return
    _logged_models.add(model)
    provider = "openai" if use_openai_sdk else (
        model.split("/", 1)[0] if model and "/" in model else "openai"
    )
    logging.info(f"LLM dispatch: provider={provider!r} model={model!r}")
```

**Step 2: Call it in both completion functions**

In `llm_completion` (L57) and `llm_acompletion` (L103), add the call right **after** the prefix
stripping block and **before** `max_retries = ...`:

```python
    if model:
        model = model.removeprefix("litellm/")
        if use_openai_sdk:
            model = model.removeprefix("openai/")
    _log_provider_once(model, use_openai_sdk)   # <-- add this line
    max_retries = 10
```

> Placed after stripping so the logged model matches what is sent to the SDK/LiteLLM, and once
> per distinct model so it does not repeat per node.

**Step 3: Verify**

```bash
python -c "import logging; logging.basicConfig(level=logging.INFO); \
from pageindex.utils import _log_provider_once; \
_log_provider_once('bedrock/eu.anthropic.claude-x', False); \
_log_provider_once('bedrock/eu.anthropic.claude-x', False); \
_log_provider_once('gpt-4o', True)"
```

Expected: two INFO lines only — `provider='bedrock'` (once, not twice) and `provider='openai'`.

---

### Task 5: Delete `config.yaml`

**Files:**
- Delete: `pageindex/config.yaml`

```bash
git rm pageindex/config.yaml
```

> Nothing reads it anymore (ConfigLoader moved to `config.py`). Verify:
> `grep -rn "config.yaml" pageindex/` → no code hits (only docstring text, fixed in Task 5).

---

### Task 6: Update textual references + `FORK_NOTES.md`

**Files:**
- Modify: `run_pageindex.py` (`--model` help L23, `--summary-model` help L25, comment L149)
- Modify: `pageindex/tree_optimize.py` (docstring L47, help L846)
- Modify: `FORK_NOTES.md` (L55 and divergence #1 status)

**Step 1:** Replace `config.yaml` mentions → `config.py` in the help text / docstrings /
comments of those files (text only, no logic change).

**Step 2:** In `FORK_NOTES.md`, extend divergence #1: note that defaults live in
`pageindex/config.py`, that `build_tree` accepts any valid key via kwargs, and that the resolved
LLM provider is logged once per model at INFO.

**Step 3: Verify no code refs remain**

```bash
grep -rn "config.yaml" pageindex/ run_pageindex.py
```

Expected: no results (or only already-updated text).

---

### Task 7: Regression + real-PDF verification

**Files:** none (verification)

**Step 1: Existing suite** (adds no tests, per CLAUDE.md)

```bash
python -m pytest -q
```

Expected: same baseline as before (no new failures).

**Step 2: Functional check with a real PDF** (owner runs; needs Bedrock credentials in the
environment)

```python
from pathlib import Path
from pageindex import build_tree
tree = build_tree(
    Path("sample.pdf").read_bytes(),
    model="bedrock/eu.anthropic.claude-...",  # summaries fall back to this model
    if_add_node_summary="yes",
    # summary_model="bedrock/…",  # optional: only to use a different summary model
)
assert tree["structure"], "empty tree"
print("OK:", tree["doc_name"], "nodes:", len(tree["structure"]))
```

Expected: builds the tree with summaries via the public API — without touching internals. With
`logging` at INFO, a `LLM dispatch: provider='bedrock' model='bedrock/…'` line appears once,
confirming the Bedrock route.

---

## Unresolved questions

- Is `config.py` the final name, or do you prefer `defaults.py` to avoid confusion with the
  `config` (SimpleNamespace) alias already in `utils.py`? (No technical clash.)
- Document this as divergence #4 in `FORK_NOTES.md` instead of extending #1?
- Functional verification (Task 6 Step 2) depends on the owner's Bedrock credentials.
