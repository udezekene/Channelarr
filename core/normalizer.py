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

# Aggressive: leading country/region/language prefix patterns to strip before
# applying the default rules.  Handles the most common M3U naming conventions:
#   [US]  [MY]  [Malaysia]   → bracket codes
#   MY |  UK|   US |         → code + pipe separator
#   US:   MY:                → code + colon
#   UK -  MY –               → code + dash/em-dash
_AGGRESSIVE_PREFIX_RE = re.compile(
    r'^(?:'
    r'\[[^\]]*\]\s*'               # [XX] or [Country Name] at start
    r'|[A-Za-z]{2,8}\s*[|:]\s*'   # MY| MY : US: etc.
    r'|[A-Za-z]{2,8}\s+[-–]\s*'   # MY - UK – etc.
    r')+'
)


def _normalize_default(name: str) -> str:
    name = _BRACKET_RE.sub('', name)
    name = _PAREN_RE.sub('', name)
    name = _TRAILING_RE.sub('', name)
    return name.strip()


def _normalize_aggressive(name: str) -> str:
    # Strip leading country/region prefixes first, then apply default rules
    name = _AGGRESSIVE_PREFIX_RE.sub('', name)
    return _normalize_default(name)


def normalize(name: str, mode: str = "default") -> str:
    """Return a normalized copy of name according to mode."""
    if not name:
        return name
    match mode:
        case "default":
            return _normalize_default(name)
        case "aggressive":
            return _normalize_aggressive(name)
        case "none":
            return name.strip()
        case _:
            # Unknown mode falls back to default
            return _normalize_default(name)
