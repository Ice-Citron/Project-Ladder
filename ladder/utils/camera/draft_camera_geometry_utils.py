from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any


@dataclass(slots=True)
class CameraIntrinsics:
    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float

    @classmethod
    def from_camera_info(cls, camera_info: Any) -> "CameraIntrinsics":
        k = list(camera_info.k)
        width = int(getattr(camera_info, "width", 0))
        height = int(getattr(camera_info, "height", 0))
        return cls(
            width=width,
            height=height,
            fx=float(k[0]),
            fy=float(k[4]),
            cx=float(k[2]),
            cy=float(k[5]),
        )


@dataclass(slots=True)
class PixelAngles:
    yaw_rad: float
    pitch_rad: float


@dataclass(slots=True)
class PixelRay:
    x: float
    y: float
    z: float


def pixel_to_normalized_xy(u: float, v: float, intrinsics: CameraIntrinsics) -> tuple[float, float]:
    x = (u - intrinsics.cx) / intrinsics.fx
    y = (v - intrinsics.cy) / intrinsics.fy
    return x, y


def pixel_to_ray(u: float, v: float, intrinsics: CameraIntrinsics) -> PixelRay:
    x, y = pixel_to_normalized_xy(u, v, intrinsics)
    norm = math.sqrt(x * x + y * y + 1.0)
    return PixelRay(x=x / norm, y=y / norm, z=1.0 / norm)


def pixel_to_angles(u: float, v: float, intrinsics: CameraIntrinsics) -> PixelAngles:
    x, y = pixel_to_normalized_xy(u, v, intrinsics)
    yaw_rad = math.atan2(x, 1.0)
    pitch_rad = math.atan2(y, 1.0)
    return PixelAngles(yaw_rad=yaw_rad, pitch_rad=pitch_rad)


def project_point_to_pixel(x_m: float, y_m: float, z_m: float, intrinsics: CameraIntrinsics) -> tuple[float, float]:
    if z_m == 0.0:
        raise ValueError("Cannot project a point with z == 0.")
    u = intrinsics.fx * (x_m / z_m) + intrinsics.cx
    v = intrinsics.fy * (y_m / z_m) + intrinsics.cy
    return u, v


def pixel_distance_to_angle(delta_px: float, focal_length_px: float) -> float:
    return math.atan2(delta_px, focal_length_px)


def bounding_box_radius_px(x0: int, y0: int, x1: int, y1: int) -> float:
    width = max(0, x1 - x0)
    height = max(0, y1 - y0)
    return 0.25 * (width + height)


def estimate_depth_from_apparent_radius(
    radius_px: float,
    true_radius_m: float,
    focal_length_px: float,
) -> float:
    if radius_px <= 0.0:
        raise ValueError("radius_px must be > 0")
    return (true_radius_m * focal_length_px) / radius_px


def frame_margin_score(u: float, v: float, intrinsics: CameraIntrinsics) -> float:
    if intrinsics.width <= 0 or intrinsics.height <= 0:
        return 0.0
    margin_x = min(u, intrinsics.width - u) / max(1.0, intrinsics.width / 2.0)
    margin_y = min(v, intrinsics.height - v) / max(1.0, intrinsics.height / 2.0)
    return max(0.0, min(1.0, min(margin_x, margin_y)))
