"""R63: `bot token-check` — prove what the current Pinterest token can actually do.

The developer dashboard's "Generate access tokens" button advertises a limited
scope set (pins:read, boards:read, user_accounts:read, ads:read, catalogs:read),
and the app secret stays locked while trial review is pending — so OAuth cannot
finish yet. That makes one question decisive: can this token READ, and can it
WRITE? Guessing is not acceptable when the answer decides whether pins go out.

This module asks the API itself: read the account, read boards, and (only when
explicitly requested) attempt a tiny real write — create a private test board and
delete it immediately — so the owner knows before posting a single pin.
"""
from __future__ import annotations

SCOPE_NOTE = (
    "Dashboard tokens advertise: pins:read, boards:read, user_accounts:read, "
    "ads:read, catalogs:read. Note what is missing: pins:write / boards:write."
)

TEST_BOARD = "gharvanaa-connection-test"

# Dashboard ("Generate token") tokens are short-lived — community + Pinterest
# docs put them at ~24 h. We never store the token itself, only a hash + when
# it was first seen, so `token-check` and `doctor` can warn BEFORE a post fails.
TOKEN_STAMP = "pinterest_token_seen.json"
TOKEN_TTL_HOURS = 24
TOKEN_WARN_HOURS = 20


def _stamp_path(cfg) -> "pathlib.Path":
    """Sits next to the media folder — same resolution as Config.media_dir."""
    import pathlib
    try:
        media = pathlib.Path(str(cfg.media_dir))
    except Exception:                                   # noqa: BLE001
        media = pathlib.Path(str(cfg.get("storage.media_dir", "data/media")))
    return media.parent / TOKEN_STAMP


def token_fingerprint(cfg) -> str:
    """sha1 prefix of the current token — never the token itself."""
    import hashlib
    tok = str(getattr(cfg, "pinterest_access_token", "") or "").strip()
    return hashlib.sha1(tok.encode()).hexdigest()[:8] if tok else ""


def note_token_use(cfg) -> float:
    """Record/lookup when THIS token was first seen. Returns age in hours."""
    import datetime
    import json
    fp = token_fingerprint(cfg)
    if not fp:
        return 0.0
    path = _stamp_path(cfg)
    data = {}
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        data = {}
    now = datetime.datetime.now().isoformat(timespec="seconds")
    if data.get("fingerprint") != fp:
        data = {"fingerprint": fp, "first_seen": now}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data))
        except OSError:
            pass
        return 0.0
    try:
        first = datetime.datetime.fromisoformat(str(data.get("first_seen")))
        return max(0.0, (datetime.datetime.now() - first).total_seconds() / 3600.0)
    except (TypeError, ValueError):
        return 0.0


def token_age_warning(cfg) -> str:
    """'' when the token is fresh, else the exact warning line to print."""
    if not token_fingerprint(cfg):
        return ""                       # no token at all → nothing to age
    hours = note_token_use(cfg)
    if hours >= TOKEN_WARN_HOURS:
        return (f"⚠️  Dashboard token ~{hours:.0f}h puratana — ivi ~"
                f"{TOKEN_TTL_HOURS}h lo expire avutayi. Malli 'Generate token' "
                f"cheyyi (leda OAuth complete chesi permanent refresh token "
                f"pettu).")
    if hours > 0:
        return f"ℹ️  Token first seen {hours:.1f}h ago (dashboard tokens ~{TOKEN_TTL_HOURS}h)."
    return "ℹ️  Token ippude add chesav — ~24h window start ayyindi."


def expiry_hint(err_text: str) -> str:
    """Turn an opaque 401 into the one action that fixes it."""
    low = (err_text or "").lower()
    if "401" in low or "unauthor" in low or "invalid_token" in low or "expired" in low:
        return ("   ➡️ Idi EXPIRY la undi: dashboard token ~24h ke pani "
                "chestundi. App page → 'Generate Access Tokens' → Production "
                "Limited → Generate token → copy → .env lo "
                "PINTEREST_ACCESS_TOKEN='<new>' → malli token-check.")
    return ""


def _err_text(exc: Exception) -> str:
    return str(exc)[:200]


