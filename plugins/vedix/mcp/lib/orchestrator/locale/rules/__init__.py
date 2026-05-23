"""Per-locale linguistic rule sets.

Each module exports ``RULES: list[Rule]``. The :mod:`.router` selects
the right module given an ISO 639-1 code. Modules are re-exported
here so static analyzers see them as proper attributes of the
``rules`` package; the actual import cost is paid only on first
attribute access via the router (Python's import system caches it).
"""
from . import de, en, es, fr, ja, ru, zh

__all__ = ["de", "en", "es", "fr", "ja", "ru", "zh"]
