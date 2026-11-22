"""Coordinate conversion: Irish Transverse Mercator (EPSG:2157) -> WGS84 longitude/latitude.

Tailte Eireann's boundary downloads are published in ITM metres.  Plotly maps need lon/lat, so we
apply the inverse Transverse Mercator projection (Snyder series, GRS80 ellipsoid; ITM and WGS84 differ
by well under a metre, which is irrelevant for a county-scale choropleth).
"""
from __future__ import annotations

import numpy as np

_A = 6378137.0
_F = 1 / 298.257222101
_E2 = 2 * _F - _F * _F
_EP2 = _E2 / (1 - _E2)
_K0 = 0.99982
_LAT0 = np.radians(53.5)
_LON0 = np.radians(-8.0)
_FE, _FN = 600000.0, 750000.0


def _meridian_arc(phi):
    e2, e4, e6 = _E2, _E2 ** 2, _E2 ** 3
    return _A * ((1 - e2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * phi
                 - (3 * e2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * np.sin(2 * phi)
                 + (15 * e4 / 256 + 45 * e6 / 1024) * np.sin(4 * phi)
                 - (35 * e6 / 3072) * np.sin(6 * phi))


def itm_to_wgs84(easting, northing):
    """Return (longitude, latitude) in degrees for ITM easting/northing in metres (scalars or arrays)."""
    e = np.asarray(easting, dtype=float)
    n = np.asarray(northing, dtype=float)
    m = _meridian_arc(_LAT0) + (n - _FN) / _K0
    mu = m / (_A * (1 - _E2 / 4 - 3 * _E2 ** 2 / 64 - 5 * _E2 ** 3 / 256))
    e1 = (1 - np.sqrt(1 - _E2)) / (1 + np.sqrt(1 - _E2))
    phi1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * np.sin(2 * mu)
            + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * np.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * np.sin(6 * mu) + (1097 * e1 ** 4 / 512) * np.sin(8 * mu))
    sin1, cos1, tan1 = np.sin(phi1), np.cos(phi1), np.tan(phi1)
    c1 = _EP2 * cos1 ** 2
    t1 = tan1 ** 2
    n1 = _A / np.sqrt(1 - _E2 * sin1 ** 2)
    r1 = _A * (1 - _E2) / (1 - _E2 * sin1 ** 2) ** 1.5
    d = (e - _FE) / (n1 * _K0)
    lat = phi1 - (n1 * tan1 / r1) * (d ** 2 / 2
                                      - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * _EP2) * d ** 4 / 24
                                      + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * _EP2 - 3 * c1 ** 2) * d ** 6 / 720)
    lon = _LON0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6
                   + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * _EP2 + 24 * t1 ** 2) * d ** 5 / 120) / cos1
    return np.degrees(lon), np.degrees(lat)
