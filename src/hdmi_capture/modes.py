"""HDMI capture timing profiles."""
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class CaptureMode:
    """One input timing and its fixed LiteX receiver configuration."""

    name: str
    width: int
    height: int
    pixel_clock_hz: int
    gateware_clock_hz: int
    h_front_porch: int
    h_sync_width: int
    h_back_porch: int
    h_sync_positive: bool
    v_front_porch: int
    v_sync_width: int
    v_back_porch: int
    v_sync_positive: bool
    receiver_k_clk_range: int
    supported_pixel_clocks_hz: tuple[int, ...]

    @property
    def h_total(self) -> int:
        return self.width + self.h_front_porch + self.h_sync_width + self.h_back_porch

    @property
    def v_total(self) -> int:
        return self.height + self.v_front_porch + self.v_sync_width + self.v_back_porch

    @property
    def refresh_hz(self) -> float:
        return self.pixel_clock_hz / (self.h_total * self.v_total)

    @property
    def timing(self) -> dict[str, int | bool]:
        return {
            "h_front_porch": self.h_front_porch,
            "h_sync_width": self.h_sync_width,
            "h_back_porch": self.h_back_porch,
            "h_sync_positive": self.h_sync_positive,
            "v_front_porch": self.v_front_porch,
            "v_sync_width": self.v_sync_width,
            "v_back_porch": self.v_back_porch,
            "v_sync_positive": self.v_sync_positive,
        }


def mode_metadata(mode: CaptureMode) -> dict[str, object]:
    """Return the mode fields shared by build and runtime manifests."""
    return {
        "capture_mode": mode.name,
        "geometry": [mode.width, mode.height],
        "clock_hz": mode.gateware_clock_hz,
        "pixel_clock_hz": mode.pixel_clock_hz,
        "supported_pixel_clocks_hz": list(mode.supported_pixel_clocks_hz),
        "receiver_k_clk_range": mode.receiver_k_clk_range,
        "timing": mode.timing,
    }


_PROFILES = {
    "vga": CaptureMode(
        name="vga",
        width=640,
        height=480,
        pixel_clock_hz=25_200_000,
        gateware_clock_hz=142_857_132,
        h_front_porch=16,
        h_sync_width=96,
        h_back_porch=48,
        h_sync_positive=False,
        v_front_porch=10,
        v_sync_width=2,
        v_back_porch=33,
        v_sync_positive=False,
        receiver_k_clk_range=5,
        supported_pixel_clocks_hz=(25_175_000, 25_200_000),
    ),
    "1080p30": CaptureMode(
        name="1080p30",
        width=1920,
        height=1080,
        pixel_clock_hz=74_250_000,
        gateware_clock_hz=142_857_132,
        h_front_porch=88,
        h_sync_width=44,
        h_back_porch=148,
        h_sync_positive=True,
        v_front_porch=4,
        v_sync_width=5,
        v_back_porch=36,
        v_sync_positive=True,
        receiver_k_clk_range=2,
        supported_pixel_clocks_hz=(74_250_000,),
    ),
    "1080p60": CaptureMode(
        name="1080p60",
        width=1920,
        height=1080,
        pixel_clock_hz=148_500_000,
        gateware_clock_hz=142_857_132,
        h_front_porch=88,
        h_sync_width=44,
        h_back_porch=148,
        h_sync_positive=True,
        v_front_porch=4,
        v_sync_width=5,
        v_back_porch=36,
        v_sync_positive=True,
        receiver_k_clk_range=1,
        supported_pixel_clocks_hz=(148_500_000,),
    ),
}

CAPTURE_MODES: Mapping[str, CaptureMode] = MappingProxyType(_PROFILES)


def get_mode(name: str) -> CaptureMode:
    """Return a supported timing profile or reject an unknown mode name."""
    try:
        return CAPTURE_MODES[name]
    except KeyError as exc:
        raise ValueError(f"Unsupported capture mode: {name}") from exc
