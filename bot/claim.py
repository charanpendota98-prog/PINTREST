"""Pinterest website claiming — one command, Rich Pins + attribution.

Why it matters: claiming a site gives **analytics + attribution for your
content** (Pinterest's own wording) and it is the requirement for **Rich Pins**.
For an affiliate page that means more reach per pin for zero extra work.

Pinterest verifies ownership in three ways; we support the two that need no DNS
access, so a VPS deployment can do it in a minute:

1. **HTML meta tag**  → injected into the bot's own pages (landing, deals,
   panel root) whenever a token is configured.
2. **HTML file**      → served at `/pinterest-<token>.html` (public, no login).

`python -m bot claim <token>` saves the token (comment-preserving config edit)
and prints exactly what to paste into Pinterest.
"""
from __future__ import annotations

import re
from pathlib import Path

CONFIG_KEY = "domain_verify_token"
SECTION = "pinterest"
TOKEN_RE = re.compile(r"[A-Za-z0-9_\-]{8,128}")
META_RE = re.compile(
    r'<meta[^>]*name=["\']p:domain_verify["\'][^>]*content=["\']([^"\']+)["\']',
    re.I)
CONTENT_RE = re.compile(r'content=["\']([^"\']+)["\']', re.I)


def parse_token(arg: str) -> str:
    """Accept a raw token, a meta tag, or a whole HTML file — return the token."""
    raw = str(arg or "").strip()
    if not raw:
        return ""
    for pattern in (META_RE, CONTENT_RE):
        m = pattern.search(raw)
        if m:
            raw = m.group(1).strip()
            break
    return raw if TOKEN_RE.fullmatch(raw) else ""


def meta_tag(token: str) -> str:
    if not token:
        return ""
    return f'<meta name="p:domain_verify" content="{token}">'


def verify_filename(token: str) -> str:
    return f"pinterest-{token}.html" if token else ""


def verify_file_content(token: str) -> str:
    """What Pinterest's HTML-file check expects to download."""
    if not token:
        return ""
    return ("<!DOCTYPE html>\n<html>\n<head>\n"
            f'{meta_tag(token)}\n'
            "<title>Pinterest domain verification</title>\n"
            "</head>\n<body>\n"
            f"p:domain_verify {token}\n"
            "</body>\n</html>\n")


def _patch_scalar(text: str, section: str, key: str, value: str) -> str:
    """Comment-preserving scalar edit (same discipline as bot.brand)."""
    lines = text.splitlines()
    out: list[str] = []
    in_sec = False
    written = False
    for line in lines:
        stripped = line.strip()
        if not in_sec and stripped == f"{section}:":
            in_sec = True
            out.append(line)
            continue
        if in_sec:
            if line and not line.startswith((" ", "\t")):
                if not written:                     # section ended: insert now
                    out.append(f'  {key}: "{value}"')
                    written = True
                in_sec = False
                out.append(line)
                continue
            if stripped.startswith(f"{key}:"):
                comment = line.split("#", 1)[1].strip() if "#" in line else ""
                out.append(f'  {key}: "{value}"'
                           + (f"  # {comment}" if comment else ""))
                written = True
                continue
        out.append(line)
    if not written:
        if in_sec:
            out.append(f'  {key}: "{value}"')
        else:
            out.extend(["", f"{section}:", f'  {key}: "{value}"'])
    return "\n".join(out).rstrip() + "\n"


def save(cfg, arg: str, path: str | Path | None = None) -> dict:
    """Store the token so the meta tag + file route go live immediately."""
    token = parse_token(arg)
    if not token:
        return {"saved": False, "token": "", "error":
                "could not read a verification token — paste the token itself "
                "or the full <meta name=\"p:domain_verify\" ...> line"}
    cfg.raw.setdefault(SECTION, {})[CONFIG_KEY] = token
    source = getattr(cfg, "source_path", None)
    target = (Path(path) if path else Path(source) if source
              else Path(__file__).resolve().parent.parent / "config.yaml")
    try:
        target.write_text(_patch_scalar(target.read_text(), SECTION, CONFIG_KEY,
                                        token))
        import yaml
        yaml.safe_load(target.read_text())      # must still parse
        wrote = True
    except Exception:  # noqa: BLE001 — saving must never crash the CLI
        wrote = False
    return {"saved": wrote, "token": token, "file": verify_filename(token),
            "path": str(target)}


def token_of(cfg) -> str:
    """Configured verification token ('' when not set)."""
    return parse_token(str(cfg.get(f"{SECTION}.{CONFIG_KEY}", "") or ""))


def inject(html: str, token: str) -> str:
    """Insert the meta tag right after <head> — used on every public page."""
    if not token or not html:
        return html
    tag = meta_tag(token)
    if 'name="p:domain_verify"' in html:
        return html.replace(META_RE.pattern, tag) if False else html
    marker = "<head>"
    idx = html.find(marker)
    if idx == -1:
        return html
    return html[:idx + len(marker)] + "\n" + tag + html[idx + len(marker):]


def lines(cfg) -> list[str]:
    token = token_of(cfg)
    out = [
        "🔖 PINTEREST WEBSITE CLAIM — analytics + attribution (+ Rich Pins)",
        "",
        "Claim cheyyalante website undali. Mana landing page unde domain ni",
        "claim chestam (VPS IP/domain unte chalu — DNS access avasaram ledu).",
        "",
    ]
    if not token:
        out += [
            "STEP 1 (Pinterest lo): Settings → Claimed accounts → 'Claim website'",
            "   → enter your site URL (ex: https://yourdomain.com)",
            "   → method lo 'Add HTML tag' leda 'Upload HTML file' pick cheyandi",
            "   → Pinterest ichhe token copy cheyandi",
            "",
            "STEP 2 (ikkada): python -m bot claim '<token or the full meta tag>'",
            "   → bot meta tag ni pages lo inject chestundi + file ni serve chestundi",
            "",
            "STEP 3: Pinterest lo 'Verify' click cheyandi → done ✅",
        ]
        return out
    base = str(cfg.get("link.public_base", "") or "").rstrip("/")
    out += [
        f"token: {token}",
        f"meta tag  : {meta_tag(token)}",
        "already injected into: landing pages, deals page, panel root",
        f"file route: /{verify_filename(token)}"
        + (f"   (full URL: {base}/{verify_filename(token)})" if base else ""),
        "",
        "Pinterest lo: Settings → Claimed accounts → Claim website →",
        "  • 'Add HTML tag'   → mana pages lo tag already undi → Verify",
        f"  • 'Upload HTML file' → download {verify_filename(token)} from the "
        "file route → upload → Verify",
        "",
        "⚠️  Domain okkate claim avutundi: mana landing e domain meeda unte",
        "   (link.public_base) aa URL ne Pinterest lo ivvandi.",
    ]
    return out
