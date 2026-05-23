"""Per-locale rule registry.

Maps ISO 639-1 codes to ``list[Rule]``. Lazily imports each module so a
job that only needs ``ru`` doesn't pay the cost of the ``zh`` regex
compilation.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from ..linguistic_rules import Rule


def get_rules(code: str) -> "list[Rule]":
    """Return the rule list for ``code``. Empty list for unknown codes.

    Unknown codes return an empty list rather than raising — the
    pipeline's behavior in that case is "skip linguistic audit", which
    is the right default for the long tail of unsupported languages.
    """
    if code == "ru":
        from . import ru
        return list(ru.RULES)
    if code == "en":
        from . import en
        return list(en.RULES)
    if code == "es":
        from . import es
        return list(es.RULES)
    if code == "de":
        from . import de
        return list(de.RULES)
    if code == "fr":
        from . import fr
        return list(fr.RULES)
    if code == "zh":
        from . import zh
        return list(zh.RULES)
    if code == "ja":
        from . import ja
        return list(ja.RULES)
    return []


def has_rules_for(code: str) -> bool:
    """Whether any rules are defined for ``code``."""
    return code in {"ru", "en", "es", "de", "fr", "zh", "ja"}
