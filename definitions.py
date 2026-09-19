"""Dagster entry point (`dagster dev`, `dagster definitions validate`, ...).

Adds src/ to sys.path by hand, since this project isn't installed as a
package -- src/ is only importable once it's on sys.path.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from oil_pipeline.dagster_defs.definitions import defs

__all__ = ["defs"]
