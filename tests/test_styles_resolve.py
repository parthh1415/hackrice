"""Every CSS variable and class the markup reaches for has to exist.

A `var(--positive)` that nothing defines does not fail, warn, or fall back to
anything visible — it resolves to nothing and the property is dropped, so the
element renders in whatever it inherited. That is the worst possible failure
mode for a stylesheet: silent, and indistinguishable from a deliberate choice.

It had already happened. The terminal recolour renamed the palette and the
markup was never swept, so five values on verify.html, the signed CHANGE column
on defend.html and two of the three provenance labels on assumptions.html were
rendering as plain body text. Defend showed a fixed loss in green while verify,
one click later, showed the same improvement in white — the app disagreeing
with itself about what "better" looks like, with nothing red anywhere to say
so.

`.muted` was worse: twenty-one uses across five pages and no rule behind any of
them, so every piece of secondary text in every table sat at full body weight.
"""

import pathlib
import re

import pytest

WEB = pathlib.Path(__file__).resolve().parents[1] / "web"
PAGES = sorted(WEB.glob("*.html"))
STYLESHEETS = sorted(WEB.glob("*.css"))


def _css():
    return "\n".join(p.read_text() for p in STYLESHEETS)


def _markup():
    return "\n".join(p.read_text() for p in PAGES) + "\n" + (WEB / "shared.js").read_text()


def test_there_are_pages_and_stylesheets_to_check():
    """Guard the guard: globbing nothing would make everything below vacuous."""
    assert len(PAGES) >= 6, f"only found {[p.name for p in PAGES]}"
    assert STYLESHEETS, "no stylesheet found, so the checks below compare nothing"
    assert "var(--" in _markup(), "no CSS variables used in the markup at all?"


def test_every_css_variable_the_markup_uses_is_defined():
    css = _css()
    defined = set(re.findall(r"(--[a-z0-9-]+)\s*:", css))
    used = set(re.findall(r"var\((--[a-z0-9-]+)\)", _markup()))
    # a variable used inside the stylesheet itself must resolve too
    used |= set(re.findall(r"var\((--[a-z0-9-]+)\)", css))

    missing = sorted(used - defined)
    assert not missing, (
        f"the markup reads {missing}, which no stylesheet defines. CSS drops the "
        "property silently, so these elements render in whatever they inherited"
    )


# Classes that are hooks for JavaScript or for attribute selectors rather than
# things with their own rules. Anything not on this list needs a rule.
_BEHAVIOURAL = {"nav-links", "status", "card-title", "sub", "keyhelp"}


def test_every_class_the_markup_uses_has_a_rule():
    css = _css()
    styled = set(re.findall(r"\.([A-Za-z][\w-]*)", css))

    used = set()
    for attr in re.findall(r'class="([^"]*)"', _markup()):
        # skip template-literal interpolations — their value is not knowable here
        if "${" in attr:
            attr = re.sub(r"\$\{[^}]*\}", " ", attr)
        used.update(t for t in attr.split() if re.fullmatch(r"[A-Za-z][\w-]*", t))
    for attr in re.findall(r'className\s*=\s*"([^"]*)"', _markup()):
        used.update(t for t in attr.split() if re.fullmatch(r"[A-Za-z][\w-]*", t))

    missing = sorted(used - styled - _BEHAVIOURAL)
    assert not missing, (
        f"{missing} appear in class attributes with no rule in any stylesheet. "
        "Either add the rule or drop the class — a class that styles nothing "
        "reads, to the next person, as styling that got lost"
    )


@pytest.mark.parametrize("name", ["--positive", "--destructive", "--muted-foreground"])
def test_the_semantic_aliases_still_point_at_the_palette(name):
    """These three are the ones that broke. Keep them pointing somewhere real."""
    css = _css()
    match = re.search(rf"{name}\s*:\s*([^;]+);", css)
    assert match, f"{name} is no longer defined"
    target = match.group(1).strip()
    if target.startswith("var("):
        inner = re.fullmatch(r"var\((--[a-z0-9-]+)\)", target)
        assert inner, f"{name} resolves to {target!r}, which is not a plain alias"
        assert re.search(rf"{inner.group(1)}\s*:", css), (
            f"{name} aliases {inner.group(1)}, which is itself undefined"
        )
