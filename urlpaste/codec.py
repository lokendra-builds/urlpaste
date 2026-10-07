"""Encode notes and files into urlpaste links, and decode them back.

Wire format (before base64url):

    [format byte] [body]
    format 1 = plain:      body = deflate(packed)
    format 2 = encrypted:  body = salt(16) | iv(12) | AES-GCM(deflate(packed))

    packed = metaLength (uint32 BE) | meta JSON (UTF-8) | content bytes
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import struct
import zlib
from dataclasses import dataclass
from typing import Literal, Optional, Union
from urllib.parse import parse_qs, urlsplit

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

FORMAT_PLAIN = 1
FORMAT_ENCRYPTED = 2
SALT_BYTES = 16
IV_BYTES = 12
TAG_BYTES = 16
PBKDF2_ITERATIONS = 600_000

# Guards against "zip bombs": a tiny link that inflates to gigabytes.
MAX_DECODED_BYTES = 20 * 1024 * 1024

DEFAULT_BASE_URL = "https://urlpaste.streamlit.app/"

# Query parameter that carries the payload: https://urlpaste.streamlit.app/?n=<payload>
PARAM = "n"

Kind = Literal["text", "markdown", "file"]
KINDS = ("text", "markdown", "file")

_BASE64URL = re.compile(r"^[A-Za-z0-9_-]*$")


class UrlpasteError(Exception):
    """Base class for all decoding errors."""


class PasswordRequiredError(UrlpasteError):
    def __init__(self) -> None:
        super().__init__("This link is password protected.")


class WrongPasswordError(UrlpasteError):
    def __init__(self) -> None:
        super().__init__("Wrong password, or the link is damaged.")


class InvalidPayloadError(UrlpasteError):
    def __init__(self, reason: str) -> None:
        super().__init__(f"This link is broken or incomplete ({reason}).")


@dataclass(frozen=True)
class TextItem:
    text: str
    kind: Literal["text", "markdown"] = "text"


@dataclass(frozen=True)
class FileItem:
    data: bytes
    name: str = "file"
    type: str = "application/octet-stream"
    kind: Literal["file"] = "file"


Item = Union[TextItem, FileItem]


# ---------- base64url ----------


def to_base64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def from_base64url(text: str) -> bytes:
    if not _BASE64URL.match(text):
        raise InvalidPayloadError("unexpected characters")
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError) as exc:
        raise InvalidPayloadError("not valid base64") from exc


# ---------- compression ----------


def _deflate(data: bytes) -> bytes:
    # wbits=-15 means raw deflate, matching CompressionStream("deflate-raw").
    compressor = zlib.compressobj(level=9, wbits=-15)
    return compressor.compress(data) + compressor.flush()


def _inflate(data: bytes) -> bytes:
    decompressor = zlib.decompressobj(wbits=-15)
    try:
        out = decompressor.decompress(data, MAX_DECODED_BYTES + 1)
        if len(out) > MAX_DECODED_BYTES or decompressor.unconsumed_tail:
            raise InvalidPayloadError("content is too large")
        out += decompressor.flush()
    except zlib.error as exc:
        raise InvalidPayloadError("could not decompress") from exc
    if not decompressor.eof:
        raise InvalidPayloadError("could not decompress")
    return out


# ---------- encryption ----------


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=PBKDF2_ITERATIONS)
    return kdf.derive(password.encode("utf-8"))


def _encrypt(data: bytes, password: str) -> bytes:
    salt = os.urandom(SALT_BYTES)
    iv = os.urandom(IV_BYTES)
    return salt + iv + AESGCM(_derive_key(password, salt)).encrypt(iv, data, None)


def _decrypt(data: bytes, password: str) -> bytes:
    if len(data) < SALT_BYTES + IV_BYTES + TAG_BYTES:
        raise InvalidPayloadError("encrypted data is truncated")
    salt, iv, ciphertext = data[:SALT_BYTES], data[SALT_BYTES : SALT_BYTES + IV_BYTES], data[SALT_BYTES + IV_BYTES :]
    try:
        return AESGCM(_derive_key(password, salt)).decrypt(iv, ciphertext, None)
    except InvalidTag as exc:
        raise WrongPasswordError() from exc


# ---------- packing ----------


def _pack(item: Item) -> bytes:
    if isinstance(item, FileItem):
        meta = {"k": "file", "n": item.name or "file", "t": item.type or "application/octet-stream"}
        content = item.data
    elif isinstance(item, TextItem):
        if item.kind not in ("text", "markdown"):
            raise ValueError(f"Unknown kind: {item.kind}")
        meta = {"k": item.kind}
        content = item.text.encode("utf-8")
    else:
        raise TypeError(f"Expected TextItem or FileItem, got {type(item).__name__}")
    meta_bytes = json.dumps(meta, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return struct.pack(">I", len(meta_bytes)) + meta_bytes + content


def _unpack(data: bytes) -> Item:
    if len(data) < 4:
        raise InvalidPayloadError("missing header")
    (meta_length,) = struct.unpack(">I", data[:4])
    if 4 + meta_length > len(data):
        raise InvalidPayloadError("header is damaged")
    try:
        meta = json.loads(data[4 : 4 + meta_length].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidPayloadError("header is damaged") from exc
    if not isinstance(meta, dict) or meta.get("k") not in KINDS:
        raise InvalidPayloadError("unknown content type")
    content = data[4 + meta_length :]

    if meta["k"] == "file":
        return FileItem(
            data=content,
            name=str(meta.get("n") or "file"),
            type=str(meta.get("t") or "application/octet-stream"),
        )
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidPayloadError("text is not valid UTF-8") from exc
    return TextItem(text=text, kind=meta["k"])


# ---------- public API ----------


def encode(item: Item, password: Optional[str] = None) -> str:
    """Encode an item into a URL-safe base64url payload."""
    compressed = _deflate(_pack(item))
    if password:
        return to_base64url(bytes([FORMAT_ENCRYPTED]) + _encrypt(compressed, password))
    return to_base64url(bytes([FORMAT_PLAIN]) + compressed)


def decode(payload: str, password: Optional[str] = None) -> Item:
    """Decode a payload. Raises PasswordRequiredError, WrongPasswordError or InvalidPayloadError."""
    data = from_base64url(payload)
    if len(data) < 2:
        raise InvalidPayloadError("empty")
    fmt, body = data[0], data[1:]
    if fmt == FORMAT_ENCRYPTED:
        if not password:
            raise PasswordRequiredError()
        body = _decrypt(body, password)
    elif fmt != FORMAT_PLAIN:
        raise InvalidPayloadError("made by an unknown version")
    return _unpack(_inflate(body))


def is_encrypted(payload: str) -> bool:
    try:
        return from_base64url(payload[:4])[0] == FORMAT_ENCRYPTED
    except (UrlpasteError, IndexError):
        return False


def make_link(item: Item, password: Optional[str] = None, base_url: str = DEFAULT_BASE_URL) -> str:
    """Encode an item and return a full shareable link."""
    base = base_url.split("?", 1)[0].split("#", 1)[0]
    return f"{base}?{PARAM}={encode(item, password)}"


def payload_from_link(link: str) -> str:
    """Accept a full link (``?n=…`` or ``#…``) or a bare payload, and return just the payload."""
    link = link.strip()
    query = urlsplit(link).query
    if query:
        values = parse_qs(query).get(PARAM)
        if values:
            return values[0]
    if "#" in link:
        return link.split("#", 1)[1]
    return link
