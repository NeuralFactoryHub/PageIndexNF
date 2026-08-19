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


def build_tree(source=None, *, pages=None, doc_name=None, **kwargs):
    """Build a PageIndex tree.

    Two mutually exclusive input paths:

      build_tree(pages=norm.pages, doc_name=norm.doc_name)   # preferred — see preprocess()
      build_tree(source)                                     # PDF bytes / path, must have text

    source:   PDF as raw bytes, a filesystem path str, or a pathlib.Path. bytes are handled in
              memory; nothing is written to disk.
    pages:    per-page text from preprocess(). Skips PDF parsing entirely.
    doc_name: explicit document name. Without it a bytes source falls back to PDF metadata,
              which client documents frequently lack — several docs all named "Untitled" make
              the consumer's retrieval catalog unusable.
    kwargs:   any valid config key (model, summary_model, log_dir, ...). Invalid keys raise
              ValueError (validated against DEFAULT_CONFIG).

    Returns the tree structure (dict). Does NOT persist — the caller decides.
    """
    if (source is None) == (pages is None):
        raise ValueError("Pass exactly one of `source` or `pages`.")

    opt = ConfigLoader().load(kwargs or None)

    if pages is not None:
        return page_index_main(None, opt, pages=pages, doc_name=doc_name)

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
    return page_index_main(doc, opt, doc_name=doc_name)
