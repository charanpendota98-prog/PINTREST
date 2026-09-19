"""R65: credentials intake — validate, classify and save .env from the CLI.

The owner pastes credentials in chat (an Amazon tag, an EarnKaro link). Two of
those were fine and one was the WRONG KIND of link, which is exactly the failure
this module exists to prevent: an EarnKaro *referral* link (earnkaro.com?r=…)
earns nothing on product clicks, while the bot needs a *deeplink prefix*
(ekaro.in/enkr…) that it can append `?url=<product>` to.

So every credential is checked for shape before it is written, and the answer
says what it is, whether it pays, and what to paste instead if it does not.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from .earnkaro import validate_token as _validate_ekaro_token

ENV_ORDER = (
    "PINTEREST_APP_ID", "PINTEREST_APP_SECRET", "PINTEREST_ACCESS_TOKEN",
    "PINTEREST_REFRESH_TOKEN", "AMAZON_TAG", "MEESHO_TEMPLATE_LINK",
    "MEESHO_AFFID", "FLIPKART_AFFID", "EARNKARO_PREFIX", "EARNKARO_API_TOKEN",
    "CUELINKS_TEMPLATE",
    "INSTAGRAM_TOKEN", "IG_USER_ID", "FB_PAGE_TOKEN", "FB_PAGE_ID",
)

AMAZON_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]*-\d{2}$")


def validate_amazon_tag(tag: str) -> dict:
    """Amazon Associates tracking id — India tags end with '-21'."""
    tag = str(tag or "").strip().strip("'\"")
    if not tag:
        return {"ok": False, "error": "Tag khali undi."}
    if not AMAZON_RE.match(tag):
        hint = "India Associates tag '<name>-21' la untundi (ex: mama086-21)."
        return {"ok": False, "error": f"'{tag}' tag format kaadu. {hint}"}
    if not tag.endswith("-21"):
        return {"ok": True, "warn": f"'{tag}' India Associates tag kaadu la undi "
                                    "(India tags '-21' tho end avutayi) — vere "
                                    "region/account aithe parvaledu.",
                "tag": tag}
    return {"ok": True, "tag": tag}


def classify_earnkaro(value: str) -> dict:
    """What did the owner actually paste? A referral link pays nothing per click."""
    v = str(value or "").strip().strip("'\"")
    if not v:
        return {"kind": "empty", "ok": False}
    if not v.startswith("http"):
        v = "https://" + v
    from urllib.parse import parse_qs, urlparse
    parsed = urlparse(v)
    host = (parsed.netloc or "").lower()
    query = parse_qs(parsed.query)

    if host.endswith("earnkaro.com") and "r" in query:
        return {
            "kind": "referral", "ok": False, "ref": query["r"][0],
            "reason": ("Idi **referral link** (earnkaro.com?r=…) — vere vaallu "
                       "EarnKaro join ayye link. Product clicks ki commission "
                       "raadu, so bot deeniki link convert cheyyaleru."),
            "fix": ("EarnKaro dashboard lo **'Create affiliate link'** / "
                    "'Deal link' generate cheyyandi → `https://ekaro.in/enkr…` "
                    "la vasthundi. Adi deeplink **prefix**; bot daaniki "
                    "`?url=<product>` append chestundi."),
        }
    if "url=" in v:
        return {"kind": "product_link", "ok": False,
                "reason": "Idi already-converted single product link.",
                "fix": "Prefix kavali (ekaro.in/enkr…), single product link kaadu."}
    if "ekaro.in" in host or (host.endswith("earnkaro.com") and parsed.path not in ("", "/")):
        return {"kind": "prefix", "ok": True, "prefix": v.rstrip("/"),
                "note": "Deeplink prefix ✅ — bot ?url=<product> append chestundi."}
    return {"kind": "unknown", "ok": False,
            "reason": f"'{host or v}' EarnKaro link la kanipistaledu.",
            "fix": "EarnKaro dashboard → 'Create affiliate link' → ekaro.in "
                   "prefix copy cheyyandi."}


def validate_earnkaro_token(value: str) -> dict:
    """EarnKaro API JWT (payload {_id, earnkaro, iat}) — shape checked offline.

    This is the token the EarnKaro site/app sends to
    webapi.earnkaro.com/api/affiliate/link-converter. With it the bot converts
    ANY product URL into the owner's own profit link, so commission lands in
    HIS EarnKaro account (never a reseller/middleman).
    """
    return _validate_ekaro_token(value)


def validate_meesho(value: str) -> dict:
    """Meesho must be the owner's own af_invite (direct commission)."""
    v = str(value or "").strip().strip("'\"")
    if not v:
        return {"ok": False, "error": "Khali undi."}
    if "af_invite" in v or "affid=" in v or "meesho.com" in v:
        if "earnkaro" in v or "ekaro" in v:
            return {"ok": False,
                    "error": "Idi EarnKaro wrapped link — Meesho commission "
                             "middleman daggaraki veltundi (R26: direct kavali).",
                    "fix": "affiliate.meesho.com → 'Get commission link' → "
                           "af_invite link paste cheyyandi."}
        return {"ok": True, "link": v}
    return {"ok": False, "error": "Meesho af_invite link la kanipistaledu.",
            "fix": "affiliate.meesho.com → 'Get commission link' (af_invite)."}


