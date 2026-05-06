"""Environmental analysis — sun position, sun path, shadow projection.

Computes solar position via a NOAA Solar Position Algorithm (SPA)
approximation accurate to roughly +/- 0.5 deg for civil-engineering
purposes (sun studies, passive design checks). No external dependency
beyond the standard library + ``rhino3dm``.

Standalone supports the pure-math tools (``sun_position``, ``sun_path``)
and an AABB-corner shadow projection. Higher-fidelity solar exposure
estimation requires ray casting against the Rhino document and is bridge
only.
"""

from __future__ import annotations

import datetime as _dt
import math
from typing import Annotated, Any
from uuid import UUID

import rhino3dm as r3
from pydantic import BaseModel, Field

from rhino_mcp.models.geometry_types import Point3dModel
from rhino_mcp.tools._helpers import MAX_OBJECT_IDS, bridge_call, doc, require_bridge_only, to_point
from rhino_mcp.tools.context import runtime
from rhino_mcp.utils.error_handling import not_found_error, parameter_error
from rhino_mcp.utils.registry import Mode


class _DocArg(BaseModel):
    doc_id: str = Field(
        "active",
        description="Document handle id; 'active' targets the current document.",
    )


class _SunPositionIn(BaseModel):
    latitude: Annotated[float, Field(ge=-90, le=90)] = 37.5663
    longitude: Annotated[float, Field(ge=-180, le=180)] = 126.9779
    datetime_iso: str = Field(
        ..., description="ISO-8601 datetime, e.g. 2026-06-21T12:00:00."
    )
    timezone_offset_h: Annotated[float, Field(ge=-12, le=14)] = 9.0


class _SunPathIn(_DocArg):
    latitude: Annotated[float, Field(ge=-90, le=90)] = 37.5663
    longitude: Annotated[float, Field(ge=-180, le=180)] = 126.9779
    year: Annotated[int, Field(ge=1900, le=2100)] = 2026
    months: list[int] = Field(
        default_factory=lambda: [3, 6, 9, 12],
        description="Months (1-12) to draw analemmas for; one polyline per month.",
    )
    hours: list[int] = Field(
        default_factory=lambda: [6, 8, 10, 12, 14, 16, 18],
        description="Hours of day (local) sampled along each monthly path.",
    )
    radius: Annotated[float, Field(gt=0, le=100000)] = 100.0
    center_point: Point3dModel = Field(default_factory=lambda: Point3dModel(x=0.0, y=0.0, z=0.0))
    timezone_offset_h: Annotated[float, Field(ge=-12, le=14)] = 9.0
    layer: str | None = Field("Site::SunPath")


class _ShadowProjectIn(_DocArg):
    object_ids: list[str] = Field(..., min_length=1, max_length=MAX_OBJECT_IDS)
    sun_vector: Point3dModel = Field(
        ..., description="Vector pointing FROM the sun TO the object (use the negative of sun-direction)."
    )
    ground_z: float = Field(0.0, description="World-Z plane the shadow is projected onto.")
    layer: str | None = Field("Site::Shadows")


class _SolarExposureIn(_DocArg):
    target_object_id: str = Field(..., description="Object whose lit/shaded ratio is computed.")
    latitude: Annotated[float, Field(ge=-90, le=90)] = 37.5663
    longitude: Annotated[float, Field(ge=-180, le=180)] = 126.9779
    date_iso: str = Field(..., description="ISO-8601 date YYYY-MM-DD.")
    hour_range: tuple[int, int] = Field((8, 18))
    step_minutes: Annotated[int, Field(ge=10, le=120)] = 60
    timezone_offset_h: Annotated[float, Field(ge=-12, le=14)] = 9.0
    obstruction_object_ids: list[str] = Field(default_factory=list, max_length=MAX_OBJECT_IDS)


class _DirectIrradianceIn(BaseModel):
    latitude: Annotated[float, Field(ge=-90, le=90)] = 37.5663
    longitude: Annotated[float, Field(ge=-180, le=180)] = 126.9779
    datetime_iso: str = Field(..., description="ISO-8601 datetime, e.g. 2026-06-21T12:00:00.")
    timezone_offset_h: Annotated[float, Field(ge=-12, le=14)] = 9.0
    altitude_m: Annotated[float, Field(ge=0.0, le=9000.0)] = 38.0
    turbidity: Annotated[float, Field(ge=1.0, le=10.0)] = 2.5


