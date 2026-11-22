"""Reference data and name standardisation for Irish counties, local authorities and regions.

Mappings
--------
* Province: traditional province of each county.
* NUTS3 region: the CSO regional grouping used in planning statistics.  The county
  membership below matches the CSO table CIRGDP07 (Border, West, Mid-East, Midlands,
  Mid-West, South-East, South-West, Dublin).
* Homeless region: the nine regions used in the Department of Housing monthly
  homelessness reports (HomeScope's mapping of counties to those regions, see README).
* Local authorities: the 31 local authorities, each mapped to one of the 26 counties
  (Dublin = 4 local authorities, Cork = 2, Galway = 2).
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, Optional

import pandas as pd

# county, province, NUTS3 region, Dept. homeless region
COUNTIES = [
    ("Carlow", "Leinster", "South-East", "South-East"),
    ("Cavan", "Ulster", "Border", "North-East"),
    ("Clare", "Munster", "Mid-West", "Mid-West"),
    ("Cork", "Munster", "South-West", "South-West"),
    ("Donegal", "Ulster", "Border", "North-West"),
    ("Dublin", "Leinster", "Dublin", "Dublin"),
    ("Galway", "Connacht", "West", "West"),
    ("Kerry", "Munster", "South-West", "South-West"),
    ("Kildare", "Leinster", "Mid-East", "Mid-East"),
    ("Kilkenny", "Leinster", "South-East", "South-East"),
    ("Laois", "Leinster", "Midlands", "Midlands"),
    ("Leitrim", "Connacht", "Border", "North-West"),
    ("Limerick", "Munster", "Mid-West", "Mid-West"),
    ("Longford", "Leinster", "Midlands", "Midlands"),
    ("Louth", "Leinster", "Mid-East", "North-East"),
    ("Mayo", "Connacht", "West", "West"),
    ("Meath", "Leinster", "Mid-East", "Mid-East"),
    ("Monaghan", "Ulster", "Border", "North-East"),
    ("Offaly", "Leinster", "Midlands", "Midlands"),
    ("Roscommon", "Connacht", "West", "West"),
    ("Sligo", "Connacht", "Border", "North-West"),
    ("Tipperary", "Munster", "Mid-West", "Mid-West"),
    ("Waterford", "Munster", "South-East", "South-East"),
    ("Westmeath", "Leinster", "Midlands", "Midlands"),
    ("Wexford", "Leinster", "South-East", "South-East"),
    ("Wicklow", "Leinster", "Mid-East", "Mid-East"),
]
COUNTY_NAMES = [c[0] for c in COUNTIES]

NUTS3_REGIONS = ["Border", "West", "Mid-West", "South-East", "South-West", "Dublin", "Mid-East", "Midlands"]
HOMELESS_REGIONS = ["Dublin", "Mid-East", "Midlands", "Mid-West", "North-East", "North-West", "South-East", "South-West", "West"]

# canonical local authority name, county, type
LOCAL_AUTHORITIES = [
    ("Carlow County Council", "Carlow", "County"),
    ("Cavan County Council", "Cavan", "County"),
    ("Clare County Council", "Clare", "County"),
    ("Cork City Council", "Cork", "City"),
    ("Cork County Council", "Cork", "County"),
    ("Donegal County Council", "Donegal", "County"),
    ("Dublin City Council", "Dublin", "City"),
    ("Dún Laoghaire-Rathdown County Council", "Dublin", "County"),
    ("Fingal County Council", "Dublin", "County"),
    ("Galway City Council", "Galway", "City"),
    ("Galway County Council", "Galway", "County"),
    ("Kerry County Council", "Kerry", "County"),
    ("Kildare County Council", "Kildare", "County"),
    ("Kilkenny County Council", "Kilkenny", "County"),
    ("Laois County Council", "Laois", "County"),
    ("Leitrim County Council", "Leitrim", "County"),
    ("Limerick City and County Council", "Limerick", "City and County"),
    ("Longford County Council", "Longford", "County"),
    ("Louth County Council", "Louth", "County"),
    ("Mayo County Council", "Mayo", "County"),
    ("Meath County Council", "Meath", "County"),
    ("Monaghan County Council", "Monaghan", "County"),
    ("Offaly County Council", "Offaly", "County"),
    ("Roscommon County Council", "Roscommon", "County"),
    ("Sligo County Council", "Sligo", "County"),
    ("South Dublin County Council", "Dublin", "County"),
    ("Tipperary County Council", "Tipperary", "County"),
    ("Waterford City and County Council", "Waterford", "City and County"),
    ("Westmeath County Council", "Westmeath", "County"),
    ("Wexford County Council", "Wexford", "County"),
    ("Wicklow County Council", "Wicklow", "County"),
]

NATIONAL_LABELS = {"ireland", "state", "all counties", "national"}


def _fold(text: str) -> str:
    """Lower-case, strip accents/punctuation so 'Dún Laoghaire-Rathdown' == 'Dun Laoghaire Rathdown'."""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _la_key(text: str) -> str:
    key = _fold(text)
    key = re.sub(r"\b(county|council|and|co)\b", " ", key)
    return re.sub(r"\s+", " ", key).strip()


# 'Cork City and Cork County' (Census 2022 combined area) -> not a single LA; handled separately.
_LA_BY_KEY: Dict[str, str] = {_la_key(n): n for n, _, _ in LOCAL_AUTHORITIES}
# Census tables label the Dublin City / Galway County rows without the word "County"/"Council"
_LA_BY_KEY.update({"dublin city": "Dublin City Council", "cork city cork": "Cork City and Cork County"})
_COUNTY_BY_LA: Dict[str, str] = {n: c for n, c, _ in LOCAL_AUTHORITIES}
_COUNTY_BY_LA["Cork City and Cork County"] = "Cork"
_COUNTY_BY_KEY = {_fold(c): c for c in COUNTY_NAMES}
CITY_KEYS = {"cork city", "galway city", "limerick city", "waterford city", "kilkenny city"}


def is_national(name: str) -> bool:
    return _fold(name) in NATIONAL_LABELS


def standardise_la(name: str) -> Optional[str]:
    """Return the canonical local-authority name (or None when unknown / national)."""
    if name is None or is_national(name):
        return None
    return _LA_BY_KEY.get(_la_key(name))


def standardise_county(name: str) -> Optional[str]:
    """Map 'Co. Clare', 'Clare', 'Clare County Council', 'Dublin City' ... to the 26 county names."""
    if name is None or is_national(name):
        return None
    folded = _fold(name)
    folded_nocounty = re.sub(r"^co ", "", folded)
    if folded_nocounty in _COUNTY_BY_KEY:
        return _COUNTY_BY_KEY[folded_nocounty]
    la = _LA_BY_KEY.get(_la_key(name))
    if la:
        return _COUNTY_BY_LA[la]
    return None


def county_reference_frame() -> pd.DataFrame:
    return pd.DataFrame(COUNTIES, columns=["county", "province", "nuts3_region", "homeless_region"])


def local_authority_frame() -> pd.DataFrame:
    return pd.DataFrame(LOCAL_AUTHORITIES, columns=["la_name", "county", "la_type"])


def region_frame() -> pd.DataFrame:
    rows = [(r, "NUTS3") for r in NUTS3_REGIONS] + [(r, "HOMELESS") for r in HOMELESS_REGIONS]
    return pd.DataFrame(rows, columns=["region_name", "region_type"])
