"""The app must import and resolve brand tokens without mmonfar_brand."""
import importlib
import sys


def test_main_imports_without_mmonfar_brand(monkeypatch):
    for name in [m for m in sys.modules if m == "mmonfar_brand" or m.startswith("mmonfar_brand.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "mmonfar_brand", None)  # import raises ImportError
    monkeypatch.delitem(sys.modules, "app.main", raising=False)
    # Streamlit calls outside a run are harmless bare-mode no-ops.
    main = importlib.import_module("app.main")
    assert main.brand_tokens.__class__.__name__ == "SimpleNamespace"
    assert main.TEAL == "#008080"
    assert main.INK == "#17242B"
    assert len(main.brand_tokens.SERIES) == 6
    monkeypatch.delitem(sys.modules, "app.main", raising=False)


def test_fallback_tokens_match_brand_package_when_present():
    import pytest
    tokens = pytest.importorskip("mmonfar_brand.tokens")
    from app import _brand_fallback as fb
    assert (fb.CANVAS, fb.CREAM, fb.TEAL, fb.TEAL_BRIGHT) == (
        tokens.CANVAS, tokens.CREAM, tokens.TEAL, tokens.TEAL_BRIGHT)
    assert fb.SERIES == tokens.SERIES
