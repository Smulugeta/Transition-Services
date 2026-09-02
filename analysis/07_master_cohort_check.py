#!/usr/bin/env python3
"""
Validate and tabulate the master demand cohort (output of sql/09 or sql/08).

Reads one row per person and produces:
  1. integrity checks that must pass before any figure is read
  2. the A / B / C / D table, with D split by outcome
  3. resident demand A + C + D, with and without the left-truncated
  4. residency resolution — the unresolved rows are the uncertainty around D
  5. D by fiscal year of demand event, with the censoring warning
  6. days from demand event to first placement, by cohort
  7. RECONCILIATION against the published A/B/C client extract (query 02),
     person by person, if that file is supplied

The reconciliation will not match exactly and is not supposed to: the demand
anchor sits earlier than the admission anchor for anyone with a waitlist
record, and residency is read at that earlier date. The script reports the
size and direction of the difference. Do not adjust either side to close it.

USAGE
    python3 07_master_cohort_check.py master.csv [--published client_level.csv]
"""
import csv, sys, argparse, datetime as dt, statistics as st
from collections import Counter, defaultdict

def day(s):
    s = (s or "").strip()
    return dt.datetime.strptime(s[:10], "%Y-%m-%d").date() if s else None

def phn(s):
    d = "".join(c for c in (s or "") if c.isdigit())
    return d.zfill(9) if d else None

def pct(a, b): return f"{a/b*100:5.1f}%" if b else "   —  "

def load(path):
    rows = list(csv.DictReader(open(path)))
    for r in rows:
        r["_phn"]   = phn(r["PHN"])
        r["_dem"]   = day(r["DEMAND_DT"])
        r["_pl"]    = day(r.get("FIRST_PLACEMENT_DT"))
        r["_dth"]   = day(r.get("DEATH_DT"))
        r["_first"] = day(r.get("FIRST_AB_ADM_EVER"))
        r["_lt"]    = r.get("LEFT_TRUNCATED", "0").strip() == "1"
        r["_coh"]   = (r.get("COHORT") or "").strip() or None
    return rows

# ── 1. integrity ────────────────────────────────────────────────────────────
def integrity(rows):
    n = len(rows)
    print("1. INTEGRITY — must all be ok before anything below is read")
    dup = n - len({r["_phn"] for r in rows})
    checks = [
        ("duplicate PHNs (must be 0 — one row per person)", dup, 0),
        ("placement before demand event", sum(1 for r in rows if r["_pl"] and r["_pl"] < r["_dem"]), 0),
        ("first-ever admission before window start (should be excluded)",
            sum(1 for r in rows if r["_first"] and r["_first"] < dt.date(2021,4,1)), 0),
        ("demand event outside window",
            sum(1 for r in rows if not (dt.date(2021,4,1) <= r["_dem"] < dt.date(2026,4,1))), 0),
        ("placed after death date", sum(1 for r in rows if r["_pl"] and r["_dth"] and r["_pl"] > r["_dth"]), 0),
        ("cohort A/C/D but not Town resident",
            sum(1 for r in rows if r["_coh"] in ("A","C","D") and r["RESIDENCY"] != "Town of Cochrane"), 0),
        ("cohort D but has a placement", sum(1 for r in rows if r["_coh"]=="D" and r["_pl"]), 0),
        ("cohort A/B but not placed in Cochrane",
            sum(1 for r in rows if r["_coh"] in ("A","B") and r.get("FIRST_PLACEMENT_IN_COCHRANE","0").strip()!="1"), 0),
        ("Town resident with no cohort (should be impossible)",
            sum(1 for r in rows if r["RESIDENCY"]=="Town of Cochrane" and not r["_coh"]), 0),
    ]
    bad = 0
    for label, c, allowed in checks:
        ok = c <= allowed
        bad += not ok
        print(f"  {label:62s} {c:7,}  {'ok' if ok else 'FAIL'}")
    print("  " + ("all checks pass" if not bad else f"{bad} CHECK(S) FAILED — stop here") + "\n")
    return bad == 0

