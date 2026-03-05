from __future__ import annotations
import hashlib
from pathlib import Path
from datetime import datetime


def sha256_bytes(b: bytes) -> str:
    """Compute sha256 hex digest for dedupe/audit."""
    return hashlib.sha256(b).hexdigest()


def store_pdf(pdf_bytes: bytes, base_dir: str) -> tuple[str, str]:
    """
    Store PDF in a date-partitioned folder:
      {base_dir}/YYYY/MM/DD/{sha256}.pdf

    Returns:
      (pdf_path, sha256_digest)
    """
    digest = sha256_bytes(pdf_bytes)
    now = datetime.utcnow()
    folder = Path(base_dir) / f"{now:%Y/%m/%d}"
    folder.mkdir(parents=True, exist_ok=True)

    path = folder / f"{digest}.pdf"
    path.write_bytes(pdf_bytes)
    return str(path), digest
