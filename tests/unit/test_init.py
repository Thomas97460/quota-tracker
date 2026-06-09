from __future__ import annotations

from unittest.mock import patch

from quota_tracker import _version_from_pyproject


def test_version_from_pyproject() -> None:
    version = _version_from_pyproject()
    assert version is not None
    assert isinstance(version, str)


def test_version_from_pyproject_invalid() -> None:
    with patch("quota_tracker.__init__.tomllib.load", side_effect=OSError):
        assert _version_from_pyproject() is None