# ── 2. cohorts ──────────────────────────────────────────────────────────────
def cohorts(rows):
    print("2. COHORTS — person-level, Town of Cochrane residents for A/C/D")
    c = Counter(r["_coh"] for r in rows if r["_coh"])
    res = c["A"] + c["C"] + c["D"]
    print(f"  A  resident, placed in Cochrane        {c['A']:6,}   {pct(c['A'],res)} of resident demand")
    print(f"  C  resident, placed outside            {c['C']:6,}   {pct(c['C'],res)}")
    print(f"  D  resident, no placement observed     {c['D']:6,}   {pct(c['D'],res)}")
    print(f"     resident demand  A + C + D          {res:6,}")
    print(f"  B  non-resident, placed in Cochrane    {c['B']:6,}")
    print(f"     use of Cochrane capacity  A + B     {c['A']+c['B']:6,}   (people; admissions are in query 01)")
    dout = Counter(r["D_OUTCOME"] for r in rows if r["_coh"] == "D")
    print("\n  D split by outcome — these are different findings, keep them apart:")
    for k, v in dout.most_common():
        print(f"    {k:46s} {v:6,}   {pct(v, c['D'])} of D")
    print(f"\n  share of resident demand that was served locally  A/(A+C+D)  {pct(c['A'],res)}")
    print(f"  share of resident demand NOT placed locally   (C+D)/(A+C+D) {pct(c['C']+c['D'],res)}")
    print(f"  compare the published (C)/(A+C) = 69.4%, which had no D.\n")

# ── 3. left-truncation ──────────────────────────────────────────────────────
def truncation(rows):
    print("3. LEFT-TRUNCATION — run everything with and without")
    for lab, sel in (("all", rows), ("excluding left-truncated", [r for r in rows if not r["_lt"]])):
        c = Counter(r["_coh"] for r in sel if r["_coh"])
        res = c["A"]+c["C"]+c["D"]
        print(f"  {lab:28s} A {c['A']:5,}  C {c['C']:5,}  D {c['D']:5,}   D share {pct(c['D'],res)}")
    lt = sum(1 for r in rows if r["_lt"])
    print(f"  left-truncated people in this extract: {lt:,}. Their demand event is artificially")
    print(f"  the first census day; days_to_placement understates their wait.\n")

# ── 4. residency resolution ─────────────────────────────────────────────────
def residency(rows):
    print("4. RESIDENCY — the UNRESOLVED rows are the uncertainty around D, not zero")
    n = len(rows)
    for k, v in Counter(r["RESIDENCY"] for r in rows).most_common():
        d = sum(1 for r in rows if r["RESIDENCY"]==k and not r["_pl"])
        print(f"  {k:46s} {v:6,}  {pct(v,n)}   of whom unplaced {d:5,}")
    unres = [r for r in rows if r["RESIDENCY"].startswith("UNRESOLVED") and not r["_pl"]]
    cD = sum(1 for r in rows if r["_coh"]=="D")
    print(f"\n  unresolved AND unplaced: {len(unres):,}. If every one were a Town resident, D would be")
    print(f"  {cD + len(unres):,} instead of {cD:,}. That is the honest upper bound; report the range.")
    conf = Counter(r["CONFIDENCE"] for r in rows if r["RESIDENCY"]=="Town of Cochrane")
    tot = sum(conf.values())
    print(f"  Town verdicts by registry depth: " +
          "  ".join(f"{k} {pct(v,tot).strip()}" for k, v in sorted(conf.items())) + "\n")

# ── 5. D by fiscal year ─────────────────────────────────────────────────────
def by_year(rows):
    print("5. RESIDENT DEMAND BY FISCAL YEAR OF DEMAND EVENT")
    print("   Censoring rises to the right: a FY2026 demand event has had less time to be placed.")
    yrs = sorted({r["DEMAND_FYE"] for r in rows if r["_coh"] in ("A","C","D")})
    print(f"   {'FYE':>6} {'A':>6} {'C':>6} {'D':>6}   {'D share':>8}   {'still waiting':>13}")
    for y in yrs:
        g = [r for r in rows if r["DEMAND_FYE"]==y and r["_coh"] in ("A","C","D")]
        c = Counter(r["_coh"] for r in g)
        sw = sum(1 for r in g if r["_coh"]=="D" and r["D_OUTCOME"].startswith("no placement"))
        print(f"   {y:>6} {c['A']:6,} {c['C']:6,} {c['D']:6,}   {pct(c['D'],len(g)):>8}   {sw:13,}")
    print()

