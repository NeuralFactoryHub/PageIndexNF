"""Typed errors for the fork.

Upstream raises bare `Exception` and, in the LLM retry loop, returns "" on exhaustion. Both
collapse unrelated causes into one indistinguishable symptom, so a caller cannot tell a broken
document from a throttled model and cannot decide whether retrying is sensible. These types make
that distinction part of the public contract: only `LLMUnavailableError` is worth a retry.
"""


class PageIndexError(Exception):
    """Base for every error raised by this library."""

    def __init__(self, message: str, doc_name: str = None, pages: list[int] = None):
        self.doc_name = doc_name
        self.pages = pages
        context = []
        if doc_name:
            context.append(f"doc={doc_name!r}")
        if pages:
            context.append(f"pages={pages}")
        super().__init__(f"{message} ({', '.join(context)})" if context else message)


# (a) The input itself cannot be read. Never retry; the caller must fix the document.
class UnreadableInputError(PageIndexError):
    pass


class UnsupportedFormatError(UnreadableInputError):
    pass


class ConversionError(UnreadableInputError):
    pass


class OCRError(UnreadableInputError):
    pass


class NotPreprocessedError(UnreadableInputError):
    pass


class MissingSystemDependencyError(PageIndexError):
    """A required system binary (tesseract, soffice) is absent from the runtime."""


# (b) The model call failed. Transport/throttling is retryable; misconfiguration never is.
class LLMUnavailableError(PageIndexError):
    """Throttling or transport failure. THIS IS THE ONLY ERROR A CALLER SHOULD RETRY."""


class LLMConfigError(PageIndexError):
    """Rejected key, missing model, forbidden access. No retry can fix it."""


# (c) The model answered but the structure could not be built from the answer.
class TreeParseError(PageIndexError):
    pass
