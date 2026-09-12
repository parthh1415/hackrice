"""Every control a shooting script tells you to click has to exist.

`docs/video-script-3min.md` opens with "This is what you read aloud", and eight
of its ten shots named a button that had been renamed or deleted — Try demo
portfolio, Continue, Find my Firebreak, Watch why, Find a fix, Validate
recommendation, a Historical tab, a Risk Desk mode. The narration was fine. The
directions were for a different app.

It also said the demo book was "fifteen thousand dollars", spoken aloud, for a
portfolio that has always been $12,300.

Proof-reading is what let that happen, so this checks it instead: every label a
script puts in bold as something to click is matched against the text of an
actual control in web/.
"""

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
SCRIPT = ROOT / "docs" / "video-script-3min.md"

# Things a presenter is told to press that are not <button> text: keys, and
# section numbers on a page that is one long scroll.
_NOT_A_BUTTON = {
    "space", "6", "10%", "5%", "15%", "25%", "1", "2", "3", "4", "5",
    "esc", "?",
}


def _controls():
    """Every clickable label the six pages render, including ones built in JS."""
    labels = set()
    for page in sorted(WEB.glob("*.html")):
        text = page.read_text()
        # markup: <button ...>Label</button>, <a class="btn" ...>Label</a>, <label class="btn">
        for tag in ("button", "a", "label"):
            for m in re.finditer(rf"<{tag}\b[^>]*>(.*?)</{tag}>", text, re.S):
                inner = re.sub(r"<[^>]+>", " ", m.group(1))
                inner = re.sub(r"\$\{[^}]*\}", "", inner)
                label = " ".join(inner.split())
                if label:
                    labels.add(label.lower())
        # strings assigned as button text in JS, e.g. playBtn.textContent = "Pause"
        for m in re.finditer(r'textContent\s*=\s*"([^"]{2,40})"', text):
            labels.add(m.group(1).strip().lower())
    for m in re.finditer(r'textContent\s*=\s*"([^"]{2,40})"', (WEB / "shared.js").read_text()):
        labels.add(m.group(1).strip().lower())
    return labels


def _directed_clicks():
    """Bold labels on a shot line — what the script tells you to press."""
    wanted = []
    for line in SCRIPT.read_text().splitlines():
        if not line.lstrip().startswith("**Shot"):
            continue
        for label in re.findall(r"\*\*(.+?)\*\*", line):
            label = label.strip()
            if label.lower().startswith("shot"):
                continue
            wanted.append(label)
    return wanted


def test_the_script_directs_clicks_at_all():
    """Guard the guard: a parser that matched nothing would pass everything."""
    assert len(_directed_clicks()) >= 8, _directed_clicks()
    assert len(_controls()) >= 10, sorted(_controls())


@pytest.mark.parametrize("label", _directed_clicks())
def test_every_button_the_script_names_exists_in_the_app(label):
    if label.lower() in _NOT_A_BUTTON:
        pytest.skip(f"{label!r} is a key or a section, not a control")
    controls = _controls()
    assert any(label.lower() == c or label.lower() in c for c in controls), (
        f"the script says to click {label!r} and no control in web/ has that "
        f"text. Closest things it does have: "
        f"{sorted(c for c in controls if c and c[0] == label.lower()[0])[:6]}"
    )


def test_the_script_does_not_speak_a_portfolio_total_the_app_does_not_show():
    """It said "fifteen thousand dollars" for a $12,300 book, out loud."""
    from firebreak import api

    total = api.handle("/api/portfolio/demo", {})["portfolio"]["total_value"]
    text = SCRIPT.read_text().lower()

    assert "fifteen thousand" not in text, f"the demo book is ${total:,.0f}"
    # and the figure it does speak has to be the real one
    spoken = "twelve thousand three hundred"
    assert total == pytest.approx(12300.0), (
        f"the demo book is now ${total:,.0f}; the script says {spoken!r} aloud"
    )
    assert spoken in text
