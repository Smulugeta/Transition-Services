#!/usr/bin/env python3
"""
Cohort D — what happened to people who were on the waitlist.

Reads the output of sql/05_waitlist_spells.sql and reproduces the exit
classification, the integrity checks, and the two sensitivity analyses that
have to accompany any death-related figure from this source.

It also runs the classification independently of the SQL, so the two are a
cross-check on each other rather than one restating the other.

THE THREE THINGS THIS EXISTS TO STOP
  1. Reading "has a death date" as "died waiting". Most people with a death
     date were placed first and died in care, which is what long-term care is.
  2. Quoting a died-waiting figure without the window that produced it. The
     number moves ~58% between a 7-day and a 180-day reading.
  3. Counting a re-registration as an exit. Many apparent disappearances
     continue under a new patient_transfer_id within days.

USAGE
    python3 06_exit_classification.py <spells.csv> [--window 30] [--rereg 90]
"""
import csv, sys, argparse, datetime as dt
from collections import Counter, defaultdict

def day(s):
    s = (s or "").strip()
    return dt.datetime.strptime(s[:10], "%Y-%m-%d").date() if s else None

def load(path):
    rows = list(csv.DictReader(open(path)))
    for r in rows:
        r["_entry"] = day(r.get("LIST_ENTRY"))
        r["_last"]  = day(r.get("LIST_LAST_SEEN"))
        r["_adm"]   = day(r.get("ADMISSION_DATE"))
        # the column is DETHDATE straight from vital stats, DEATH_DATE once
        # query 05 has aliased it
        r["_death"] = day(r.get("DEATH_DATE") or r.get("DETHDATE"))
        r["_wait"]  = r.get("STILL_WAITING", "0").strip() == "1"
    return rows

def bar(n, total, width=34):
    return "#" * max(1, round(n / total * width)) if n else ""

def integrity(rows):
    """Anomalies that mean the vital-stats join is matching the wrong person."""
    print("INTEGRITY — the vital-stats join")
    checks = [
        ("death date precedes list entry",
         sum(1 for r in rows if r["_death"] and r["_entry"] and r["_death"] < r["_entry"])),
        ("still censused after the death date",
         sum(1 for r in rows if r["_death"] and r["_last"] and r["_death"] < r["_last"])),
        ("admitted after the death date",
         sum(1 for r in rows if r["_death"] and r["_adm"] and r["_adm"] > r["_death"])),
        ("negative days to placement",
         sum(1 for r in rows if r["_adm"] and r["_entry"] and r["_adm"] < r["_entry"])),
    ]
    n = len(rows)
    for label, c in checks:
        flag = "ok" if c / n < 0.001 else "INVESTIGATE"
        print(f"  {label:38s} {c:7,}  ({c/n*100:.3f}%)  {flag}")
    print("  Each is impossible in reality. A few are stale records; a lot means")
    print("  the join key is wrong and nothing below can be trusted.\n")

def reregistered(rows, window):
    """A later spell for the same person starting within `window` days."""
    byp = defaultdict(list)
    for r in rows:
        byp[r["PATIENT_ID"]].append(r)
    for v in byp.values():
        v.sort(key=lambda x: (x["_entry"] or dt.date.min))
    out = {}
    for pid, spells in byp.items():
        for i, r in enumerate(spells):
            hit = None
            for o in spells[i+1:]:
                if o["_entry"] and r["_last"] and 0 <= (o["_entry"] - r["_last"]).days <= window:
                    hit = o
                    break
            out[id(r)] = hit
    return out

def classify(r, window, rereg):
    if r["_wait"]:                                    return "STILL WAITING (censored)"
    if r["_adm"]:
        if r["_death"] and r["_death"] < r["_adm"]:   return "ANOMALY - admitted after death"
        if r["_death"]:                               return "PLACED, died later in care"
        return "PLACED"
    if r["_death"]:
        if r["_entry"] and r["_death"] < r["_entry"]: return "ANOMALY - death precedes entry"
        gap = (r["_death"] - r["_last"]).days
        if gap <= window:                             return "DIED WAITING"
        return "left list, died later"
    if rereg is not None:
        same = rereg["PATIENT_TRANSFER_ID"] == r["PATIENT_TRANSFER_ID"]
        return "returned to the list later" if same else "RE-REGISTERED under a new transfer"
    return "LEFT LIST - outcome unknown"

