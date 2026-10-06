from __future__ import annotations

import gzip
import hashlib
import mimetypes
import threading
from dataclasses import dataclass
from pathlib import Path

from .. import __version__

STATIC_ROOT = Path(__file__).resolve().parent / "static"

_EXTRA_CONTENT_TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".ttf": "font/ttf",
    ".map": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}
_COMPRESSIBLE_SUFFIXES = frozenset({".js", ".mjs", ".css", ".html", ".json", ".webmanifest", ".svg", ".txt", ".map"})
_MINIMUM_COMPRESSION_BYTES = 1024


class AssetNotFoundError(FileNotFoundError):
    pass


@dataclass(frozen=True)
class Asset:
    path: str
    content_type: str
    payload: bytes
    etag: str
    immutable: bool
    compressible: bool

    def header_etag(self, encoding: str) -> str:
        suffix = "-gzip" if encoding == "gzip" else ""
        return '"' + self.etag + suffix + '"'


class AssetStore:
    def __init__(self, root: Path | None = None) -> None:
        self._root = Path(root) if root is not None else STATIC_ROOT
        self._lock = threading.Lock()
        self._cache: dict[str, Asset] = {}
        self._compressed: dict[str, bytes] = {}

    @property
    def root(self) -> Path:
        return self._root

    def resolve(self, request_path: str) -> Asset:
        relative = self._normalize(request_path)
        with self._lock:
            cached = self._cache.get(relative)
        if cached is not None:
            return cached
        absolute = (self._root / relative).resolve()
        root = self._root.resolve()
        if root != absolute and root not in absolute.parents:
            raise AssetNotFoundError(relative)
        if not absolute.is_file():
            raise AssetNotFoundError(relative)
        payload = absolute.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        asset = Asset(
            path=relative,
            content_type=_content_type(relative),
            payload=payload,
            etag=digest[:40],
            immutable=relative.startswith("vendor/"),
            compressible=_is_compressible(relative, payload),
        )
        with self._lock:
            self._cache[relative] = asset
        return asset

    def compressed_payload(self, asset: Asset) -> bytes:
        with self._lock:
            cached = self._compressed.get(asset.etag)
        if cached is not None:
            return cached
        payload = gzip.compress(asset.payload, compresslevel=9, mtime=0)
        with self._lock:
            self._compressed[asset.etag] = payload
        return payload

    def environment_hash(self) -> str:
        digest = hashlib.sha256()
        digest.update(__version__.encode("utf-8"))
        if self._root.is_dir():
            for path in sorted(self._root.rglob("*")):
                if path.is_file():
                    digest.update(str(path.relative_to(self._root)).encode("utf-8"))
                    digest.update(str(path.stat().st_size).encode("utf-8"))
        return digest.hexdigest()[:16]

    def _normalize(self, request_path: str) -> str:
        text = str(request_path or "").split("?", 1)[0].split("#", 1)[0]
        text = text.replace("\\", "/")
        while "//" in text:
            text = text.replace("//", "/")
        if text.startswith("/"):
            text = text[1:]
        if not text:
            text = "index.html"
        if text.endswith("/"):
            text += "index.html"
        parts = [part for part in text.split("/") if part not in ("", ".")]
        if any(part == ".." for part in parts):
            raise AssetNotFoundError(request_path)
        return "/".join(parts)


def _is_compressible(relative: str, payload: bytes) -> bool:
    if len(payload) < _MINIMUM_COMPRESSION_BYTES:
        return False
    return Path(relative).suffix.lower() in _COMPRESSIBLE_SUFFIXES


def _content_type(relative: str) -> str:
    suffix = Path(relative).suffix.lower()
    if suffix in _EXTRA_CONTENT_TYPES:
        return _EXTRA_CONTENT_TYPES[suffix]
    guessed, _ = mimetypes.guess_type(relative)
    if guessed:
        return guessed
    return "application/octet-stream"
