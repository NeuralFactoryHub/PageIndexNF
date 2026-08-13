# Fork Customizations Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: use executing-plans skill to implement this plan task-by-task.

**Goal:** Make the PageIndex fork `uv add`-installable with a stable `build_tree` entry point, fix the `offset=None` crash, and rewrite node summaries to be node-specific and language-preserving.

**Architecture:** Three isolated divergences on `feature/customizations`. Fork additions live in a NEW file (`pageindex/build_tree.py`) to keep the fork thin and avoid merge conflicts with the large upstream `page_index.py`. Two in-place minimal patches (offset, summary prompt). No tests added (per CLAUDE.md). No persistence in the library — `build_tree` returns the tree.

**Tech Stack:** Python ≥3.10, setuptools build backend, LiteLLM→Bedrock (needs `boto3`).

**Reference:** `@backend-python` for Python patterns. Design: `docs/plans/2026-08-13-fork-customizations/design.md`.

---

### Task 1: Packaging metadata (`pyproject.toml`)

**Files:**
- Create: `pyproject.toml`

**Step 1: Write pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "pageindexnf"
version = "0.1.0"
description = "Neural Factory fork of PageIndex — reasoning-based tree index for long documents."
requires-python = ">=3.10"
dependencies = [
    "litellm==1.84.0",
    "pymupdf==1.26.4",
    "PyPDF2==3.0.1",
    "pypdfium2==4.30.0",
    "python-dotenv==1.2.2",
    "pyyaml==6.0.2",
    "regex>=2024.0.0",
    "sortedcontainers==2.4.0",
    "boto3",
]

[tool.setuptools.packages.find]
include = ["pageindex*"]
```

> `boto3` is added (missing upstream; LiteLLM→Bedrock needs it). Deps mirror `requirements.txt`. `packages.find` with `pageindex*` captures `pageindex` and the `pageindex.flash` subpackage.

**Step 2: Verify metadata builds**

```bash
python -m pip install --upgrade build >/dev/null && python -m build --wheel 2>&1 | tail -5
```

Expected: a wheel is produced under `dist/` with no errors. (If `build` is unavailable, skip to Task 2 verification which installs the package directly.)

---

### Task 2: `build_tree` public entry point

**Files:**
- Create: `pageindex/build_tree.py`
- Modify: `pageindex/__init__.py`

**Step 1: Implement `build_tree`**

Create `pageindex/build_tree.py`:

```python
"""Public library entry point for the fork.

Isolated in its own module (not page_index.py) so the fork stays thin and
upstream merges do not conflict. `build_tree` is the stable seam the consuming
backend imports; internals may change upstream without breaking it.
"""
from io import BytesIO
from pathlib import Path

from .page_index import page_index


def build_tree(source, **kwargs):
    """Build a PageIndex tree from a PDF.

    source: PDF as raw bytes, a filesystem path str, or a pathlib.Path.
            bytes are handled in memory; nothing is written to disk.
    kwargs: forwarded to `page_index` (model, toc_check_page_num,
            max_page_num_each_node, if_add_node_summary, ...).

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
    return page_index(doc, **kwargs)
```

> `page_index` (page_index.py:1280) already builds the `opt` config from kwargs and accepts a path or `BytesIO` (validated in `page_index_main`, page_index.py:1235). So `build_tree` is a thin normalizing wrapper — the sibling of the CLI in `run_pageindex.py`.

**Step 2: Export it**

Modify `pageindex/__init__.py` — add after the existing imports:

```python
from .build_tree import build_tree
```

**Step 3: Verify install + import**

```bash
pip install -e . 2>&1 | tail -3
python -c "from pageindex import build_tree; print(build_tree)"
```

Expected: install succeeds; prints `<function build_tree at 0x...>`.

---

### Task 3: Fix `offset=None` crash

**Files:**
- Modify: `pageindex/page_index.py:506-512` (`add_page_offset_to_toc_json`)

**Step 1: Default offset to 0**

Replace the function body's start so `None` becomes `0`:

```python
def add_page_offset_to_toc_json(data, offset):
    if offset is None:
        offset = 0
    for i in range(len(data)):
        if data[i].get('page') is not None and isinstance(data[i]['page'], int):
            data[i]['physical_index'] = data[i]['page'] + offset
            del data[i]['page']

    return data
```

> Root cause: `calculate_page_offset` returns `None` when no page pairs match (page_index.py:496); `None + int` crashes. `0` is the identity offset (physical == logical), so aligned docs are unchanged.

**Step 2: Verify no crash path**

```bash
python -c "from pageindex.page_index import add_page_offset_to_toc_json as f; print(f([{'page': 5}], None))"
```

Expected: `[{'physical_index': 5}]` — no `TypeError`.

---

### Task 4: Node-distinctive summary prompt

**Files:**
- Modify: `pageindex/utils.py:637-645` (`generate_node_summary`)

**Step 1: Replace the prompt**

```python
async def generate_node_summary(node, model=None):
    prompt = f"""You are given one section of a larger document. Write a summary of THIS
section only. State directly the specific topics, entities, values, and
details it contains. Do NOT describe the document as a whole, do NOT
restate its purpose or legal framework, and do NOT begin with phrases
like "This document is..." or "This section describes...". Start with the
content itself. Write in the same language as the section text.

Section text: {node['text']}

Return only the summary.
"""
    response = await llm_acompletion(model, prompt)
    return response
```

> Only the OSS path (`generate_node_summary`) changes. The flash path (`summarize_tree`, utils.py:741) has its own prompts and is out of scope (design §7 OQ1, resolved). `SUMMARY_RAW_TEXT_TOKENS` behavior is untouched.

**Step 2: Verify import still clean**

```bash
python -c "from pageindex.utils import generate_node_summary; print('ok')"
```

Expected: `ok`.

---

### Task 5: Regression check + FORK_NOTES status

**Files:**
- Modify: `FORK_NOTES.md` (flip the three `Status: TODO` → `Status: DONE`)

**Step 1: Run the existing test suite** (does not add tests — runs upstream's)

```bash
python -m pytest -q
```

Expected: same pass/fail baseline as before the changes (no new failures).

**Step 2: Update FORK_NOTES statuses** to `DONE` for divergences #1, #2, #3.

---

## Unresolved questions

- Package name `pageindexnf` / version `0.1.0` / `requires-python ">=3.10"` — assumed; confirm.
- `boto3` unpinned (upstream pins others) — pin a version?
- Dependency list duplicated in `pyproject.toml` and `requirements.txt` — keep both (CI uses requirements) or make one source of truth later?
