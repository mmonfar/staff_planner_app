"""Built-in fallback for the optional mmonfar_brand package.

mmonfar_brand is not on PyPI (its repo is local only). When it is missing,
the app uses these values. They are copied from brand-identity's token file
(mcp/brand/mmonfar-brand-tokens.json). When the package is present, it wins.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

CANVAS = "#17242B"
CREAM = "#FDFBF7"
TEAL = "#008080"
TEAL_BRIGHT = "#00A3A3"
SERIES = [TEAL, TEAL_BRIGHT, "#60AFAD", "#89C2C0", "#ACD4D1", "#BBDBD8"]

tokens = SimpleNamespace(
    CANVAS=CANVAS, CREAM=CREAM, TEAL=TEAL, TEAL_BRIGHT=TEAL_BRIGHT, SERIES=SERIES
)

_FONTS = {
    "display": ["Plus Jakarta Sans", "Segoe UI", "DejaVu Sans"],
    "label": ["Space Grotesk", "Segoe UI", "DejaVu Sans"],
}


def _streamlit_apply(st_module: Any, *, page_title: str | None = None,
                     page_icon: str | None = None, layout: str = "wide",
                     set_page_config: bool = True, **kwargs: Any) -> None:
    """Page config plus a small brand stylesheet (accent and fonts only)."""
    if set_page_config:
        cfg: dict[str, Any] = {"layout": layout, **kwargs}
        if page_title is not None:
            cfg["page_title"] = page_title
        if page_icon is not None:
            cfg["page_icon"] = page_icon
        st_module.set_page_config(**cfg)
    st_module.markdown(
        "<style>html, body, [data-testid='stAppViewContainer'] "
        f"{{font-family: 'Plus Jakarta Sans', 'Segoe UI', system-ui, sans-serif; "
        f"color: {CANVAS};}} a {{color: {TEAL};}}</style>",
        unsafe_allow_html=True,
    )


def _matplotlib_apply(ground: str = "light") -> None:
    """Set matplotlib colours and fonts close to the identity."""
    import matplotlib as mpl
    from cycler import cycler

    dark = ground == "dark"
    bg, ink = (CANVAS, CREAM) if dark else (CREAM, CANVAS)
    mpl.rcParams.update({
        "figure.facecolor": bg, "axes.facecolor": bg, "savefig.facecolor": bg,
        "text.color": ink, "axes.labelcolor": ink, "axes.edgecolor": ink,
        "xtick.color": ink, "ytick.color": ink,
        "font.family": _FONTS["display"],
        "axes.prop_cycle": cycler(color=SERIES),
        "axes.spines.top": False, "axes.spines.right": False,
    })


streamlit = SimpleNamespace(apply=_streamlit_apply)
matplotlib = SimpleNamespace(apply=_matplotlib_apply)
