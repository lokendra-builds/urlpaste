import re

import pytest

from urlpaste import (
    FileItem,
    InvalidPayloadError,
    PasswordRequiredError,
    TextItem,
    WrongPasswordError,
    decode,
    encode,
    is_encrypted,
    make_link,
    payload_from_link,
)
from urlpaste.codec import from_base64url, to_base64url
from urlpaste.limits import describe_length

URL_SAFE = re.compile(r"^[A-Za-z0-9_-]+$")


def test_plain_text_round_trips():
    payload = encode(TextItem("hello world"))
    assert URL_SAFE.match(payload)
    assert decode(payload) == TextItem("hello world")


def test_markdown_kind_is_preserved():
    item = TextItem("# Title\n\n- one\n- two", kind="markdown")
    assert decode(encode(item)) == item


@pytest.mark.parametrize("text", ["नमस्ते दुनिया 👋", "café ✓ 𝔘𝔫𝔦𝔠𝔬𝔡𝔢", "", "line1\r\nline2\ttab"])
def test_unicode_and_edge_text_survive(text):
    assert decode(encode(TextItem(text))).text == text


def test_binary_file_round_trips_byte_for_byte():
    data = bytes((i * 31 + 7) % 256 for i in range(4096))
    item = FileItem(data=data, name="data.bin", type="application/octet-stream")
    assert decode(encode(item)) == item


def test_compression_beats_plain_base64_by_far():
    text = "The quick brown fox jumps over the lazy dog. " * 200
    assert len(encode(TextItem(text))) < len(text) * 4 / 3 / 10


def test_encrypted_round_trip():
    payload = encode(TextItem("secret"), password="hunter2")
    assert is_encrypted(payload)
    assert decode(payload, password="hunter2") == TextItem("secret")


def test_encrypted_payload_hides_plaintext():
    payload = encode(TextItem("my-api-key-1234567890"), password="pw")
    assert b"my-api-key" not in from_base64url(payload)


def test_same_input_encrypts_differently_each_time():
    assert encode(TextItem("same"), password="pw") != encode(TextItem("same"), password="pw")


def test_missing_password():
    with pytest.raises(PasswordRequiredError):
        decode(encode(TextItem("x"), password="pw"))


def test_wrong_password():
    with pytest.raises(WrongPasswordError):
        decode(encode(TextItem("x"), password="right"), password="wrong")


def test_plain_payload_is_not_encrypted():
    assert not is_encrypted(encode(TextItem("x")))


def test_truncated_link_fails_cleanly():
    payload = encode(TextItem("a fairly long note that will be cut in half " * 5))
    with pytest.raises(InvalidPayloadError):
        decode(payload[: len(payload) // 2])


@pytest.mark.parametrize("bad", ["not a payload!", "A", to_base64url(bytes([9, 1, 2, 3]))])
def test_garbage_input(bad):
    with pytest.raises(InvalidPayloadError):
        decode(bad)


def test_tampered_encrypted_payload_is_rejected():
    data = bytearray(from_base64url(encode(TextItem("integrity"), password="pw")))
    data[-1] ^= 0xFF
    with pytest.raises(WrongPasswordError):
        decode(to_base64url(bytes(data)), password="pw")


def test_zip_bomb_is_refused():
    payload = encode(FileItem(data=bytes(25 * 1024 * 1024), name="zeros"))
    assert len(payload) < 100_000
    with pytest.raises(InvalidPayloadError, match="too large"):
        decode(payload)


def test_make_link_and_extract_payload():
    link = make_link(TextItem("hi"), base_url="https://example.com/app/?old=1#frag")
    assert link.startswith("https://example.com/app/?n=")
    assert decode(payload_from_link(link)) == TextItem("hi")


def test_payload_from_link_accepts_all_forms():
    payload = encode(TextItem("hi"))
    assert payload_from_link(payload) == payload
    assert payload_from_link(f"https://x.dev/?n={payload}") == payload
    assert payload_from_link(f"https://x.dev/#{payload}") == payload
    assert payload_from_link(f"  https://x.dev/?a=1&n={payload}  ") == payload


def test_length_guidance():
    assert describe_length(100).level == "ok"
    assert describe_length(5_000).level == "warn"
    assert describe_length(3_000_000).level == "bad"
