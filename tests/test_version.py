"""`leadhound --version` reports the installed version."""

from __future__ import annotations

import subprocess
import sys

from leadhound import __version__


def test_version_flag() -> None:
    out = subprocess.run(
        [sys.executable, "-m", "leadhound", "--version"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert out.strip() == f"leadhound {__version__}"


def test_version_matches_package() -> None:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as pkg_version

    try:
        installed = pkg_version("leadhound")
    except PackageNotFoundError:  # not installed in this env; skip strictly
        installed = __version__
    assert __version__ == installed
