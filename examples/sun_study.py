"""Sun study workflow example.

Compute solar position for a given location/time, draw monthly sun-path
polylines on a 100 m hemisphere, and project simple shadow polygons from
a row of buildings onto the ground plane. Runs in standalone.
"""

from rhino_mcp.document import registry
from rhino_mcp.tools.context import set_runtime
from rhino_mcp.utils.registry import Mode

set_runtime(Mode.STANDALONE, None)

# Seoul, City Hall.
LATITUDE = 37.5663
LONGITUDE = 126.9779
TIMEZONE = 9.0


def main() -> None:
    handle = registry().get_or_create("sun_demo")
    file3dm = handle.file3dm

    import rhino3dm as r3

    # Massing — a row of three boxes.
    for i in range(3):
        bbox = r3.BoundingBox(r3.Point3d(i * 25, 0, 0), r3.Point3d(i * 25 + 12, 18, 24 - i * 6))
        attrs = r3.ObjectAttributes()
        attrs.Name = f"Block_{i}"
        file3dm.Objects.AddBrep(r3.Brep.CreateFromBox(r3.Box(bbox)), attrs)
    object_ids = [str(file3dm.Objects[i].Attributes.Id) for i in range(len(file3dm.Objects))]

    from rhino_mcp.tools.environment import (
        _ShadowProjectIn,
        _SunPathIn,
        _SunPositionIn,
        register,
        solar_position,
        sun_vector_from_az_alt,
    )

    class _Bag:
        funcs: dict[str, object] = {}

        def tool(self, **_):
            def deco(fn):
                self.funcs[fn.__name__] = fn
                return fn

            return deco

    bag = _Bag()
    register(bag, Mode.STANDALONE)

    # Solar position at 14:00 on June 21.
    when_iso = "2026-06-21T14:00:00"
    pos = bag.funcs["rhino_sun_position"](
        _SunPositionIn(
            latitude=LATITUDE,
            longitude=LONGITUDE,
            datetime_iso=when_iso,
            timezone_offset_h=TIMEZONE,
        )
    )
    print(f"Sun at {when_iso} (Seoul):")
    print(f"  azimuth = {pos['summary']['azimuth_deg']:.2f} deg")
    print(f"  altitude = {pos['summary']['altitude_deg']:.2f} deg")

    # Draw monthly sun-path polylines.
    bag.funcs["rhino_sun_path"](
        _SunPathIn(
            doc_id="sun_demo",
            latitude=LATITUDE,
            longitude=LONGITUDE,
            year=2026,
            months=[3, 6, 9, 12],
            hours=[7, 9, 11, 13, 15, 17],
            radius=80.0,
            timezone_offset_h=TIMEZONE,
        )
    )

    # Project shadows from sun_dir at 14:00 (vector points away from sun).
    import datetime as _dt

    when = _dt.datetime.fromisoformat(when_iso)
    az, alt = solar_position(LATITUDE, LONGITUDE, when, TIMEZONE)
    sx, sy, sz = sun_vector_from_az_alt(az, alt)
    # Shadow ray points from object toward ground (i.e. -sun_to_object).
    ray = (-sx, -sy, -sz)
    bag.funcs["rhino_shadow_project"](
        _ShadowProjectIn(
            doc_id="sun_demo",
            object_ids=object_ids,
            sun_vector={"x": ray[0], "y": ray[1], "z": ray[2]},
            ground_z=0.0,
        )
    )

    output = "/tmp/sun_study_demo.3dm"
    file3dm.Write(output, version=8)
    print(f"\n3DM written: {output}")


if __name__ == "__main__":
    main()
