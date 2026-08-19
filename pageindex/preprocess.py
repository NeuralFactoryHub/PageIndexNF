"""Document normalization: Office → PDF, scanned-page detection, OCR.

Fork-owned module. Runs BEFORE tree building, because on scanned annexes the section headings
exist only as pixels: a tree built from the text layer loses the structural boundaries exactly
where the annexes begin.

This library never installs system binaries — it asserts them. See the README for the
Dockerfile lines the consumer must provide.
"""
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .errors import (
    ConversionError,
    MissingSystemDependencyError,
    UnsupportedFormatError,
)

OFFICE_EXTENSIONS = {".doc", ".docx", ".odt", ".xls", ".xlsx", ".ods", ".ppt", ".pptx", ".odp"}

# Resolution order matters: `libreoffice` and `soffice` are the Linux names, the third is the
# macOS app bundle, which is not on PATH.
_SOFFICE_CANDIDATES = (
    "libreoffice",
    "soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
)


def _find_soffice() -> str:
    for candidate in _SOFFICE_CANDIDATES:
        resolved = shutil.which(candidate) or (candidate if os.path.isfile(candidate) else None)
        if resolved:
            return resolved
    raise MissingSystemDependencyError(
        "LibreOffice not found. Install it in the runtime image: "
        "`apt-get install -y libreoffice`"
    )


def _require_tesseract() -> None:
    if shutil.which("tesseract") is None:
        raise MissingSystemDependencyError(
            "tesseract not found. Install it in the runtime image: "
            "`apt-get install -y tesseract-ocr tesseract-ocr-ita tesseract-ocr-osd`"
        )


_CONVERSION_TIMEOUT_SECONDS = 120


def _convert_to_pdf(data: bytes, suffix: str) -> bytes:
    """Render an Office document to PDF via LibreOffice headless.

    Conversion is needed for pagination, not fidelity: PageIndex cites by page number and a
    .docx has no pages until something lays it out.
    """
    soffice = _find_soffice()
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / f"input{suffix}"
        src.write_bytes(data)
        try:
            result = subprocess.run(
                # --norestore matters: without it a previously crashed instance hangs the
                # conversion on a recovery dialog nobody will ever answer.
                # -env:UserInstallation isolates the profile: warm Lambda invocations share
                # /tmp, and two concurrent conversions would otherwise contend for one profile.
                [soffice,
                 f"-env:UserInstallation=file://{tmp}/lo_profile",
                 "--headless", "--norestore", "--convert-to", "pdf",
                 "--outdir", tmp, str(src)],
                capture_output=True,
                timeout=_CONVERSION_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as e:
            raise ConversionError(
                f"LibreOffice timed out after {_CONVERSION_TIMEOUT_SECONDS}s"
            ) from e

        out = src.with_suffix(".pdf")
        # LibreOffice can exit 0 and produce nothing, so the return code alone is not evidence.
        if result.returncode != 0 or not out.exists():
            raise ConversionError(
                f"LibreOffice failed (exit {result.returncode}): "
                f"{result.stderr.decode(errors='replace')[:500]}"
            )
        return out.read_bytes()
