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

# Quality and codec tokens the default normaliser recognises
_QUALITY = (
    r'(?:'
    r'HDR10\+?'               # HDR10, HDR10+  (must precede HDR/HD)
    r'|HDR'                   # HDR
    r'|Ultra\s+HD'            # "Ultra HD" as a phrase
    r'|HD|SD|SDR|4K|FHD|UHD'  # standard quality tiers
    r'|HEVC|H\.265|H\.264|H265|H264|AVC|MPEG2?'  # codecs
    r'|RAW'                   # RAW feed
    r'|\d+[Ff][Pp][Ss]'       # frame rates: 50fps, 60FPS, etc.
    r')'
)

_BRACKET_RE  = re.compile(r'\s*\[.*?\]', re.IGNORECASE)
_PAREN_RE    = re.compile(r'\s*\(.*?\)', re.IGNORECASE)
# Allow space, slash, or dash as separator before quality tokens so that
# "UHD/4K" and "HD-SDR" are fully stripped rather than partially.
_TRAILING_RE = re.compile(r'(?:[\s/\-]+' + _QUALITY + r'[\s\W]*)+$', re.IGNORECASE)

# Unicode superscript quality markers sometimes embedded in M3U channel names
# ᴴᴰ = superscript HD,  ᴿᴬᵂ = superscript RAW
_UNICODE_QUALITY_RE = re.compile(r'\s*(?:ᴴᴰ|ᴿᴬᵂ)\s*')
_MULTI_SPACE_RE     = re.compile(r' {2,}')

# Scheduling / availability noise phrases embedded in channel names
_NOISE_RE = re.compile(
    r'\b(?:'
    r'matchday\s+only'
    r'|match\s+day\s+only'
    r'|matchday'
    r'|match\s+day'
    r'|ppv\s+only'
    r'|ppv'
    r'|live\s+only'
    r')\b[\s\W]*',
    re.IGNORECASE,
)

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
    r'|[A-Za-z]{2,8}\s*[-–]\s*'   # MY - UK – UK- etc.
    r'|\|\s*'                       # bare | prefix: "| Alaves"
    r')+'
)


def _normalize_default(name: str) -> str:
    name = _MULTI_SPACE_RE.sub(' ', _UNICODE_QUALITY_RE.sub(' ', name))
    name = _BRACKET_RE.sub('', name)
    name = _PAREN_RE.sub('', name)
    name = _NOISE_RE.sub('', name)
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