VALIDATORS = {
    "AMAZON_TAG": validate_amazon_tag,
    "EARNKARO_PREFIX": classify_earnkaro,
    "EARNKARO_API_TOKEN": validate_earnkaro_token,
    "MEESHO_TEMPLATE_LINK": validate_meesho,
    "MEESHO_AFFID": lambda v: ({"ok": bool(str(v).strip()), "tag": str(v).strip()}
                               if str(v).strip() else {"ok": False, "error": "khali"}),
    "FLIPKART_AFFID": lambda v: ({"ok": bool(str(v).strip())}
                                 if str(v).strip() else {"ok": False, "error": "khali"}),
    "CUELINKS_TEMPLATE": lambda v: ({"ok": "{url}" in str(v),
                                     "error": "{url} placeholder ledu"}
                                    if str(v).strip() else {"ok": False, "error": "khali"}),
}
# keys the validators do not police (tokens/passwords) are accepted as-is
PASSTHROUGH = ("PINTEREST_ACCESS_TOKEN", "PINTEREST_REFRESH_TOKEN",
               "PINTEREST_APP_ID", "PINTEREST_APP_SECRET", "INSTAGRAM_TOKEN",
               "IG_USER_ID", "FB_PAGE_TOKEN", "FB_PAGE_ID")


SECRETISH = ("TOKEN", "SECRET", "PASSWORD", "API_KEY")


def mask(key: str, value: str) -> str:
    """Never echo a raw secret back to a terminal, log or screenshot."""
    v = str(value or "")
    k = str(key or "").upper()
    if any(tag in k for tag in SECRETISH) and len(v) > 12:
        return f"{v[:10]}\u2026({len(v)} chars)"
    return v


def env_path() -> Path:
    return Path(__file__).resolve().parent.parent / ".env"


def save_env(mapping: dict, path: str | Path | None = None) -> dict:
    """Comment-preserving .env update (creates the file from .env.example)."""
    target = Path(path) if path else env_path()
    if not target.exists():
        example = target.parent / ".env.example"
        target.write_text(example.read_text() if example.exists() else
                          "# secrets — never commit this file\n")
    lines = target.read_text().splitlines()
    written: list[str] = []
    for key, value in mapping.items():
        if value is None:
            continue
        value = str(value)
        found = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(f"{key}=") or stripped.startswith(f"{key} ="):
                comment = ""
                if "#" in line and not stripped.startswith("#"):
                    comment = line.split("#", 1)[1].strip()
                lines[i] = f"{key}={value}" + (f"  # {comment}" if comment else "")
                found = True
                break
        if not found:
            lines.append(f"{key}={value}")
        written.append(key)
    target.write_text("\n".join(lines).rstrip() + "\n")
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    return {"saved": bool(written), "keys": written, "path": str(target)}


def apply_credentials(pairs: list[tuple[str, str]], path: str | Path | None = None) -> dict:
    """Validate each pair, save only what is correct, explain the rest."""
    accepted: dict[str, str] = {}
    results: list[dict] = []
    for key, raw in pairs:
        value = str(raw or "").strip().strip("'\"")
        if not value:
            continue
        validator = VALIDATORS.get(key)
        if validator is None and key not in PASSTHROUGH:
            results.append({"key": key, "ok": False,
                            "error": f"'{key}' teliyani key."})
            continue
        check = validator(value) if validator else {"ok": True}
        if check.get("ok"):
            stored = (check.get("value") or check.get("tag") or
                      check.get("prefix") or check.get("link") or value)
            accepted[key] = str(stored)
            results.append({"key": key, "ok": True, "value": str(stored),
                            "note": check.get("note") or check.get("warn", "")})
        else:
            results.append({"key": key, "ok": False,
                            "error": check.get("error") or check.get("reason", ""),
                            "fix": check.get("fix", ""),
                            "kind": check.get("kind", "")})
    saved = save_env(accepted, path) if accepted else {"saved": False, "keys": []}
    return {"results": results, "saved": saved, "accepted": accepted}


