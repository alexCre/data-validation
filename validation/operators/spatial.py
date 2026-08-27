from shapely import wkt as shapely_wkt
from shapely.geometry import Point

from validation.registry import operator

_GEOD = None


def _geod():
    global _GEOD
    if _GEOD is None:
        from pyproj import Geod

        _GEOD = Geod(ellps="WGS84")
    return _GEOD


def _parse_wkt(value):
    if not value:
        return None
    try:
        geom = shapely_wkt.loads(value)
    except Exception:
        return None
    if geom.is_empty:
        return None
    return geom


@operator(
    "geometry_exists",
    category="spatial",
    description="True if the lot has a parseable geometry (WKT).",
    input_types=["geometry_wkt"],
    output_type="bool",
)
def geometry_exists(geometry_wkt) -> bool:
    return _parse_wkt(geometry_wkt) is not None


@operator(
    "geometry_area_ha",
    category="spatial",
    description=(
        "Geodesic area of a WKT geometry in hectares, computed on the WGS84 "
        "ellipsoid (EPSG:4326 coordinates) via pyproj.Geod, not by "
        "reprojecting to an equal-area planar CRS."
    ),
    input_types=["geometry_wkt"],
    output_type="number",
)
def geometry_area_ha(geometry_wkt) -> float | None:
    geom = _parse_wkt(geometry_wkt)
    if geom is None:
        return None
    area_m2, _perimeter = _geod().geometry_area_perimeter(geom)
    return abs(area_m2) / 10_000


@operator(
    "point_within_geometry",
    category="spatial",
    description="True if the (lat, lon) point falls within the WKT geometry.",
    input_types=["number", "number", "geometry_wkt"],
    output_type="bool",
)
def point_within_geometry(latitude, longitude, geometry_wkt) -> bool | None:
    geom = _parse_wkt(geometry_wkt)
    if geom is None or latitude is None or longitude is None:
        return None
    point = Point(longitude, latitude)
    return geom.contains(point)
