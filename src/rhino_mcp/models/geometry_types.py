"""Pydantic models mirroring core rhino3dm geometry primitives."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class Point3dModel(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"x": 0.0, "y": 0.0, "z": 0.0}]})
    x: float = Field(..., description="X coordinate in document units")
    y: float = Field(..., description="Y coordinate in document units")
    z: float = Field(0.0, description="Z coordinate in document units (default 0)")


class Vector3dModel(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"x": 1.0, "y": 0.0, "z": 0.0}]})
    x: float = Field(..., description="X component")
    y: float = Field(..., description="Y component")
    z: float = Field(0.0, description="Z component (default 0)")


class PlaneModel(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "origin": {"x": 0, "y": 0, "z": 0},
                    "x_axis": {"x": 1, "y": 0, "z": 0},
                    "y_axis": {"x": 0, "y": 1, "z": 0},
                }
            ]
        }
    )
    origin: Point3dModel = Field(..., description="Plane origin")
    x_axis: Vector3dModel = Field(
        default_factory=lambda: Vector3dModel(x=1.0, y=0.0, z=0.0),
        description="X-axis (unit vector)",
    )
    y_axis: Vector3dModel = Field(
        default_factory=lambda: Vector3dModel(x=0.0, y=1.0, z=0.0),
        description="Y-axis (unit vector, must be orthogonal to x_axis)",
    )


class IntervalModel(BaseModel):
    t0: float = Field(..., description="Lower bound")
    t1: float = Field(..., description="Upper bound")


class BoundingBoxModel(BaseModel):
    min: Point3dModel = Field(..., description="Lower-left-front corner")
    max: Point3dModel = Field(..., description="Upper-right-back corner")


class ColorRGBA(BaseModel):
    r: Annotated[int, Field(ge=0, le=255, description="Red 0-255")] = 0
    g: Annotated[int, Field(ge=0, le=255, description="Green 0-255")] = 0
    b: Annotated[int, Field(ge=0, le=255, description="Blue 0-255")] = 0
    a: Annotated[int, Field(ge=0, le=255, description="Alpha 0-255 (default opaque)")] = 255


class Transform4x4(BaseModel):
    matrix: list[list[float]] = Field(
        ...,
        description="4x4 row-major transform matrix",
        min_length=4,
        max_length=4,
    )
