"""Brand name dictionary for display-quality channel name casing.

Edit BRANDS below to add or correct entries. Keys are lowercase; values are
the display form you want. Entries are matched word-by-word, so "bbc" fixes
"Bbc" → "BBC" anywhere in a channel name.

To add your own:
    "paramount": "Paramount+",
    "trace":     "Trace",
"""

# lowercase word → correct display form
BRANDS: dict[str, str] = {

    # ── BBC ───────────────────────────────────────────────────────────
    "bbc":          "BBC",
    "cbbc":         "CBBC",
    "cbeebies":     "CBeebies",

    # ── ITV ───────────────────────────────────────────────────────────
    "itv":          "ITV",
    "itv2":         "ITV2",
    "itv3":         "ITV3",
    "itv4":         "ITV4",
    "itvbe":        "ITVBe",

    # ── Channel 4 family ──────────────────────────────────────────────
    "e4":           "E4",
    "more4":        "More4",
    "film4":        "Film4",
    "4music":       "4Music",

    # ── Channel 5 family ──────────────────────────────────────────────
    "5star":        "5Star",
    "5usa":         "5USA",
    "5select":      "5Select",

    # ── Sky ───────────────────────────────────────────────────────────
    "sky":          "Sky",
    "skyone":       "Sky One",
    "skymax":       "Sky Max",
    "skyatlantic":  "Sky Atlantic",
    "skyarts":      "Sky Arts",
    "skycomedy":    "Sky Comedy",
    "skycrime":     "Sky Crime",
    "skydocs":      "Sky Docs",
    "skynature":    "Sky Nature",
    "skyhistory":   "Sky History",
    "skynews":      "Sky News",
    "skysports":    "Sky Sports",

    # ── BT Sport ──────────────────────────────────────────────────────
    "bt":           "BT",
    "btsport":      "BT Sport",

    # ── UKTV channels ─────────────────────────────────────────────────
    "dave":         "Dave",
    "gold":         "Gold",
    "alibi":        "Alibi",
    "eden":         "Eden",
    "yesterday":    "Yesterday",
    "blaze":        "Blaze",

    # ── UK news / talk ────────────────────────────────────────────────
    "gb":           "GB",           # GB News
    "lbc":          "LBC",
    "talktv":       "TalkTV",
    "tv":           "TV",

    # ── UK / International sports ─────────────────────────────────────
    "espn":         "ESPN",
    "eurosport":    "Eurosport",
    "bein":         "beIN",
    "nba":          "NBA",
    "nfl":          "NFL",
    "nhl":          "NHL",
    "mlb":          "MLB",
    "ufc":          "UFC",
    "wwe":          "WWE",
    "fc":           "FC",
    "sbs":          "SBS",
    "npo":          "NPO",
    "euro":         "EURO",
    "rcd":          "RCD",

    # ── DSTV / MultiChoice ────────────────────────────────────────────
    "dstv":         "DStv",
    "supersport":   "SuperSport",
    "mnet":         "M-Net",
    "kyknet":       "kykNET",
    "1magic":       "1Magic",
    "mzansi":       "Mzansi",
    "enca":         "eNCA",
    "etv":          "eTV",
    "sabc":         "SABC",
    "newzroom":     "Newzroom",     # Newzroom Afrika
    "africa":       "Africa",
    "novela":       "Novela",       # Novela Magic
    "channel":      "Channel",
    "trace":        "Trace",        # Trace Urban / Trace Mziki
    "ze":           "Zee",          # Zee World (sometimes split)
    "zee":          "Zee",

    # ── News (international) ──────────────────────────────────────────
    "cnn":          "CNN",
    "cnbc":         "CNBC",
    "msnbc":        "MSNBC",
    "al":           "Al",           # Al Jazeera
    "jazeera":      "Jazeera",
    "dw":           "DW",
    "france":       "France",       # France 24
    "rt":           "RT",

    # ── Kids ──────────────────────────────────────────────────────────
    "nickelodeon":  "Nickelodeon",
    "nick":         "Nick",
    "nickjr":       "Nick Jr",
    "disney":       "Disney",
    "boomerang":    "Boomerang",
    "cartoon":      "Cartoon",      # Cartoon Network

    # ── Entertainment / US cable ──────────────────────────────────────
    "hbo":          "HBO",
    "hbomax":       "HBOMax",
    "amc":          "AMC",
    "nbc":          "NBC",
    "abc":          "ABC",
    "cbs":          "CBS",
    "fox":          "Fox",
    "mtv":          "MTV",
    "tnt":          "TNT",
    "tbs":          "TBS",
    "fx":           "FX",
    "fxx":          "FXX",
    "syfy":         "Syfy",
    "tlc":          "TLC",
    "hgtv":         "HGTV",
    "e!":           "E!",
    "bravo":        "Bravo",
    "lifetime":     "Lifetime",
    "comedy":       "Comedy",       # Comedy Central
    "nat":          "Nat",          # Nat Geo
    "geo":          "Geo",
    "natgeo":       "Nat Geo",
    "discovery":    "Discovery",
    "animal":       "Animal",       # Animal Planet
    "history":      "History",
    "crime":        "Crime",        # Crime + Investigation
    "investigation": "Investigation",
    "paramount":    "Paramount",

    # ── Quality suffixes (keep consistent casing after strip) ─────────
    "hd":           "HD",
    "fhd":          "FHD",
    "uhd":          "UHD",
    "4k":           "4K",
    "sd":           "SD",

    # ── Country/region codes (in case they survive normalisation) ─────
    "uk":           "UK",
    "us":           "US",
    "sa":           "SA",
}


def apply_brands(name: str) -> str:
    """Title-case a name, then fix known brand words using BRANDS.

    "dstv | ss la liga" → "DStv | Ss La Liga"
    "bbc one"           → "BBC One"
    "supersport 1"      → "SuperSport 1"
    """
    words = name.title().split()
    return " ".join(BRANDS.get(w.lower(), w) for w in words)