def verify(cfg, write_test: bool = False) -> list[str]:
    """Answer 'what can this token do?' with real API calls, never assumptions."""
    from .pinterest_api import PinterestAPI

    api = PinterestAPI(cfg)
    out = [
        "═" * 70,
        "🔐 PINTEREST TOKEN CHECK — ee token entha cheyyagaladu (live proof)",
        "═" * 70,
        f"   Mode      : {api.auth_mode}",
        f"   App ID    : {api.app_id or '(not set)'}",
        "   App secret: "
        + ("set ✅ (OAuth possible)" if api.app_secret
           else "LOCKED (trial review pending)"),
        "",
    ]

    if not api.configured:
        out += [
            "❌ Credentials levu. .env lo pedu:",
            "   PINTEREST_ACCESS_TOKEN='<dashboard token>'   (trial, ippude)",
            "   PINTEREST_APP_ID / PINTEREST_APP_SECRET      (OAuth, approval tarvata)",
            "   Test: python -m bot token-check",
        ]
        return out

    out += ["", token_age_warning(cfg)]
    read_ok = False
    try:
        account = api.user_account()
        read_ok = True
        out += [
            "✅ READ works — token valid, v5 API accept chesindi.",
            f"   Account: @{account.get('username', '?')} "
            f"({account.get('account_type', '?')})",
            f"   Followers: {account.get('follower_count', '?')} · "
            f"Boards: {account.get('board_count', '?')} · "
            f"Pins: {account.get('pin_count', '?')}",
        ]
    except Exception as exc:  # noqa: BLE001 — any failure IS the answer
        out += [
            "❌ READ failed — token invalid/expired leda read scope ledu.",
            f"   Detail: {_err_text(exc)}",
            "",
            "   Fix: dashboard → Generate token (Trial) → copy → .env lo",
            "        PINTEREST_ACCESS_TOKEN='...'   (tokens expire avutayi)",
        ]
        hint = expiry_hint(_err_text(exc))
        if hint:
            out.append(hint)

    if read_ok:
        try:
            boards = api.list_boards()
            names = ", ".join(b.get("name", "?") for b in boards[:5]) or "(none)"
            out.append(f"✅ boards:read works — {len(boards)} board(s): {names}")
        except Exception as exc:  # noqa: BLE001
            out.append(f"⚠️  boards:read failed: {_err_text(exc)}")

    out.append("")
    if write_test:
        out.append("🧪 WRITE TEST — private board create + delete (safe, reversible)")
        try:
            board = api.create_board(TEST_BOARD, "temporary connection test")
            board_id = str(board.get("id", ""))
            out.append(f"   ✅ boards:write WORKS — test board {board_id} create "
                       "ayyindi")
            if board_id:
                try:
                    api._request("DELETE", f"/boards/{board_id}")
                    out.append("   ✅ Test board delete ayyindi — account lo emi "
                               "migaledu")
                except Exception as exc:  # noqa: BLE001
                    out.append(f"   ⚠️ Test board delete avvaledu "
                               f"({_err_text(exc)}) — Pinterest lo '{TEST_BOARD}' "
                               "ni manual ga delete cheyyandi.")
            out += [
                "",
                "   ➡️ boards:write undi ante pins:write kuda undochu. Full pin",
                "      test:  python -m bot add <product-url>  →  python -m bot run",
            ]
        except Exception as exc:  # noqa: BLE001
            out += [
                "   ❌ WRITE BLOCKED — ee token tho boards/pins create cheyyaleru.",
                f"      Detail: {_err_text(exc)}",
                "",
                "   Ee case lo:",
                "   1) Trial review approve ayye varaku aagu (app secret unlock",
                "      ayyaka OAuth: python -m bot auth-url → auth --code)",
                "   2) Appudu pins:write + boards:write tho permanent token vasthundi",
                "      → pins start.",
                "   " + SCOPE_NOTE,
            ]
    else:
        out += [
            "ℹ️  READ verified. WRITE capability ippude test cheyyali ante:",
            "      python -m bot token-check --write-test",
            "    (private test board create chesi ventane delete chestundi —",
            "     account lo emi miguladu)",
        ]

    out += [
        "",
        "─" * 70,
        "PATH REMINDER (order):",
        "   1. Trial token → read live (ippudu chesam)",
        "   2. App approval → app secret unlock",
        "   3. python -m bot auth-url  →  python -m bot auth --code <CODE>",
        "      (permanent refresh token, write scopes tho)",
        "   4. Standard access request → public pins: python -m bot app --upgrade",
    ]
    return out


def lines(cfg, write_test: bool = False) -> list[str]:
    return verify(cfg, write_test)
