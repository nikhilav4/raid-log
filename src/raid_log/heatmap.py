"""5x5 probability by impact grid with risk IDs placed in their cells."""

from __future__ import annotations

import datetime as dt
import io
from collections import defaultdict
from pathlib import Path

import matplotlib
from matplotlib.figure import Figure
from matplotlib.patches import Patch, Rectangle

from raid_log.bands import BANDS, band_for
from raid_log.model import Item, ItemType, Register

PROBABILITY_LABELS = ["Rare", "Unlikely", "Possible", "Likely", "Almost certain"]
IMPACT_LABELS = ["Negligible", "Minor", "Moderate", "Major", "Severe"]
# Two IDs per row and four rows is what fits in a cell at the default figure size.
IDS_PER_ROW = 2
MAX_IDS_PER_CELL = 8


def plotted_risks(register: Register, include_closed: bool = False) -> list[Item]:
    return [
        item
        for item in register.items
        if item.type is ItemType.RISK
        and item.exposure is not None
        and (include_closed or item.is_active)
    ]


def draw(register: Register, today: dt.date, include_closed: bool = False) -> Figure:
    risks = plotted_risks(register, include_closed)
    cells: dict[tuple[int, int], list[str]] = defaultdict(list)
    for risk in sorted(risks, key=lambda r: r.id):
        cells[(risk.probability or 0, risk.impact or 0)].append(risk.id)

    fig = Figure(figsize=(8, 7.4), layout="constrained")
    ax = fig.add_subplot()
    for probability in range(1, 6):
        for impact in range(1, 6):
            exposure = probability * impact
            ax.add_patch(
                Rectangle(
                    (impact - 0.5, probability - 0.5),
                    1,
                    1,
                    facecolor=band_for(exposure).color,
                    edgecolor="white",
                    linewidth=3,
                )
            )
            ax.text(
                impact - 0.43,
                probability + 0.41,
                str(exposure),
                fontsize=8,
                color="#5f6b76",
                ha="left",
                va="top",
            )
            ids = cells.get((probability, impact))
            if ids:
                ax.text(
                    impact,
                    probability - 0.06,
                    _wrap(ids),
                    fontsize=9.5,
                    fontweight="bold",
                    color="#1d2733",
                    ha="center",
                    va="center",
                    linespacing=1.35,
                )

    ax.set_xlim(0.5, 5.5)
    ax.set_ylim(0.5, 5.5)
    ax.set_aspect("equal")
    ax.set_xticks(range(1, 6), [f"{n}\n{label}" for n, label in enumerate(IMPACT_LABELS, 1)])
    ax.set_yticks(range(1, 6), [f"{label} {n}" for n, label in enumerate(PROBABILITY_LABELS, 1)])
    ax.tick_params(length=0, labelsize=9, colors="#33404d")
    ax.set_xlabel("Impact", fontsize=10, color="#33404d", labelpad=8)
    ax.set_ylabel("Probability", fontsize=10, color="#33404d", labelpad=8)
    for spine in ax.spines.values():
        spine.set_visible(False)

    noun = "risk" if len(risks) == 1 else "risks"
    scope = noun if include_closed else f"active {noun}"
    ax.set_title(
        f"{register.title}\n{len(risks)} {scope} as of {today}",
        loc="left",
        fontsize=11,
        color="#1d2733",
        pad=12,
    )
    fig.legend(
        handles=[Patch(facecolor=band.color, label=band.label) for band in reversed(BANDS)],
        loc="outside lower center",
        ncols=4,
        frameon=False,
        fontsize=8.5,
        title="Exposure = probability x impact",
        title_fontsize=8.5,
    )
    return fig


def save(fig: Figure, path: Path) -> None:
    with matplotlib.rc_context(_SVG_SETTINGS):
        fig.savefig(path, dpi=150, metadata=_metadata(path.suffix))


def to_svg(fig: Figure) -> str:
    buffer = io.StringIO()
    with matplotlib.rc_context(_SVG_SETTINGS):
        fig.savefig(buffer, format="svg", metadata=_metadata(".svg"))
    return buffer.getvalue()


# Text stays text (small, searchable IDs) and the output is byte-for-byte repeatable.
_SVG_SETTINGS = {"svg.fonttype": "none", "svg.hashsalt": "raid-log"}


def _metadata(suffix: str) -> dict[str, str | None]:
    return {"Date": None} if suffix.lower() == ".svg" else {}


def _wrap(ids: list[str]) -> str:
    shown = ids if len(ids) <= MAX_IDS_PER_CELL else ids[: MAX_IDS_PER_CELL - IDS_PER_ROW]
    rows = ["  ".join(shown[i : i + IDS_PER_ROW]) for i in range(0, len(shown), IDS_PER_ROW)]
    if len(shown) < len(ids):
        rows.append(f"+{len(ids) - len(shown)} more")
    return "\n".join(rows)
