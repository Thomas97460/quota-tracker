"""quota_tracker package."""

from __future__ import annotations

import sys
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _version_from_pyproject() -> str | None:
    """Read project version directly from pyproject.toml when metadata is unavailable."""

    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    try:
        with pyproject_path.open("rb") as fh:
            pyproject = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return None
    project = pyproject.get("project")
    if not isinstance(project, dict):
        return None
    pkg_version = project.get("version")
    if isinstance(pkg_version, str) and pkg_version:
        return pkg_version
    return None


try:
    __version__ = version("quota-tracker")
except PackageNotFoundError:
    __version__ = _version_from_pyproject() or "0+unknown"

try:
    from quota_tracker._dev_build import DEV_BUILD  # type: ignore
except ImportError:
    DEV_BUILD = False

_is_git = (
    not getattr(sys, "frozen", False) and (Path(__file__).resolve().parents[1] / ".git").exists()
)

if (DEV_BUILD or _is_git) and not __version__.endswith("-dev"):
    __version__ += "-dev"

__all__ = ["__version__"]
