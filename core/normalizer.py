"""Channel name normalization functions.

Modes
-----
default     Strips trailing/bracketed quality tokens (HD, SD, 4K, FHD, UHD)
            and trims surrounding whitespace.
none        Returns the name with only whitespace trimmed — no other changes.
aggressive  Phase 4: additionally strips language/country codes and other noise.

Usage
-----
    from core import normalizer
    clean = normalizer.normalize("CNN HD")          # "CNN"
    raw   = normalizer.normalize("CNN HD", "none")  # "CNN HD"
"""

import re

# Quality tokens the default normalizer recognises
_QUALITY = r'(?:HD|SD|4K|FHD|UHD)'

_BRACKET_RE  = re.compile(r'\s*\[.*?\]', re.IGNORECASE)
_PAREN_RE    = re.compile(r'\s*\(.*?\)', re.IGNORECASE)
_TRAILING_RE = re.compile(r'(?:\s+' + _QUALITY + r')+$', re.IGNORECASE)


def _normalize_default(name: str) -> str:
    name = _BRACKET_RE.sub('', name)
    name = _PAREN_RE.sub('', name)
    name = _TRAILING_RE.sub('', name)
    return name.strip()


def normalize(name: str, mode: str = "default") -> str:
    """Return a normalized copy of name according to mode."""
    if not name:
        return name
    match mode:
        case "default":
            return _normalize_default(name)
        case "none":
            return name.strip()
        case _:
            # Unknown mode falls back to default
            return _normalize_default(name)