class _DaylightFactorIn(BaseModel):
    window_area_m2: Annotated[float, Field(gt=0)] = Field(
        ..., description="Total glazed area W (m^2)."
    )
    visible_sky_angle_deg: Annotated[float, Field(ge=0, le=180)] = Field(
        ..., description="Angle of sky visible from window (theta, degrees)."
    )
    glass_transmittance: Annotated[float, Field(gt=0, le=1)] = 0.7
    maintenance_factor: Annotated[float, Field(gt=0, le=1)] = 0.9
    total_surface_area_m2: Annotated[float, Field(gt=0)] = Field(
        ..., description="Total internal surface area A_total (m^2)."
    )
    average_reflectance: Annotated[float, Field(ge=0, lt=1)] = 0.5


def _parse_iso(s: str) -> _dt.datetime:
    try:
        return _dt.datetime.fromisoformat(s)
    except ValueError as exc:
        raise parameter_error("datetime_iso", f"could not parse '{s}'") from exc


def solar_position(latitude: float, longitude: float, when: _dt.datetime, tz_offset_h: float) -> tuple[float, float]:
    """Return (azimuth_deg [0=N, CW], altitude_deg) for the given location/time.

    Implements the standard NOAA SPA approximation. Suitable for sun studies
    where +/- 0.5 deg accuracy is acceptable. For research-grade radiation
    modelling use a dedicated library (pvlib, ladybug-tools).
    """
    # Convert local time to UTC.
    utc = when - _dt.timedelta(hours=tz_offset_h)
    # Days since 2000-01-01 12:00 UTC (J2000).
    j2000 = _dt.datetime(2000, 1, 1, 12, 0, 0, tzinfo=None)
    n = (utc - j2000).total_seconds() / 86400.0

    # Mean longitude and mean anomaly of the Sun (deg).
    L = (280.460 + 0.9856474 * n) % 360.0
    g = math.radians((357.528 + 0.9856003 * n) % 360.0)
    # Ecliptic longitude (deg).
    lam = math.radians(L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    # Obliquity of the ecliptic.
    eps = math.radians(23.439 - 0.0000004 * n)

    # Right ascension and declination.
    ra = math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))  # rad
    dec = math.asin(math.sin(eps) * math.sin(lam))  # rad

    # Greenwich Mean Sidereal Time (hours).
    gmst = (18.697374558 + 24.06570982441908 * n) % 24.0
    # Local Sidereal Time (rad).
    lst = math.radians((gmst * 15.0 + longitude) % 360.0)
    # Hour angle (rad).
    ha = lst - ra

    lat_r = math.radians(latitude)
    sin_alt = math.sin(lat_r) * math.sin(dec) + math.cos(lat_r) * math.cos(dec) * math.cos(ha)
    sin_alt = max(-1.0, min(1.0, sin_alt))
    altitude = math.degrees(math.asin(sin_alt))
    sin_az = -math.cos(dec) * math.sin(ha)
    cos_az = math.sin(dec) * math.cos(lat_r) - math.cos(dec) * math.sin(lat_r) * math.cos(ha)
    azimuth = (math.degrees(math.atan2(sin_az, cos_az)) + 360.0) % 360.0
    return azimuth, altitude


def kasten_young_air_mass(altitude_deg: float) -> float:
    """Air-mass ratio (Kasten-Young 1989). Returns infinity below the horizon.

    AM = 1 / (sin(alt) + 0.50572 * (alt + 6.07995)^-1.6364)
    Used by direct-beam irradiance models that need a finite air-mass for
    altitudes near the horizon.
    """
    if altitude_deg <= 0:
        return float("inf")
    return 1.0 / (
        math.sin(math.radians(altitude_deg))
        + 0.50572 * (altitude_deg + 6.07995) ** -1.6364
    )


def direct_normal_irradiance(altitude_deg: float, altitude_m: float, turbidity: float) -> float:
    """Direct Normal Irradiance (W/m^2) using a Bird-style clear-sky model.

    DNI = E0 * exp(-T_link * AM_relative)
    where E0 is the extraterrestrial irradiance (~1361 W/m^2), AM_relative is
    Kasten-Young air mass, and T_link wraps Linke turbidity ~1 (very clear)
    .. ~7 (industrial haze). Suitable for civil-engineering daylight studies
    when ladybug-tools / pvlib are unavailable.
    """
    if altitude_deg <= 0:
        return 0.0
    e0 = 1361.0
    am = kasten_young_air_mass(altitude_deg)
    # Altitude-pressure correction (US standard atmosphere).
    pressure_ratio = math.exp(-altitude_m / 8500.0)
    am_abs = am * pressure_ratio
    return e0 * math.exp(-0.1 * turbidity * am_abs)


