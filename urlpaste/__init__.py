"""urlpaste: share notes and files as a link. Nothing is saved anywhere."""

from .codec import (
    DEFAULT_BASE_URL,
    PARAM,
    FileItem,
    InvalidPayloadError,
    PasswordRequiredError,
    TextItem,
    UrlpasteError,
    WrongPasswordError,
    decode,
    encode,
    is_encrypted,
    make_link,
    payload_from_link,
)

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_BASE_URL",
    "FileItem",
    "InvalidPayloadError",
    "PARAM",
    "PasswordRequiredError",
    "TextItem",
    "UrlpasteError",
    "WrongPasswordError",
    "decode",
    "encode",
    "is_encrypted",
    "make_link",
    "payload_from_link",
]
