"""The claim the whole demo rests on, checked by making the network explode.

README says "Nothing here touches the internet unless you explicitly ask it
to." That was true, and it was asserted rather than proven — the way it gets
checked in practice is by someone turning off the wifi in a conference room
five minutes before they present.

So: patch out the ability to open a socket at all, then drive every endpoint.
Anything that reaches for the network raises instead of blocking on a DNS
lookup that will not resolve, which is the failure mode that actually eats a
demo — not an exception, a thirty-second hang.
"""

import socket
from unittest import mock

import pytest

from firebreak import api

ROUTES = [
    "/api/health",
    "/api/dataset",
    "/api/break?leverage=5&gamma=0.2&band=1.05&breaches=3",
    "/api/stabilise?leverage=5&gamma=0.2&band=1.05&breaches=3&asset=0",
    "/api/boundary?leverage=5&gamma=0.2&band=1.05",
    "/api/portfolio/demo",
    "/api/cascade?asset=NVDA&magnitude=0.2469140625&leverage=5&gamma=0.2&band=1.05",
]


def _explode(*args, **kwargs):
    raise AssertionError(
        "this code path tried to open a socket. The demo runs on a conference "
        "network that may not exist; every number has to come off disk."
    )


@pytest.fixture
def no_network():
    with mock.patch.object(socket, "socket", _explode), \
         mock.patch.object(socket, "create_connection", _explode), \
         mock.patch.object(socket, "getaddrinfo", _explode):
        yield


@pytest.mark.parametrize("route", ROUTES)
def test_every_endpoint_answers_with_the_network_gone(route, no_network):
    out = api.handle(route, {})
    assert isinstance(out, dict) and out


def test_the_whole_portfolio_loop_answers_with_the_network_gone(no_network):
    """Search, fix and validate — the five screens, in one call."""
    out = api.handle("/api/portfolio/full?limit=0.10", {})

    assert out["found"] is True
    assert out["asset"] == "NVDA"
    assert out["fix"]["dollars"] == pytest.approx(478.2766919706773, rel=1e-9)
    assert out["validation"]["identical_shock"]["after_loss"] < out["params"]["limit"]


def test_an_uploaded_book_is_answered_with_the_network_gone(no_network):
    """The CSV path too — it is the half of the demo that is not pre-recorded."""
    out = api.handle("/api/portfolio/full?limit=0.10", {"holdings": [
        {"symbol": "NVDA", "market_value": 50000},
        {"symbol": "CASH", "market_value": 50000},
    ], "source": "csv"})

    assert out["found"] is True
    assert out["portfolio"]["total_value"] == pytest.approx(100000.0)


def test_the_guard_itself_can_fail(no_network):
    """Otherwise every test above passes because nothing was ever patched."""
    with pytest.raises(AssertionError, match="tried to open a socket"):
        socket.socket()
    with pytest.raises(AssertionError, match="tried to open a socket"):
        socket.getaddrinfo("example.com", 80)