def status_lines(cfg=None) -> list[str]:
    """Which money credentials are live, and what each one means."""
    def _env(key: str) -> str:
        return str(os.getenv(key, "") or "").strip()

    def _val(*keys: str) -> str:
        for k in keys:
            v = _env(k)
            if v:
                return v
        if cfg is not None:
            for k in keys:
                try:
                    v = str(cfg.get(k, "") or "").strip()
                except Exception:  # noqa: BLE001
                    v = ""
                if v:
                    return v
        return ""

    amazon = _val("AMAZON_TAG", "affiliate.amazon_tag")
    meesho = _val("MEESHO_TEMPLATE_LINK", "affiliate.meesho_template_link")
    meesho_aff = _val("MEESHO_AFFID", "affiliate.meesho_affid")
    ekaro = _val("EARNKARO_PREFIX", "affiliate.earnkaro_prefix")
    ekaro_tok = _env("EARNKARO_API_TOKEN") or _env("EARNKARO_TOKEN")
    ekaro_who = ""
    if ekaro_tok:
        try:
            from .earnkaro import decode_token as _dec
            info = _dec(ekaro_tok)
            ekaro_who = (f"id {info.get('earnkaro')} · {info.get('age_days')}d "
                         f"old" if info.get("ok") else "shape doubtful")
        except Exception:  # noqa: BLE001
            ekaro_who = "set"
    pin_id = _val("PINTEREST_APP_ID")
    pin_tok = _env("PINTEREST_ACCESS_TOKEN") or _env("PINTEREST_REFRESH_TOKEN")

    def mark(ok: bool) -> str:
        return "✅" if ok else "❌"

    out = [
        "═" * 70,
        "🔑 CREDENTIALS STATUS (money links kuda ikkada)",
        "═" * 70,
        f"   {mark(bool(pin_id))} Pinterest app id     : {pin_id or '(not set)'}",
        f"   {mark(bool(pin_tok))} Pinterest token      : "
        f"{'set' if pin_tok else '(trial token / OAuth pending)'}",
        f"   {mark(bool(amazon))} Amazon Associates tag: {amazon or '(not set)'}",
        f"   {mark(bool(meesho))} Meesho af_invite     : "
        f"{'set (DIRECT commission ✅)' if meesho else '(not set)'}"
        + (f"  [affid: {meesho_aff}]" if meesho_aff else ""),
        f"   {mark(bool(ekaro_tok))} EarnKaro API token  : "
        f"{ekaro_who or '(not set)'}"
        + ("   ← every store auto-converts ✅" if ekaro_tok else ""),
        f"   {mark(bool(ekaro))} EarnKaro deeplink    : "
        f"{ekaro or '(legacy prefix, not needed with the API)'}",
        "",
    ]
    if not meesho:
        out += [
            "   ⚠️ Meesho af_invite ledu → Meesho products ki EarnKaro wrap",
            "      avutundi, appudu commission **middleman** daggaraki veltundi.",
            "      Direct kavali: affiliate.meesho.com → 'Get commission link'.",
            "",
        ]
    if amazon:
        out.append(f"   • Amazon pins: tag '{amazon}' tho direct Associates "
                   "commission (EarnKaro avasaram ledu).")
    if ekaro_tok:
        out.append("   • Flipkart/Myntra/Ajio/Nykaa… prati product URL ni EarnKaro "
                   "API nee OWN profit link ki convert chestundi (direct).")
        out.append("     Live proof: python -m bot earnkaro probe")
    elif ekaro:
        out.append("   • Vere stores: legacy deeplink prefix tho wrap "
                   "(best: `python -m bot earnkaro capture` → API token).")
    else:
        out.append("   • Flipkart/Myntra/Ajio ki tracking ledu → ee round lo "
                   "`python -m bot earnkaro capture` cheyyandi.")
    out += [
        "",
        "   Save cheyyadam:  python -m bot creds --amazon <tag> "
        "--earnkaro-token <jwt>",
        "   Validate cheyyadam: python -m bot creds   (ee status eh)",
    ]
    return out
