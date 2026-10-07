import io

import pytest

from urlpaste import FileItem, TextItem, decode, payload_from_link
from urlpaste.cli import main


def run(monkeypatch, capsys, argv, stdin=b"", passwords=()):
    stream = io.TextIOWrapper(io.BytesIO(stdin), encoding="utf-8")
    monkeypatch.setattr("sys.stdin", stream)
    answers = iter(passwords)
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))
    code = main(argv)
    out, err = capsys.readouterr()
    return code, out, err


def test_encode_stdin_text(monkeypatch, capsys):
    code, out, err = run(monkeypatch, capsys, ["encode", "-q"], stdin="hello from cli".encode())
    assert code == 0
    assert decode(payload_from_link(out.strip())) == TextItem("hello from cli")
    assert err == ""


def test_encode_markdown_file(monkeypatch, capsys, tmp_path):
    note = tmp_path / "notes.md"
    note.write_text("# Hi", encoding="utf-8")
    code, out, _ = run(monkeypatch, capsys, ["encode", str(note), "--markdown", "-q"])
    assert code == 0
    assert decode(payload_from_link(out.strip())) == TextItem("# Hi", kind="markdown")


def test_encode_binary_file_keeps_name_and_type(monkeypatch, capsys, tmp_path):
    png = tmp_path / "pic.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(range(50)))
    code, out, _ = run(monkeypatch, capsys, ["encode", str(png), "-q"])
    item = decode(payload_from_link(out.strip()))
    assert code == 0
    assert isinstance(item, FileItem)
    assert (item.name, item.type, item.data) == ("pic.png", "image/png", png.read_bytes())


def test_password_round_trip(monkeypatch, capsys):
    _, out, err = run(monkeypatch, capsys, ["encode", "-p"], stdin=b"top secret", passwords=["pw", "pw"])
    link = out.strip()
    assert "separately" in err
    code, out, _ = run(monkeypatch, capsys, ["decode", link], passwords=["pw"])
    assert code == 0
    assert out == "top secret\n"


def test_mismatched_passwords_abort(monkeypatch, capsys):
    with pytest.raises(SystemExit, match="don't match"):
        run(monkeypatch, capsys, ["encode", "-p"], stdin=b"x", passwords=["a", "b"])


def test_wrong_password_returns_error(monkeypatch, capsys):
    _, out, _ = run(monkeypatch, capsys, ["encode", "-p", "-q"], stdin=b"x", passwords=["pw", "pw"])
    code, _, err = run(monkeypatch, capsys, ["decode", out.strip()], passwords=["nope"])
    assert code == 1
    assert "Wrong password" in err


def test_decode_file_writes_and_refuses_overwrite(monkeypatch, capsys, tmp_path):
    src = tmp_path / "data.bin"
    src.write_bytes(bytes(range(256)))
    _, out, _ = run(monkeypatch, capsys, ["encode", str(src), "-q"])
    target = tmp_path / "out.bin"

    code, _, _ = run(monkeypatch, capsys, ["decode", out.strip(), "-o", str(target)])
    assert code == 0
    assert target.read_bytes() == src.read_bytes()

    with pytest.raises(SystemExit, match="already exists"):
        run(monkeypatch, capsys, ["decode", out.strip(), "-o", str(target)])


def test_decode_broken_link(monkeypatch, capsys):
    code, _, err = run(monkeypatch, capsys, ["decode", "https://x.dev/?n=AAAA"])
    assert code == 1
    assert "broken" in err


def test_large_file_is_rejected(monkeypatch, capsys, tmp_path):
    big = tmp_path / "big.bin"
    big.write_bytes(bytes(1024 * 1024 + 1))
    with pytest.raises(SystemExit, match="larger than 1 MB"):
        run(monkeypatch, capsys, ["encode", str(big)])