def daylight_factor_bre(
    window_area: float,
    sky_angle_deg: float,
    transmittance: float,
    maintenance: float,
    total_surface_area: float,
    avg_reflectance: float,
) -> float:
    """BRE simplified daylight factor (% of internal illuminance / external illuminance).

    DF = (W * theta * tau * M) / (A * (1 - R^2))
    where W is glazed area (m^2), theta is the visible-sky angle (degrees),
    tau is glazing transmittance, M is maintenance factor, A is total
    internal surface area (m^2) and R is the average reflectance.
    """
    denom = total_surface_area * (1.0 - avg_reflectance * avg_reflectance)
    if denom <= 0:
        return 0.0
    return (window_area * sky_angle_deg * transmittance * maintenance) / denom


def sun_vector_from_az_alt(azimuth_deg: float, altitude_deg: float) -> tuple[float, float, float]:
    """Convert (azimuth, altitude) to a unit vector pointing toward the sun.

    World convention: +X = east, +Y = north, +Z = up. Azimuth is measured
    clockwise from north (0 = N, 90 = E, 180 = S, 270 = W).
    """
    az = math.radians(azimuth_deg)
    alt = math.radians(altitude_deg)
    x = math.cos(alt) * math.sin(az)
    y = math.cos(alt) * math.cos(az)
    z = math.sin(alt)
    return x, y, z


def _project_to_z_plane(p: r3.Point3d, sun_dir: tuple[float, float, float], ground_z: float) -> r3.Point3d | None:
    """Project ``p`` along ``sun_dir`` onto the plane Z = ground_z. Return None for grazing rays.

    ``sun_dir`` points FROM the object TOWARD the ground (the light's propagation
    direction). A ray ``p + t * sun_dir`` is shot until its Z hits ``ground_z``.
    """
    sx, sy, sz = sun_dir
    if abs(sz) < 1e-9:
        return None
    t = (ground_z - p.Z) / sz
    if t < 0:
        return None
    return r3.Point3d(p.X + t * sx, p.Y + t * sy, ground_z)


