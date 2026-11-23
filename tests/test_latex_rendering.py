from pathlib import Path

from engine.mathdocs import BY_PAGE


def test_all_st_latex_equations_use_single_backslash_commands():
    """Raw Python LaTeX strings must contain one slash per command."""
    for page, entries in BY_PAGE.items():
        for kind, equation in entries:
            if kind == "tex":
                assert "\\\\" not in equation, f"Double-escaped LaTeX in {page}: {equation}"


def test_model_library_economic_equations_are_not_double_escaped():
    source = Path(__file__).resolve().parents[1].joinpath("app.py").read_text(encoding="utf-8")
    start = source.index('st.markdown("### Economic equations at a glance")')
    end = source.index('st.warning("The platform\'s economics are', start)
    block = source[start:end]
    assert 'r"\\\\' not in block
    assert "st.latex(" in block
