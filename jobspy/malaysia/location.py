from __future__ import annotations

import re
from enum import Enum

from jobspy.model import Country, Location


class MalaysianState(str, Enum):
    """The 13 states and 3 federal territories."""

    JOHOR = "Johor"
    KEDAH = "Kedah"
    KELANTAN = "Kelantan"
    MELAKA = "Melaka"
    NEGERI_SEMBILAN = "Negeri Sembilan"
    PAHANG = "Pahang"
    PERAK = "Perak"
    PERLIS = "Perlis"
    PULAU_PINANG = "Pulau Pinang"
    SABAH = "Sabah"
    SARAWAK = "Sarawak"
    SELANGOR = "Selangor"
    TERENGGANU = "Terengganu"
    KUALA_LUMPUR = "Kuala Lumpur"
    LABUAN = "Labuan"
    PUTRAJAYA = "Putrajaya"


# alias -> (canonical city or None, state)
_GAZETTEER: dict[str, tuple[str | None, MalaysianState]] = {}


def _key(text: str) -> str:
    """Lowercases and strips punctuation so alias lookup is forgiving.

    "/", "&" and "-" are mapped to a space *before* the stricter strip below
    runs, because a board may use one of them where the canonical name has a
    space (e.g. "Petaling-Jaya" for "Petaling Jaya"). Deleting them outright,
    as a plain punctuation-strip would, fuses the two words into one token
    ("petalingjaya") that cannot match the registered "petaling jaya" key.
    Repeated whitespace is then collapsed, so a delimiter with spaces on
    both sides ("Petaling - Jaya") does not leave a double space behind.

    This does not make every slash-joined label resolve: "Klang/Port Klang"
    joins two independently-registered places rather than splitting one
    two-word name, so it becomes "klang port klang", which is itself not a
    registered key even after this fix (see
    tests/malaysia/test_location.py::test_slash_joined_dual_locality_still_does_not_resolve).
    """
    text = re.sub(r"[/&-]", " ", text.lower())
    text = re.sub(r"[^a-z0-9 ]+", "", text)
    return " ".join(text.split())


def _add(city: str | None, state: MalaysianState, *aliases: str) -> None:
    names = [city] if city else []
    names += [state.value] if city is None else []
    for name in [*names, *aliases]:
        if name:
            _GAZETTEER[_key(name)] = (city, state)


# --- Federal territories -------------------------------------------------
_add(
    "Kuala Lumpur",
    MalaysianState.KUALA_LUMPUR,
    "KL",
    "WP Kuala Lumpur",
    "W.P. Kuala Lumpur",
    "Wilayah Persekutuan Kuala Lumpur",
    "Federal Territory of Kuala Lumpur",
)
_add(
    "Putrajaya",
    MalaysianState.PUTRAJAYA,
    "WP Putrajaya",
    "Wilayah Persekutuan Putrajaya",
)
_add("Labuan", MalaysianState.LABUAN, "WP Labuan", "Wilayah Persekutuan Labuan")

# KL localities
for _locality in (
    "Bukit Bintang",
    "Bangsar",
    "Bangsar South",
    "Mont Kiara",
    "Cheras",
    "Setapak",
    "Sentul",
    "Wangsa Maju",
    "Bukit Jalil",
    "Sri Petaling",
    "Kepong",
    "Segambut",
    "KL Sentral",
    "Mid Valley",
    "Damansara Heights",
    "Taman Tun Dr Ismail",
    "TTDI",
):
    _add(_locality, MalaysianState.KUALA_LUMPUR)

# --- Selangor ------------------------------------------------------------
_add(None, MalaysianState.SELANGOR, "Selangor", "Selangor Darul Ehsan")
for _city in (
    "Petaling Jaya",
    "Shah Alam",
    "Subang Jaya",
    "Cyberjaya",
    "Puchong",
    "Klang",
    "Kajang",
    "Bangi",
    "Bandar Baru Bangi",
    "Seri Kembangan",
    "Rawang",
    "Sepang",
    "Semenyih",
    "Ampang",
    "Damansara",
    "Sunway",
    "Kota Damansara",
    "Bandar Utama",
    "Cheras Selatan",
    "Port Klang",
    "Batu Caves",
    "Selayang",
    "Gombak",
    "Hulu Langat",
    "Kuala Selangor",
):
    _add(_city, MalaysianState.SELANGOR)
