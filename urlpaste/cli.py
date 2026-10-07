"""Command-line interface: create and open urlpaste links from the terminal.

    echo "hello" | urlpaste encode                 # text from stdin
    urlpaste encode notes.md --markdown             # a file's contents as Markdown
    urlpaste encode report.pdf                      # any small file
    urlpaste encode secrets.txt --text --password   # prompts for a password
    urlpaste decode "https://…/urlpaste/#AW…"       # print the note or save the file
"""

from __future__ import annotations

import argparse
import getpass
import mimetypes
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import __version__
from .codec import (
    DEFAULT_BASE_URL,
    FileItem,
    PasswordRequiredError,
    TextItem,
    UrlpasteError,
    decode,
    is_encrypted,
    make_link,
    payload_from_link,
)
from .limits import describe_length

MAX_INPUT_BYTES = 1024 * 1024


def _read_password(confirm: bool) -> str:
    password = getpass.getpass("Password: ")
    if confirm and password != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords don't match.")
    if not password:
        raise SystemExit("Password can't be empty.")
    return password


def _cmd_encode(args: argparse.Namespace) -> int:
    if args.path:
        path = Path(args.path)
        if not path.is_file():
            raise SystemExit(f"No such file: {path}")
        if path.stat().st_size > MAX_INPUT_BYTES:
            raise SystemExit(f"{path.name} is larger than 1 MB. The whole file has to fit inside the link.")
        raw = path.read_bytes()
    else:
        if sys.stdin.isatty():
            print("Type or paste your note, then press Ctrl-D:", file=sys.stderr)
        raw = sys.stdin.buffer.read()
        if len(raw) > MAX_INPUT_BYTES:
            raise SystemExit("Input is larger than 1 MB. The whole note has to fit inside the link.")

    if args.path and not (args.text or args.markdown):
        mime = mimetypes.guess_type(args.path)[0] or "application/octet-stream"
        item = FileItem(data=raw, name=Path(args.path).name, type=mime)
    else:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise SystemExit("That isn't UTF-8 text. Drop --text/--markdown to share it as a file.")
        item = TextItem(text=text, kind="markdown" if args.markdown else "text")

    password = _read_password(confirm=True) if args.password else None
    link = make_link(item, password=password, base_url=args.base_url)
    print(link)

    if not args.quiet:
        info = describe_length(len(link))
        print(f"\n{len(link):,} characters. {info.label}", file=sys.stderr)
        if password:
            print("Share the password separately. It is not in the link.", file=sys.stderr)
    return 0


def _cmd_decode(args: argparse.Namespace) -> int:
    payload = payload_from_link(args.link)
    password = None
    if is_encrypted(payload):
        password = _read_password(confirm=False)
    try:
        item = decode(payload, password=password)
    except PasswordRequiredError:
        password = _read_password(confirm=False)
        item = decode(payload, password=password)

    if isinstance(item, TextItem):
        if args.output:
            Path(args.output).write_text(item.text, encoding="utf-8")
            print(f"Saved to {args.output}", file=sys.stderr)
        else:
            sys.stdout.write(item.text)
            if item.text and not item.text.endswith("\n"):
                sys.stdout.write("\n")
        return 0

    target = Path(args.output) if args.output else Path(Path(item.name).name or "file")
    if target.exists() and not args.force:
        raise SystemExit(f"{target} already exists. Use --force to overwrite, or -o to pick another name.")
    target.write_bytes(item.data)
    print(f"Saved {item.name} ({len(item.data):,} bytes, {item.type}) to {target}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="urlpaste",
        description="Share notes and small files as a link. Nothing is saved anywhere: the link is the note.",
    )
    parser.add_argument("--version", action="version", version=f"urlpaste {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    enc = sub.add_parser("encode", help="turn a note or file into a link")
    enc.add_argument("path", nargs="?", help="file to share (reads text from stdin if omitted)")
    kind = enc.add_mutually_exclusive_group()
    kind.add_argument("--text", action="store_true", help="share the file's contents as plain text")
    kind.add_argument("-m", "--markdown", action="store_true", help="share as Markdown (rendered when opened)")
    enc.add_argument("-p", "--password", action="store_true", help="encrypt with a password (you'll be prompted)")
    enc.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"site that opens the link (default: {DEFAULT_BASE_URL})")
    enc.add_argument("-q", "--quiet", action="store_true", help="print only the link")
    enc.set_defaults(func=_cmd_encode)

    dec = sub.add_parser("decode", help="open a link: print the note or save the file")
    dec.add_argument("link", help="a full urlpaste link, or just the part after #")
    dec.add_argument("-o", "--output", help="write to this file instead of stdout / the original file name")
    dec.add_argument("-f", "--force", action="store_true", help="overwrite an existing file")
    dec.set_defaults(func=_cmd_decode)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except UrlpasteError as exc:
        print(f"urlpaste: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
