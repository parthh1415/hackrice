#!/usr/bin/env python3
"""Freeze the demo path to disk so it can be served with no engine at all.

Run it whenever the dataset or the engine changes, and once more right
before the demo:

    PYTHONPATH=src python3 scripts/record_golden.py

Everything it writes lands in data/cache/golden/ and comes back out via
?demo=1, or automatically if a live solve throws.
"""

import sys

from minima import api


def main():
    written = api.record_golden()

    print(f"recorded {len(written)} responses -> {api.GOLDEN}")
    for path in written:
        size = path.stat().st_size
        print(f"  {path.name:<52} {size / 1024:7.1f} KB")

    # a recording of a scenario that doesn't break is useless on stage: the
    # frontend renders the "nothing broke" branch and the demo is over.
    empty = []
    for path in written:
        import json

        payload = json.loads(path.read_text())
        if payload.get("found") is False:
            empty.append(path.name)
    if empty:
        print("\nwarning: these recorded a no-break result:", ", ".join(empty))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