def main(path, window, rereg_days):
    rows = load(path)
    n = len(rows)
    people = len({r["PATIENT_ID"] for r in rows})
    print(f"\n{path}")
    print(f"spells {n:,}   people {people:,}   "
          f"transfers {len({(r['PATIENT_ID'], r['PATIENT_TRANSFER_ID']) for r in rows}):,}\n")

    integrity(rows)

    rr = reregistered(rows, rereg_days)
    counts = Counter(classify(r, window, rr[id(r)]) for r in rows)

    print(f"EXIT CLASSIFICATION   (died-waiting window {window}d, "
          f"re-registration window {rereg_days}d)")
    for k, v in counts.most_common():
        print(f"  {k:36s} {v:7,}  {v/n*100:5.1f}%  {bar(v, n)}")

    # ── the misreading this exists to prevent ───────────────────────────────
    anyd = sum(1 for r in rows if r["_death"])
    dw   = counts["DIED WAITING"]
    print(f"\nWHY 'HAS A DEATH DATE' IS NOT 'DIED WAITING'")
    print(f"  spells carrying any death date      {anyd:7,}  ({anyd/n*100:.1f}%)")
    print(f"  of those, died without a placement  {dw:7,}  ({dw/anyd*100:.1f}% of them)")
    print(f"  quoting the first as the second overstates it by {anyd/max(dw,1):.1f}x")

    # ── sensitivity: the window is a judgement call, so show its range ───────
    print(f"\nSENSITIVITY — 'died waiting' by choice of window")
    unpl = [r for r in rows if not r["_wait"] and not r["_adm"] and r["_death"]]
    for w in (7, 14, 30, 60, 90, 180):
        c = sum(1 for r in unpl if (r["_death"] - r["_last"]).days <= w)
        mark = "  <- reported" if w == window else ""
        print(f"  within {w:3d} days  {c:7,}  ({c/n*100:4.1f}% of spells){mark}")
    lo = sum(1 for r in unpl if (r["_death"] - r["_last"]).days <= 7)
    hi = sum(1 for r in unpl if (r["_death"] - r["_last"]).days <= 180)
    print(f"  spread across the range: {(hi-lo)/max(lo,1)*100:.0f}%. State the window "
          f"in the same sentence as the number.")

    # ── hospice / palliative confound ───────────────────────────────────────
    stream = "CARE_STREAM" if "CARE_STREAM" in rows[0] else None
    print(f"\nHOSPICE / PALLIATIVE — expected deaths inflate any death figure")
    if stream:
        for s in sorted({r[stream] for r in rows}):
            g = [r for r in rows if r[stream] == s]
            d = sum(1 for r in g if r["_death"])
            print(f"  {s:24s} spells {len(g):7,}   with a death date {d/len(g)*100:5.1f}%")
        print("  Report Type A/B separately. A hospice client dying while waiting is")
        print("  not the same finding as an LTC client dying while waiting.")
    else:
        hp = [r for r in rows
              if "HOSPICE" in (r.get("LOCATION_AT_ENTRY") or "").upper()
              or "PALLIAT" in (r.get("LOCATION_AT_ENTRY") or "").upper()]
        d = sum(1 for r in hp if r["_death"])
        print(f"  entered the list from a hospice/palliative setting: {len(hp):,}")
        print(f"    with a death date: {d:,} ({d/max(len(hp),1)*100:.0f}%) "
              f"vs {anyd/n*100:.1f}% overall")
        print("  CARE_STREAM is not in this extract — add it in query 05 and re-run,")
        print("  because entry setting is a weak proxy for care type.")

    # ── readiness ───────────────────────────────────────────────────────────
    if "WAS_APPROVED" in rows[0]:
        never = [r for r in rows if not r["_adm"] and not r["_wait"]]
        ap = sum(1 for r in never if r["WAS_APPROVED"].strip() == "1")
        print(f"\nREADINESS — of {len(never):,} who left without a placement, "
              f"{ap:,} ({ap/max(len(never),1)*100:.0f}%) had been")
        print( "  assessed and approved. The rest were still in process and were never")
        print( "  actually waiting for a bed; they do not belong in cohort D.")
    print()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("spells_csv")
    ap.add_argument("--window", type=int, default=30,
                    help="days after last census within which a death counts as "
                         "died-waiting (default 30)")
    ap.add_argument("--rereg", type=int, default=90,
                    help="days within which a later spell counts as a "
                         "re-registration (default 90)")
    a = ap.parse_args()
    main(a.spells_csv, a.window, a.rereg)
