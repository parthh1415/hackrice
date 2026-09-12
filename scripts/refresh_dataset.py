"""Refetch the holdings matrix from EDGAR and overwrite data/cache/dataset.json.

    PYTHONPATH=src python3 scripts/refresh_dataset.py

The committed dataset.json is one frozen quarter. Run this when a new 13F
quarter lands and you actually want to move to it — then re-record the golden
path (scripts/record_golden.py), because the recordings are of the old numbers
and nothing will tell you they've drifted.

Needs network. Citadel's information table alone is 8MB, so it is not fast.
"""

import sys
import time

sys.path.insert(0, "src")

from firebreak.dataset import CACHE, load_dataset

if __name__ == "__main__":
    started = time.time()
    data = load_dataset(refresh=True)
    print(f"{CACHE} — {data['quarter']}, {len(data['funds'])} managers, "
          f"{len(data['tickers'])} tickers, {time.time() - started:.1f}s")
