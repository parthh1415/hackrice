"""JSON endpoints. Thin — all the thinking happens in engine/search."""

import urllib.parse


class NotFound(Exception):
    pass


def handle(path, body):
    route, _, query = path.partition("?")
    params = dict(urllib.parse.parse_qsl(query))

    if route == "/api/health":
        return {"ok": True}

    raise NotFound(route)
