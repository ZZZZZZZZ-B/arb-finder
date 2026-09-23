from __future__ import annotations

import logging
from pathlib import Path


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(project_root: str | Path | None = None) -> Path:
    root = Path(project_root) if project_root is not None else Path(__file__).resolve().parent.parent
    log_path = root / "arb_finder.log"
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=[logging.FileHandler(log_path, encoding="utf-8")],
        force=True,
    )
    return log_path
