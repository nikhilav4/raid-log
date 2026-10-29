from __future__ import annotations

from typing import NamedTuple


class Band(NamedTuple):
    floor: int
    name: str
    span: str
    color: str

    @property
    def label(self) -> str:
        return f"{self.name} ({self.span})"


# Floors line up with the validator: 12 and above is where a mitigation becomes mandatory.
BANDS = [
    Band(20, "Critical", "20-25", "#ef9a9a"),
    Band(12, "High", "12-16", "#f8c08a"),
    Band(5, "Moderate", "5-10", "#f9e3a0"),
    Band(1, "Low", "1-4", "#cde5c8"),
]


def band_for(exposure: int) -> Band:
    return next(band for band in BANDS if exposure >= band.floor)
