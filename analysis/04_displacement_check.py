#!/usr/bin/env python3
"""
Displacement check — did the residents the A/B/C analysis calls "displaced"
actually ask for a Cochrane bed?

The placement query establishes that 220 of 317 Town of Cochrane residents were
first placed outside the town. It cannot say whether they wanted to be. That
question needs the waitlist census, which records the sites people rated and
the dates they were on the list.

This script joins the two on PHN and answers three things:

  1. How many displaced Town residents ever rated a Cochrane site.
  2. Whether the request came BEFORE the outside placement (displacement) or
     AFTER it (hindsight — a request to move back, which proves nothing about
     the original placement decision).
  3. How long they were observably on the Cochrane list.

The published figure is (2): 138 of 220 were on the Cochrane list at or before
the moment they were placed elsewhere, median 70 observed days, longest 1,358.
Because the census begins 2021-04-01, 138 is a floor, not a count.

USAGE
    python3 04_displacement_check.py <placement.csv> <waitlist.csv>

  placement.csv  output of sql/02_client_level_detail.sql
  waitlist.csv   output of sql/03_waitlist_rated_sites.sql

Both are read as exported CSV with header row. Nothing is written; the script
prints and exits non-zero if the two files cannot be joined.
"""
import csv, sys, datetime as dt, statistics as st
from collections import defaultdict

WINDOW_OPENS = dt.datetime(2021, 4, 1)   # first waitlist census date

def phn(s):
    """Registry PHNs are 9 digits; exports vary on leading zeros and dashes."""
    d = "".join(c for c in (s or "") if c.isdigit())
    return d.zfill(9) if d else None

def day(s):
    s = (s or "").strip()
    return dt.datetime.strptime(s[:10], "%Y-%m-%d") if s else None

def main(placement_csv, waitlist_csv):
    W = list(csv.DictReader(open(waitlist_csv)))
    P = [r for r in csv.DictReader(open(placement_csv)) if r.get("PATIENT_ID")]

    # every census date on which a person appeared against a Cochrane site
    on_list = defaultdict(list)
    for r in W:
        k = phn(r["PHN"])
        d = day(r["CENSUS_DATE"])
        if k and d:
            on_list[k].append(d)

    # the demand population: one row per person, on their first-ever placement,
    # Level 3 excluded — must match 01_demand_capacity_report.sql exactly
    demand = [r for r in P
              if r["ADMISSION_SEQ"] == "1"
              and r.get("IS_TRUE_FIRST", "1") == "1"
              and phn(r["PHN"])
              and r["CARE_STREAM"] != "Type B - Level 3"]

    town     = [r for r in demand if r["TOWN_3YR"] == "1"]
    placed_in  = [r for r in town if r["PLACED_IN_COCHRANE"] == "1"]
    placed_out = [r for r in town if r["PLACED_IN_COCHRANE"] == "0"]

    if not town:
        sys.exit("no Town of Cochrane residents found — check the column names "
                 "in the placement export")

    print(f"Town of Cochrane demand population : {len(town)}")
    print(f"  placed in Cochrane               : {len(placed_in)}")
    print(f"  placed outside Cochrane          : {len(placed_out)}\n")

    rated = [r for r in placed_out if phn(r["PHN"]) in on_list]
    print(f"Of the {len(placed_out)} placed outside, {len(rated)} ever rated a "
          f"Cochrane site.\n")

    # ── the test that matters: was the request before the placement? ────────
    before = spans = after = 0
    observed = []
    for r in rated:
        adm = day(r["ADMISSION_DATE"])
        ds  = on_list[phn(r["PHN"])]
        if max(ds) < adm:
            before += 1                      # asked, waited, placed elsewhere
        elif min(ds) > adm:
            after += 1                       # asked only after — excluded
            continue
        else:
            spans += 1                       # on the list on the day itself
        observed.append((max(ds) - min(ds)).days + 1)

    evidence = before + spans
    print("Was the Cochrane request before or after the outside placement?")
    print(f"  list period ENDS before the placement : {before:4d}")
    print(f"  list period SPANS the placement date  : {spans:4d}")
    print(f"  list period STARTS after it (excluded): {after:4d}")
    print(f"\n  -> {evidence} of {len(placed_out)} residents placed outside Cochrane were on")
    print( "     the Cochrane list at or before the moment they were placed elsewhere.")

    if observed:
        o = sorted(observed)
        print(f"\n  observed days on the Cochrane list: median {int(st.median(o))}"
              f"  p90 {o[int(len(o)*.9)]}  longest {o[-1]}")

    # ── why the number is a floor ───────────────────────────────────────────
    early = sum(1 for r in placed_out if day(r["ADMISSION_DATE"]) < WINDOW_OPENS
                + dt.timedelta(days=365))
    print(f"\nFLOOR CHECK: {early} of the outside placements happened in the first year")
    print( "  of the census window. Anyone who rated Cochrane before 2021-04-01 and was")
    print(f"  placed early is invisible to this join, so {evidence} is a floor, not a count.")
    print(f"\nWhat cannot be said: whether the remaining {len(placed_out)-evidence} also wanted a")
    print( "  local bed. Their preferences are not recorded in the source available.")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