def register(mcp, mode: Mode) -> None:  # type: ignore[no-untyped-def]
    @mcp.tool(annotations={"title": "Sun Position", "readOnlyHint": True, "idempotentHint": True})
    def rhino_sun_position(args: _SunPositionIn) -> dict[str, Any]:
        """Compute solar azimuth + altitude for a location/time. Pure calculation, no doc edits."""
        when = _parse_iso(args.datetime_iso)
        az, alt = solar_position(args.latitude, args.longitude, when, args.timezone_offset_h)
        sx, sy, sz = sun_vector_from_az_alt(az, alt)
        return {
            "summary": {
                "azimuth_deg": round(az, 4),
                "altitude_deg": round(alt, 4),
                "sun_vector": {"x": round(sx, 6), "y": round(sy, 6), "z": round(sz, 6)},
                "is_above_horizon": alt > 0,
                "datetime": args.datetime_iso,
                "latitude": args.latitude,
                "longitude": args.longitude,
            },
            "text": f"Sun: az={az:.2f}°, alt={alt:.2f}° (above_horizon={alt > 0})",
        }

    @mcp.tool(annotations={"title": "Sun Path", "readOnlyHint": False})
    def rhino_sun_path(args: _SunPathIn) -> dict[str, Any]:
        """Draw monthly sun-path polylines on a hemisphere of given radius around ``center_point``.

        Standalone draws into the active rhino3dm document; bridge mode
        forwards so the path is visible in Rhino's viewport.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.environment.sun_path", args.model_dump())
        h = doc(args.doc_id)
        from rhino_mcp.tools._helpers import _resolve_layer_index

        layer_index = _resolve_layer_index(h, args.layer or "Site::SunPath")
        center = to_point(args.center_point)

        # One polyline per month, samples = hours of day.
        polyline_ids: list[str] = []
        sample_count = 0
        for month in args.months:
            if not 1 <= month <= 12:
                raise parameter_error("months", "month entries must be in 1..12")
            poly = r3.Polyline()
            day = 21  # solstice/equinox-ish midpoint of each month
            for hour in args.hours:
                if not 0 <= hour <= 23:
                    raise parameter_error("hours", "hour entries must be in 0..23")
                when = _dt.datetime(args.year, month, day, hour, 0, 0)
                az, alt = solar_position(args.latitude, args.longitude, when, args.timezone_offset_h)
                if alt < 0:
                    continue
                sx, sy, sz = sun_vector_from_az_alt(az, alt)
                p = r3.Point3d(
                    center.X + args.radius * sx,
                    center.Y + args.radius * sy,
                    center.Z + args.radius * sz,
                )
                poly.Add(p.X, p.Y, p.Z)
                sample_count += 1
            if poly.Count >= 2:
                pc = poly.ToPolylineCurve()
                attrs = r3.ObjectAttributes()
                attrs.LayerIndex = layer_index
                attrs.Name = f"sunpath_{args.year}_{month:02d}"
                attrs.SetUserString("month", str(month))
                attrs.SetUserString("year", str(args.year))
                new_id: UUID = h.file3dm.Objects.Add(pc, attrs)
                polyline_ids.append(h.add_index(new_id))
        return {
            "summary": {
                "polyline_ids": polyline_ids,
                "month_count": len(polyline_ids),
                "sample_count": sample_count,
                "radius": args.radius,
            },
            "text": f"Sun path: {len(polyline_ids)} polyline(s), {sample_count} samples",
        }

    @mcp.tool(annotations={"title": "Project Shadow", "readOnlyHint": False})
    def rhino_shadow_project(args: _ShadowProjectIn) -> dict[str, Any]:
        """Project objects' bounding-box corners along ``sun_vector`` to the ground plane.

        Standalone produces a coarse 4-corner shadow polygon per object
        (suitable for sketch-grade studies). Bridge mode emits accurate
        wireframe-projection shadow polygons.
        """
        if runtime().mode is Mode.BRIDGE:
            return bridge_call("rhino.environment.shadow_project", args.model_dump())
        h = doc(args.doc_id)
        sun = to_point(args.sun_vector)
        # Normalise.
        n = math.sqrt(sun.X * sun.X + sun.Y * sun.Y + sun.Z * sun.Z)
        if n < 1e-9:
            raise parameter_error("sun_vector", "sun_vector cannot be zero")
        sun_dir = (sun.X / n, sun.Y / n, sun.Z / n)
        if sun_dir[2] >= 0:
            raise parameter_error(
                "sun_vector",
                "sun_vector.z must be negative (rays travelling downward to ground)",
            )
        from rhino_mcp.tools._helpers import _resolve_layer_index

        layer_index = _resolve_layer_index(h, args.layer or "Site::Shadows")

        shadow_ids: list[str] = []
        for oid in args.object_ids:
            obj = h.file3dm.Objects.FindId(oid)
            if obj is None:
                raise not_found_error("object", oid)
            bb = obj.Geometry.GetBoundingBox()
            corners_3d = [
                r3.Point3d(bb.Min.X, bb.Min.Y, bb.Min.Z),
                r3.Point3d(bb.Max.X, bb.Min.Y, bb.Min.Z),
                r3.Point3d(bb.Max.X, bb.Max.Y, bb.Min.Z),
                r3.Point3d(bb.Min.X, bb.Max.Y, bb.Min.Z),
                r3.Point3d(bb.Min.X, bb.Min.Y, bb.Max.Z),
                r3.Point3d(bb.Max.X, bb.Min.Y, bb.Max.Z),
                r3.Point3d(bb.Max.X, bb.Max.Y, bb.Max.Z),
                r3.Point3d(bb.Min.X, bb.Max.Y, bb.Max.Z),
            ]
            projected: list[r3.Point3d] = []
            for c in corners_3d:
                pp = _project_to_z_plane(c, sun_dir, args.ground_z)
                if pp is not None:
                    projected.append(pp)
            if not projected:
                continue
            # 2-D convex hull of projected corners (XY only).
            hull = _convex_hull_xy(projected)
            if len(hull) < 3:
                continue
            poly = r3.Polyline()
            for p in hull:
                poly.Add(p.X, p.Y, args.ground_z)
            poly.Add(hull[0].X, hull[0].Y, args.ground_z)
            pc = poly.ToPolylineCurve()
            attrs = r3.ObjectAttributes()
            attrs.LayerIndex = layer_index
            attrs.Name = f"shadow_{oid[:8]}"
            attrs.SetUserString("source_object_id", oid)
            new_id = h.file3dm.Objects.Add(pc, attrs)
            shadow_ids.append(h.add_index(new_id))
        return {
            "summary": {
                "shadow_ids": shadow_ids,
                "object_count": len(args.object_ids),
                "shadow_count": len(shadow_ids),
                "ground_z": args.ground_z,
            },
            "text": f"Projected {len(shadow_ids)} shadow(s) from {len(args.object_ids)} object(s)",
        }

    @mcp.tool(annotations={"title": "Direct Beam Irradiance", "readOnlyHint": True, "idempotentHint": True})
    def rhino_direct_irradiance(args: _DirectIrradianceIn) -> dict[str, Any]:
        """Direct Normal Irradiance (W/m^2) clear-sky estimate via Bird + Kasten-Young air mass.

        Includes Linke turbidity (1 = very clear, 7 = industrial haze) and
        site altitude. Pure calculation — no doc edits.
        """
        when = _parse_iso(args.datetime_iso)
        az, alt = solar_position(args.latitude, args.longitude, when, args.timezone_offset_h)
        am = kasten_young_air_mass(alt)
        dni = direct_normal_irradiance(alt, args.altitude_m, args.turbidity)
        return {
            "summary": {
                "azimuth_deg": round(az, 4),
                "altitude_deg": round(alt, 4),
                "air_mass": round(am, 4) if math.isfinite(am) else None,
                "dni_w_per_m2": round(dni, 2),
                "is_above_horizon": alt > 0,
                "datetime": args.datetime_iso,
                "altitude_m": args.altitude_m,
                "turbidity": args.turbidity,
            },
            "text": (
                f"DNI={dni:.1f} W/m^2 at alt={alt:.2f}°, AM={am:.2f}"
                if math.isfinite(am) else "Sun below horizon: DNI=0"
            ),
        }

    @mcp.tool(annotations={"title": "Daylight Factor (BRE)", "readOnlyHint": True, "idempotentHint": True})
    def rhino_daylight_factor(args: _DaylightFactorIn) -> dict[str, Any]:
        """BRE simplified daylight factor for a side-lit room.

        DF = (W * theta * tau * M) / (A_total * (1 - R^2)) (% as decimal).
        For early-stage architectural studies; for radiance-grade accuracy
        use ladybug-tools or DAYSIM.
        """
        df = daylight_factor_bre(
            args.window_area_m2,
            args.visible_sky_angle_deg,
            args.glass_transmittance,
            args.maintenance_factor,
            args.total_surface_area_m2,
            args.average_reflectance,
        )
        rating = (
            "deficient (<2%)" if df < 2 else
            "acceptable (2-5%)" if df < 5 else
            "good (>=5%)"
        )
        return {
            "summary": {
                "daylight_factor_pct": round(df, 3),
                "rating": rating,
                "inputs": args.model_dump(),
            },
            "text": f"BRE daylight factor = {df:.2f}% ({rating})",
        }

    @mcp.tool(annotations={"title": "Solar Exposure Estimate", "readOnlyHint": True})
    def rhino_solar_exposure_estimate(args: _SolarExposureIn) -> dict[str, Any]:
        """Estimate cumulative solar exposure (lit minutes / total minutes) on an object (bridge only).

        Bridge implementation samples the time range, casts a ray from the
        target's centroid toward the sun at each step, and counts lit
        samples (no obstruction along the ray). Returns a 0-1 ratio.
        """
        require_bridge_only("rhino_solar_exposure_estimate")
        return bridge_call("rhino.environment.solar_exposure_estimate", args.model_dump())


def _convex_hull_xy(points: list[r3.Point3d]) -> list[r3.Point3d]:
    """Andrew's monotone-chain convex hull on the XY projection."""
    pts = sorted({(round(p.X, 6), round(p.Y, 6)) for p in points})
    if len(pts) <= 1:
        return [r3.Point3d(x, y, 0.0) for x, y in pts]

    def cross(o: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    return [r3.Point3d(x, y, 0.0) for x, y in hull]