_add("Petaling Jaya", MalaysianState.SELANGOR, "PJ")
_add("Subang Jaya", MalaysianState.SELANGOR, "USJ")

# --- Pulau Pinang --------------------------------------------------------
_add(None, MalaysianState.PULAU_PINANG, "Penang", "Pulau Pinang")
for _city in (
    "George Town",
    "Bayan Lepas",
    "Butterworth",
    "Bukit Mertajam",
    "Seberang Perai",
    "Gelugor",
    "Tanjung Tokong",
    "Batu Kawan",
    "Perai",
    "Taman Pulau Pinang",
    "Simpang Ampat",
):
    _add(_city, MalaysianState.PULAU_PINANG)
_add("George Town", MalaysianState.PULAU_PINANG, "Georgetown")

# --- Johor ---------------------------------------------------------------
_add(None, MalaysianState.JOHOR, "Johor", "Johor Darul Takzim")
for _city in (
    "Johor Bahru",
    "Iskandar Puteri",
    "Nusajaya",
    "Skudai",
    "Pasir Gudang",
    "Kulai",
    "Batu Pahat",
    "Muar",
    "Kluang",
    "Senai",
    "Pontian",
    "Segamat",
):
    _add(_city, MalaysianState.JOHOR)
_add("Johor Bahru", MalaysianState.JOHOR, "JB")

# --- Remaining states ----------------------------------------------------
_add(None, MalaysianState.PERAK, "Perak")
for _city in (
    "Ipoh",
    "Taiping",
    "Teluk Intan",
    "Sitiawan",
    "Lumut",
    "Kampar",
    "Batu Gajah",
):
    _add(_city, MalaysianState.PERAK)

_add(None, MalaysianState.KEDAH, "Kedah")
for _city in ("Alor Setar", "Sungai Petani", "Kulim", "Langkawi", "Jitra"):
    _add(_city, MalaysianState.KEDAH)

_add(None, MalaysianState.PERLIS, "Perlis")
_add("Kangar", MalaysianState.PERLIS)

_add(None, MalaysianState.KELANTAN, "Kelantan")
for _city in ("Kota Bharu", "Pasir Mas", "Tanah Merah"):
    _add(_city, MalaysianState.KELANTAN)

_add(None, MalaysianState.TERENGGANU, "Terengganu")
for _city in ("Kuala Terengganu", "Kemaman", "Dungun", "Kerteh"):
    _add(_city, MalaysianState.TERENGGANU)

_add(None, MalaysianState.PAHANG, "Pahang")
for _city in (
    "Kuantan",
    "Temerloh",
    "Bentong",
    "Genting Highlands",
    "Cameron Highlands",
    "Gambang",
):
    _add(_city, MalaysianState.PAHANG)

_add(None, MalaysianState.MELAKA, "Melaka", "Malacca")
for _city in ("Melaka City", "Ayer Keroh", "Alor Gajah", "Jasin"):
    _add(_city, MalaysianState.MELAKA)

_add(None, MalaysianState.NEGERI_SEMBILAN, "Negeri Sembilan", "Negri Sembilan")
for _city in ("Seremban", "Nilai", "Port Dickson", "Bahau", "Senawang"):
    _add(_city, MalaysianState.NEGERI_SEMBILAN)

_add(None, MalaysianState.SABAH, "Sabah")
for _city in ("Kota Kinabalu", "Sandakan", "Tawau", "Lahad Datu", "Keningau", "Papar"):
    _add(_city, MalaysianState.SABAH)

_add(None, MalaysianState.SARAWAK, "Sarawak")
for _city in ("Kuching", "Miri", "Sibu", "Bintulu", "Samarahan", "Sri Aman"):
    _add(_city, MalaysianState.SARAWAK)

