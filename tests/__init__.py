"""Test package.

Isolation: the deployed admin panel is password-locked via the
DASHBOARD_PASSWORD env var. Tests exercise the unlocked route behaviour, so
the variable is cleared here — one place, applies to every test module,
before any of them import bot.dashboard.
"""
import os

os.environ.pop("DASHBOARD_PASSWORD", None)
os.environ.pop("DASHBOARD_SECRET", None)
