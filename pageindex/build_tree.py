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
