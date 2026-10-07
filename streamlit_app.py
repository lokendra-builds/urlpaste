"""urlpaste web app: create and open links where the link itself is the note.

Run locally:  streamlit run streamlit_app.py
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

import streamlit as st

from urlpaste import (
    FileItem,
    InvalidPayloadError,
    PasswordRequiredError,
    TextItem,
    WrongPasswordError,
    decode,
    is_encrypted,
    make_link,
)
from urlpaste.codec import PARAM
from urlpaste.limits import describe_length

MAX_FILE_BYTES = 1024 * 1024
MAX_NOTE_CHARS = 500_000
REPO_URL = "https://github.com/lokendra-builds/urlpaste"
AUTHOR_URL = "https://github.com/lokendra-builds"
ASSETS = Path(__file__).parent / "assets"

st.set_page_config(
    page_title="urlpaste – Share notes and files as a link. Nothing is saved.",
    page_icon=str(ASSETS / "logo.png"),
    layout="wide",
    menu_items={
        "Get help": f"{REPO_URL}#readme",
        "Report a bug": f"{REPO_URL}/issues",
        "About": f"**urlpaste**: the link is the note. Nothing is saved anywhere.\n\n[Source on GitHub]({REPO_URL})",
    },
)

# Static styling only: no user content is ever placed inside st.html.
STYLES = """
<style>
  /* Tighten the top: Streamlit reserves ~6rem above the content by default */
  [data-testid="stHeader"] { background: transparent; height: 2.5rem; }
  .block-container, [data-testid="stMainBlockContainer"] { padding-top: 1.25rem !important; padding-bottom: 2rem; }
  .up-nav { display: flex; align-items: center; justify-content: space-between; gap: 1rem; margin: 0 0 1.6rem 0; }
  .up-wordmark { display: flex; align-items: center; gap: .65rem; text-decoration: none !important; }
  .up-wordmark img { width: 38px; height: 38px; flex: none; }
  .up-wordmark span { font-weight: 800; font-size: 1.55rem; letter-spacing: -.03em; color: #ececf2; line-height: 1; }
  .up-wordmark b {
    font-weight: 800; background: linear-gradient(90deg, #818cf8, #5eead4);
    -webkit-background-clip: text; background-clip: text; color: transparent;
  }
  .up-navlinks { display: flex; gap: .5rem; flex-wrap: wrap; }
  .up-navlinks a {
    padding: .4rem .9rem; border-radius: 999px; border: 1px solid #262633;
    color: #c7d2fe !important; text-decoration: none !important; font-size: .9rem;
  }
  .up-navlinks a.star { background: #16161f; }
  .up-navlinks a:hover { border-color: #818cf8; }
  .up-eyebrow {
    display: inline-block; padding: 4px 12px; border-radius: 999px;
    background: rgba(94, 234, 212, .12); color: #5eead4;
    font-weight: 600; font-size: .8rem; letter-spacing: .08em; text-transform: uppercase;
  }
  .up-hero h1 {
    font-size: clamp(2.2rem, 5vw, 3.4rem) !important; line-height: 1.05 !important;
    letter-spacing: -.02em; margin: .45rem 0 .55rem 0 !important; padding: 0 !important;
  }
  .up-hero h1 em { font-style: normal; color: #818cf8; }
  .up-hero p { color: #a1a1b5; font-size: 1.1rem; max-width: 62rem; margin: 0; }
  .up-hero strong { color: #ececf2; }

  /* Horizontal timeline on wide screens, vertical on narrow ones. Plain divs, so Streamlit's list styles can't interfere. */
  .up-tl { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 0 1.5rem; margin: .75rem 0 0 0; }
  .up-st { position: relative; }
  .up-st:not(:last-child)::after {
    content: ""; position: absolute; top: 19px; left: 52px; right: calc(-1.5rem + 8px); height: 2px;
    background: linear-gradient(90deg, #818cf8, #5eead4); opacity: .55;
  }
  .up-dot {
    position: relative; z-index: 1; width: 40px; height: 40px; border-radius: 50%;
    display: grid; place-items: center; font-weight: 700; font-size: .95rem;
    background: #16161f; color: #c7d2fe; border: 2px solid #818cf8;
  }
  .up-st.final .up-dot { border-color: #5eead4; color: #5eead4; }
  .up-st h4 { margin: .9rem 0 .35rem 0 !important; padding: 0 !important; font-size: 1.02rem !important; color: #ececf2; }
  .up-st p { margin: 0 0 .65rem 0; color: #a1a1b5; font-size: .9rem; line-height: 1.5; }
  .up-chip {
    display: inline-block; max-width: 100%; padding: .3rem .6rem; border-radius: 6px;
    background: #16161f; border: 1px solid #262633; color: #c7d2fe;
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace; font-size: .78rem;
    overflow-wrap: anywhere;
  }
  .up-st.final .up-chip { color: #5eead4; border-color: rgba(94, 234, 212, .35); }

  @media (max-width: 900px) {
    .up-tl { grid-template-columns: 1fr; gap: 1.5rem; }
    .up-st { display: grid; grid-template-columns: 40px 1fr; column-gap: 1rem; }
    .up-st:not(:last-child)::after {
      top: 44px; bottom: calc(-1.5rem + 4px); left: 19px; right: auto; width: 2px; height: auto;
      background: linear-gradient(#818cf8, #5eead4);
    }
    .up-st h4 { margin-top: .45rem !important; }
  }

  .up-footer {
    margin-top: 3rem; padding: 1.4rem 0 .4rem 0; border-top: 1px solid #262633;
    display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 1rem;
  }
  .up-brand { display: flex; align-items: center; gap: .8rem; }
  .up-avatar {
    width: 42px; height: 42px; border-radius: 50%; display: grid; place-items: center; flex: none;
    background: linear-gradient(135deg, #818cf8, #5eead4); color: #0b0b10; font-weight: 800; font-size: 1rem;
  }
  .up-brand .by { color: #8b8ba0; font-size: .8rem; letter-spacing: .06em; text-transform: uppercase; }
  .up-brand .name { color: #ececf2; font-weight: 700; font-size: 1.05rem; line-height: 1.2; }
  .up-brand .role { color: #a1a1b5; font-size: .88rem; }
  .up-links { display: flex; flex-wrap: wrap; gap: .5rem; }
  .up-links a {
    padding: .4rem .85rem; border-radius: 999px; border: 1px solid #262633; background: #16161f;
    color: #c7d2fe !important; text-decoration: none !important; font-size: .88rem;
  }
  .up-links a:hover { border-color: #818cf8; }
</style>
"""

# st.html sanitizes inline <svg>, so the logo is embedded as an image data URI.
LOGO_DATA_URI = "data:image/svg+xml;base64," + base64.b64encode((ASSETS / "logo.svg").read_bytes()).decode("ascii")


def nav_html() -> str:
    return f"""
    <nav class="up-nav">
      <a class="up-wordmark" href="./" target="_self" aria-label="urlpaste home">
        <img src="{LOGO_DATA_URI}" alt="" width="38" height="38"><span>url<b>paste</b></span>
      </a>
      <div class="up-navlinks">
        <a href="{REPO_URL}#readme" target="_blank" rel="noopener">Docs</a>
        <a class="star" href="{REPO_URL}" target="_blank" rel="noopener">⭐ Star on GitHub</a>
      </div>
    </nav>
    """


HERO = """
<div class="up-hero">
  <span class="up-eyebrow">Nothing is saved. Anywhere.</span>
  <h1>The link <em>is</em> the note.</h1>
  <p>Write a note or upload a small file. urlpaste compresses it and packs it <strong>inside the link itself</strong>.
     No database, no storage, no account. Whoever opens the link sees the note, and nothing is kept anywhere else.</p>
</div>
"""

TIMELINE_STEPS = [
    ("You write a note", "Plain text, Markdown, or a small file.", "Meeting at 5pm, room 4"),
    ("Pack", "A tiny header records what it is, followed by the content.", "{&quot;k&quot;:&quot;text&quot;} + bytes"),
    ("Compress", "Raw deflate keeps the link short. Text shrinks 50–80%.", "22 B → 17 B"),
    ("Encrypt (optional)", "AES-256-GCM with a key from your password. The password is never in the link.", "salt · iv · ciphertext"),
    ("Encode", "URL-safe base64 turns the bytes into link-safe characters.", "?n=AWNgYOCpVs…"),
    ("Someone opens it", "Every step runs in reverse, in memory. Nothing is written anywhere.", "Meeting at 5pm, room 4"),
]


def timeline_html() -> str:
    steps = []
    for i, (title, body, chip) in enumerate(TIMELINE_STEPS, start=1):
        final = " final" if i == len(TIMELINE_STEPS) else ""
        steps.append(
            f'<div class="up-st{final}"><span class="up-dot">{i}</span>'
            f'<div><h4>{title}</h4><p>{body}</p><span class="up-chip">{chip}</span></div></div>'
        )
    return f'<div class="up-tl" role="list" aria-label="How it works">{"".join(steps)}</div>'


def base_url() -> str:
    """The URL this app is served from, so generated links point back here."""
    try:
        return st.context.url.split("?", 1)[0]
    except AttributeError:  # older Streamlit without st.context.url
        return "http://localhost:8501/"


def format_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.2f} MB"


def size_meter(link: str, input_bytes: int) -> None:
    info = describe_length(len(link))
    message = f"**{len(link):,} characters** (from {format_bytes(input_bytes)}). {info.label}"
    {"ok": st.success, "warn": st.warning, "bad": st.error}[info.level](message, icon=None)


def footer() -> None:
    st.html(
        f"""
        <footer class="up-footer">
          <div class="up-brand">
            <span class="up-avatar">LS</span>
            <div>
              <div class="by">Designed &amp; built by</div>
              <div class="name">Lokendra Singh Rathore</div>
              <div class="role">Building production agentic AI · Python · Django · Temporal</div>
            </div>
          </div>
          <nav class="up-links">
            <a href="{AUTHOR_URL}" target="_blank" rel="noopener">GitHub</a>
            <a href="{REPO_URL}" target="_blank" rel="noopener">⭐ Star urlpaste</a>
            <a href="{REPO_URL}/issues" target="_blank" rel="noopener">Report an issue</a>
          </nav>
        </footer>
        """
    )


# ---------- create ----------


def create_page() -> None:
    st.html(HERO)

    left, right = st.columns([3, 2], gap="large")

    with left:
        mode = st.segmented_control("What do you want to share?", ["Note", "File"], default="Note") or "Note"
        item = None
        input_bytes = 0

        if mode == "File":
            upload = st.file_uploader("Upload a small file (up to 1 MB, best under 20 KB)")
            if upload is not None:
                data = upload.getvalue()
                if len(data) > MAX_FILE_BYTES:
                    st.error(f"That file is {format_bytes(len(data))}. The limit is 1 MB, because the whole file has to fit inside the link.")
                else:
                    mime = upload.type or mimetypes.guess_type(upload.name)[0] or "application/octet-stream"
                    item = FileItem(data=data, name=upload.name, type=mime)
                    input_bytes = len(data)
        else:
            text = st.text_area(
                "Your note",
                height=320,
                max_chars=MAX_NOTE_CHARS,
                placeholder="Write or paste anything…  (press Ctrl/⌘ + Enter to create the link)",
            )
            markdown = st.checkbox("Render as Markdown")
            if text:
                item = TextItem(text=text, kind="markdown" if markdown else "text")
                input_bytes = len(text.encode("utf-8"))

        password = st.text_input(
            "Password (optional)",
            type="password",
            help="Encrypts the note with AES-256-GCM. Share the password separately; it is never put in the link.",
        )

    with right:
        st.subheader("Your link")
        if item is None:
            st.info("Write a note or upload a file, and your link appears here.")
        else:
            with st.spinner("Encrypting…" if password else "Encoding…"):
                link = make_link(item, password=password or None, base_url=base_url())
            st.code(link, language=None, wrap_lines=True)
            st.caption("Use the copy icon in the top-right corner of the box.")
            st.link_button("Open link in a new tab", link, type="primary", use_container_width=True)
            size_meter(link, input_bytes)
            if password:
                st.caption("🔒 Encrypted. Share the password separately.")

    st.divider()
    how_it_works()
    footer()


def how_it_works() -> None:
    st.subheader("How it works")
    st.html(timeline_html())

    st.write("")
    st.subheader("Questions")
    left, right = st.columns(2, gap="large")
    with left:
        with st.expander("Is my note stored anywhere?"):
            st.write(
                "No. There is no database and no file storage. When someone opens a link, the app decodes it "
                "in memory to show it, and keeps nothing."
            )
        with st.expander("Who can read my link?"):
            st.write(
                "Anyone who has the link, unless you set a password. Like any URL, links end up in browser "
                "history and chat logs, and hosting providers may log them. Use a password for anything sensitive."
            )
        with st.expander("Can I use it from the terminal?"):
            st.code('pip install -r requirements.txt\necho "hello" | urlpaste encode', language="bash")
    with right:
        with st.expander("How big can a note be?"):
            st.write(
                "Links under 2,000 characters work almost everywhere. Larger links work when pasted between "
                "browsers, but many chat apps cut them off. The meter under your link shows where you are."
            )
        with st.expander("Can I delete a link after sharing it?"):
            st.write("No. Whoever has the link has the content. That's the trade-off for storing nothing.")


# ---------- view ----------


def view_page(payload: str) -> None:
    password = None
    if is_encrypted(payload):
        _, center, _ = st.columns([1, 2, 1])
        with center:
            st.title("🔒 This note is password protected")
            with st.form("unlock"):
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Unlock", type="primary", use_container_width=True)
            if not submitted or not password:
                new_note_button()
                return

    try:
        item = decode(payload, password=password)
    except WrongPasswordError as exc:
        st.error(str(exc))
        new_note_button()
        return
    except PasswordRequiredError as exc:
        st.warning(str(exc))
        return
    except InvalidPayloadError as exc:
        st.error(f"{exc} Ask the sender to copy the whole link again.")
        new_note_button()
        return

    st.html('<span class="up-eyebrow">Decoded from the link · not stored anywhere</span>')

    if isinstance(item, FileItem):
        st.title(f"📄 {item.name}")
        st.caption(f"{format_bytes(len(item.data))} · {item.type}")
        if item.type.startswith("image/") and item.type != "image/svg+xml":
            st.image(item.data, caption=item.name)
        st.download_button("Download file", item.data, file_name=item.name, mime=item.type, type="primary")
    elif item.kind == "markdown":
        with st.container(border=True):
            st.markdown(item.text)  # HTML is escaped by default: safe for untrusted input
        with st.expander("Show source"):
            st.code(item.text, language="markdown", wrap_lines=True)
    else:
        st.code(item.text, language=None, wrap_lines=True)

    new_note_button()
    footer()


def new_note_button() -> None:
    if st.button("✏️  Create your own note"):
        st.query_params.clear()
        st.rerun()


st.html(STYLES)
st.html(nav_html())

payload = st.query_params.get(PARAM)
if payload:
    view_page(payload)
else:
    create_page()