# --- ISO 3166-2:MY state codes --------------------------------------------
# Indeed Malaysia emits state codes rather than names (Location.state ==
# "M14", not "Kuala Lumpur"). Matched case-insensitively via _key().
#
# Provenance: only FOUR of these were empirically confirmed against a live
# 400-row baseline scrape, by checking which cities co-occurred with each
# code: M01 with Johor Bahru; M07 with Bayan Lepas, Butterworth, George
# Town, Bukit Mertajam and Perai; M10 with Petaling Jaya, Cyberjaya, Shah
# Alam and Seri Kembangan; M14 with Kuala Lumpur. The remaining twelve are
# taken from the ISO 3166-2:MY standard and have NOT been verified against
# Indeed's actual output.
_ISO_STATE_CODES: dict[str, MalaysianState] = {
    "M01": MalaysianState.JOHOR,
    "M02": MalaysianState.KEDAH,
    "M03": MalaysianState.KELANTAN,
    "M04": MalaysianState.MELAKA,
    "M05": MalaysianState.NEGERI_SEMBILAN,
    "M06": MalaysianState.PAHANG,
    "M07": MalaysianState.PULAU_PINANG,
    "M08": MalaysianState.PERAK,
    "M09": MalaysianState.PERLIS,
    "M10": MalaysianState.SELANGOR,
    "M11": MalaysianState.TERENGGANU,
    "M12": MalaysianState.SABAH,
    "M13": MalaysianState.SARAWAK,
    "M14": MalaysianState.KUALA_LUMPUR,
    "M15": MalaysianState.LABUAN,
    "M16": MalaysianState.PUTRAJAYA,
}
for _code, _iso_state in _ISO_STATE_CODES.items():
    _add(None, _iso_state, _code)


def _lookup(text: str | None) -> tuple[str | None, MalaysianState] | None:
    if not text:
        return None
    return _GAZETTEER.get(_key(text))


def resolve_state(text: str | None) -> MalaysianState | None:
    """Resolves one free-text location, as a caller types it, to a state.

    For building a board's query filter, not for normalizing scraped output
    (normalize_location does that). Tries the whole string, then each
    comma-separated part left to right, so "Petaling Jaya, Selangor" and the
    fork's own "Kuala Lumpur, Malaysia" convention both resolve. Returns None
    for anything that is not a Malaysian place - including "Malaysia" itself,
    which is a nationwide search, not a state.
    """
    if not text:
        return None
    candidates = [text] + [part.strip() for part in text.split(",")]
    for candidate in candidates:
        hit = _lookup(candidate)
        if hit:
            return hit[1]
    return None


def normalize_location(
    location: Location | None,
) -> tuple[Location | None, str | None]:
    """Resolves a scraped Location to a canonical Malaysian city and state.

    Returns (normalized_location, unmatched_text). unmatched_text is non-None
    only when nothing could be resolved; the caller logs it so the gazetteer
    can grow from measured misses rather than guesses.

    `state` is set only on a genuine gazetteer or ISO-code match — an
    unrecognized raw state string (e.g. the country name "Malaysia", or a
    typo) is never written into the state field as if it were canonical. On
    a miss, `state` is cleared to None rather than left as the raw text (see
    comment on the miss path below); `city` is left untouched either way.
    """
    if location is None:
        return None, None

    city_hit = _lookup(location.city)
    state_hit = _lookup(location.state)

    if city_hit:
        canonical_city, state = city_hit
        return (
            Location(
                city=canonical_city or location.city,
                state=state.value,
                country=Country.MALAYSIA,
            ),
            None,
        )

    if state_hit:
        _, state = state_hit
        return (
            Location(city=location.city, state=state.value, country=Country.MALAYSIA),
            None,
        )

    unmatched = ", ".join(part for part in (location.city, location.state) if part)
    # Canonical-or-nothing: a raw, unresolved state string (e.g. the country
    # name "Malaysia") must never sit in the `state` field, because Task 10's
    # duplicate grouping compares jobs by equal state and would otherwise
    # group unrelated postings under shared junk values. The raw text isn't
    # lost — it's still in `unmatched` for the gazetteer backlog. `city` is
    # left as-is since it isn't consumed as a canonical value.
    return (
        Location(city=location.city, state=None, country=location.country),
        unmatched or None,
    )
