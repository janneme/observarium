"""Utility for downloading catalogue files to a local cache directory."""

import shutil
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

_ALLOWED_SCHEMES: frozenset[str] = frozenset({"https"})


def _validate_url(url: str) -> None:
    """Raise ValueError when the URL scheme is not HTTPS."""
    scheme = urlparse(url).scheme
    if scheme not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"URL scheme {scheme!r} is not allowed; only HTTPS is permitted."
        )


class Downloader:
    """Downloads remote files to a local cache directory.

    Files already present on disk are not re-downloaded.
    """

    def __init__(self, cache_dir: Path, debug: bool = False) -> None:
        self._cache_dir = cache_dir
        self._debug = debug
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    def fetch(self, url: str, filename: str) -> Path:
        """Return path to the local file, downloading it if absent.

        Args:
            url: HTTPS URL of the remote file.
            filename: Local filename within the cache directory.

        Returns:
            Path to the cached local file.
        """
        dest = self._cache_dir / filename
        if not dest.exists():
            _validate_url(url)
            print(f"Downloading {url} → {dest}")
            with urllib.request.urlopen(url) as response:  # noqa: S310
                with dest.open("wb") as fh:
                    shutil.copyfileobj(response, fh)
        elif self._debug:
            print(f"Using cached {dest}")
        return dest