# ── 6. days to placement ────────────────────────────────────────────────────
def waits(rows):
    print("6. DAYS FROM DEMAND EVENT TO FIRST PLACEMENT — placed people only")
    print("   The denominator for 'how many waited' is section 2, never this table.")
    for coh in ("A","B","C"):
        d = sorted(int(r["DAYS_TO_PLACEMENT"]) for r in rows if r["_coh"]==coh and r["DAYS_TO_PLACEMENT"].strip())
        if d:
            print(f"   {coh}  n {len(d):5,}   median {int(st.median(d)):4d}   p90 {d[int(len(d)*.9)]:4d}")
    print("   Not comparable to the published wait (approval -> admission); this clock starts")
    print("   at the demand event, which is earlier.\n")

# ── 7. reconciliation ───────────────────────────────────────────────────────
def reconcile(rows, pub_path):
    P = [x for x in csv.DictReader(open(pub_path)) if x["PATIENT_ID"]]
    # the published basis: first-ever placement in window, Level 3 excluded
    pub = {}
    for x in P:
        if (x["ADMISSION_SEQ"]=="1" and x["PHN"].strip()
            and x["FIRST_AB_ADMISSION_DATE"][:10] >= "2021-04-01"
            and x["CARE_STREAM"] != "Type B - Level 3"):
            town, area, inc = x["TOWN_3YR"]=="1", x["AREA_3YR"]=="1", x["PLACED_IN_COCHRANE"]=="1"
            coh = "A" if town and inc else "C" if town else "B" if (inc and not area) else None
            pub[phn(x["PHN"])] = coh
    mas = {r["_phn"]: r["_coh"] for r in rows}
    print("7. RECONCILIATION against the published A/B/C (query 02 basis)")
    print("   Expected NOT to match exactly. Report the difference; do not adjust either side.")
    print("   A and C are on the published demand basis (first-ever placement in window).")
    print("   B here is the same basis; the published 189 is a CAPACITY count over every")
    print("   in-window admission and is not the comparator for this row.")
    pc = Counter(v for v in pub.values() if v); mc = Counter(v for v in mas.values() if v)
    print(f"   {'':12s} {'published':>10} {'master':>10} {'diff':>7}")
    for k in ("A","B","C"):
        print(f"   {k:12s} {pc[k]:10,} {mc[k]:10,} {mc[k]-pc[k]:+7,}")
    print(f"   {'D':12s} {'—':>10} {mc['D']:10,}")
    # person-level transitions
    tr = Counter()
    for p, c in pub.items():
        if c: tr[(c, mas.get(p, "absent"))] += 1
    print("\n   where each published person landed in the master cohort:")
    for (a, b), v in sorted(tr.items(), key=lambda x: (-x[1])):
        flag = "" if a == b else "   <- explain"
        print(f"     published {a}  ->  master {str(b):8s} {v:6,}{flag}")
    absent = sum(v for (a,b),v in tr.items() if b=="absent")
    if absent:
        print(f"\n   {absent:,} published people are absent from the master extract. Likely causes:")
        print( "   PHN normalisation differs, or they fall in the dropped cell (non-resident,")
        print( "   not placed in Cochrane) under the earlier anchor. Each needs a reason.")
    print()

def main(a):
    rows = load(a.master_csv)
    print(f"\n{a.master_csv}\n{len(rows):,} people in the demand cohort\n")
    ok = integrity(rows)
    cohorts(rows); truncation(rows); residency(rows); by_year(rows); waits(rows)
    if a.published: reconcile(rows, a.published)
    if not ok: sys.exit("integrity checks failed")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("master_csv")
    ap.add_argument("--published", help="query 02 client-level CSV, for reconciliation")
    main(ap.parse_args())
