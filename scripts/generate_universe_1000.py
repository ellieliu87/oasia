"""
Generate and validate the 1000-CUSIP simulated universe.

Usage:
    python scripts/generate_universe_1000.py [--save]

    --save   Persist the universe and snapshots to CSV files in data/market_data/.

The script triggers the data-generation logic in data/universe_1000.py,
prints summary statistics, and optionally saves to CSV for inspection.
"""
from __future__ import annotations

import sys
import os
import argparse
from pathlib import Path

# Add project root to path so imports resolve correctly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate 1000-CUSIP MBS universe")
    parser.add_argument("--save", action="store_true",
                        help="Save universe and snapshots to CSV")
    args = parser.parse_args()

    print("=" * 70)
    print("  Oasia — 1000-CUSIP Universe Generator")
    print("=" * 70)

    print("\n[1/4] Building static pool universe …")
    from data.universe_1000 import (
        get_universe_1000,
        get_universe_snapshots,
        screen_universe,
        get_pool_snapshot,
        get_pool_history,
    )

    univ = get_universe_1000()
    print(f"      Total pools   : {len(univ):,}")
    print(f"      Total balance : ${univ['original_balance'].sum() / 1e9:.1f}B")

    print("\n[2/4] Product breakdown:")
    for pt in ["CC30", "CC15", "GN30", "GN15"]:
        sub = univ[univ["product_type"] == pt]
        bal = sub["original_balance"].sum() / 1e9
        print(f"      {pt:<6}  {len(sub):>4} pools  ${bal:>7.1f}B  "
              f"avg coupon {sub['coupon'].mean():.2f}%  "
              f"avg FICO {sub['fico'].mean():.0f}  "
              f"avg LTV {sub['ltv'].mean():.2f}")

    print("\n[3/4] Loading 6-month snapshot history …")
    snaps = get_universe_snapshots()
    print(f"      Snapshot rows : {len(snaps):,}")
    print(f"      Date range    : {snaps['snapshot_date'].min().date()} to "
          f"{snaps['snapshot_date'].max().date()}")
    dates = sorted(snaps["snapshot_date"].unique())
    for dt in dates:
        sub = snaps[snaps["snapshot_date"] == dt]
        print(f"        {dt.date()}  "
              f"avg price={sub['market_price'].mean():.2f}  "
              f"avg CPR={sub['cpr'].mean()*100:.1f}%  "
              f"avg OAS={sub['oas_bps'].mean():.0f}bps  "
              f"avg OAD={sub['oad_years'].mean():.2f}yrs")

    print("\n[4/4] Sample pool detail:")
    sample_id = univ.iloc[0]["pool_id"]
    snap = get_pool_snapshot(sample_id)
    hist = get_pool_history(sample_id)
    print(f"      Pool      : {sample_id}")
    print(f"      CUSIP     : {univ.iloc[0]['cusip']}")
    print(f"      Product   : {univ.iloc[0]['product_type']}")
    print(f"      Coupon    : {univ.iloc[0]['coupon']:.2f}%")
    print(f"      WAC       : {univ.iloc[0]['wac']:.3f}%")
    print(f"      FICO/LTV  : {univ.iloc[0]['fico']} / {univ.iloc[0]['ltv']:.2f}")
    if snap:
        print(f"      Latest snapshot ({snap.get('snapshot_date', '').date() if hasattr(snap.get('snapshot_date', ''), 'date') else snap.get('snapshot_date', '')}): "
              f"price={snap.get('market_price', 0):.3f}  "
              f"OAS={snap.get('oas_bps', 0):.0f}bps  "
              f"OAD={snap.get('oad_years', 0):.2f}yrs  "
              f"CPR={snap.get('cpr', 0)*100:.1f}%")
    print(f"      History rows: {len(hist)}")

    # Screening test
    print("\n[extra] Screening test — CC30 with coupon 6.0-6.5%:")
    results = screen_universe({
        "product_type": ["CC30"],
        "coupon": (6.0, 6.5),
    })
    print(f"        {len(results)} pools found")

    if args.save:
        out_dir = PROJECT_ROOT / "data" / "market_data"
        out_dir.mkdir(parents=True, exist_ok=True)

        univ_path  = out_dir / "universe_1000_pools.csv"
        snaps_path = out_dir / "universe_1000_snapshots.csv"

        univ.to_csv(univ_path, index=False)
        snaps.to_csv(snaps_path, index=False)

        print(f"\n[saved] {univ_path}")
        print(f"[saved] {snaps_path}")

    print("\n" + "=" * 70)
    print("  Done.")
    print("=" * 70)


if __name__ == "__main__":
    main()
