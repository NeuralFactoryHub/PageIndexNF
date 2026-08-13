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
