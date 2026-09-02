#!/usr/bin/env python3
"""
Validate and tabulate the master demand cohort (output of sql/09, revision 2).

Revision 2 after second review:
  - STOPS on any integrity failure; nothing below the checks is printed.
  - Adds the placement-after-follow-up test that would have caught the leak.
  - D is reported as D1 (still waiting) / D2 (died) / D3 (exited, unknown).
    "No placement observed" is never relabelled as "still waiting".
  - Residency METHOD A (published: any Town address in 3 prior FY) and
    METHOD B (most recent address in the lookback) are both tabulated, with
    the person-level transition matrix between them.
  - Registry missingness reported in its four classes.
  - NULL-source admissions and same-day placement ties reported.
  - People never approved are shown and excluded from A-D.

A clean run of this script is a data-integrity result. It is NOT a
methodological sign-off, and it cannot detect an outcome the source never
recorded (see the zone-coverage warning).

USAGE
    python3 07_master_cohort_check.py master.csv [--published client_level.csv]
"""
import csv, sys, argparse, datetime as dt, statistics as st
from collections import Counter, defaultdict

WIN_START, WIN_END, FOLLOW_UP = dt.date(2021,4,1), dt.date(2026,4,1), dt.date(2026,3,31)

def day(s):
    s = (s or "").strip()
    return dt.datetime.strptime(s[:10], "%Y-%m-%d").date() if s else None
def phn(s):
    d = "".join(c for c in (s or "") if c.isdigit()); return d.zfill(9) if d else None
def pct(a, b): return f"{a/b*100:5.1f}%" if b else "   —  "
def col(r, k, default=""): return (r.get(k) or default).strip()

def load(path):
    rd = csv.DictReader(open(path)); rd.fieldnames = [h.strip().upper() for h in rd.fieldnames]
    rows = list(rd)
    for r in rows:
        r["_phn"]  = phn(r["PHN"]);            r["_dem"] = day(r["DEMAND_DT"])
        r["_pl"]   = day(col(r,"FIRST_PLACEMENT_DT"))
        r["_plaf"] = day(col(r,"FIRST_PLACEMENT_AFTER_FOLLOWUP"))
        r["_dth"]  = day(col(r,"DEATH_DT"));    r["_hist"] = day(col(r,"FIRST_RESIDENTIAL_EVER"))
        r["_lt"]   = col(r,"LEFT_TRUNCATED","0") == "1"
        r["_app"]  = col(r,"WAS_APPROVED","1") == "1"
        r["_coh"]  = col(r,"COHORT") or None
        r["_inc"]  = col(r,"FIRST_PLACEMENT_IN_COCHRANE","0") == "1"
        r["_resA"] = col(r,"RESIDENCY_ANY3");   r["_resB"] = col(r,"RESIDENCY_LATEST")
        r["_dcls"] = col(r,"D_CLASS")
    return rows

# ── 1. integrity — gate ──────────────────────────────────────────────────────
def integrity(rows):
    print("1. INTEGRITY — the script stops if any of these fail")
    n = len(rows)
    checks = [
        ("duplicate PHNs (one row per person)", n - len({r["_phn"] for r in rows})),
        ("placement before demand event",      sum(1 for r in rows if r["_pl"] and r["_pl"] < r["_dem"])),
        ("PLACEMENT AFTER FOLLOW-UP END counted as placed",
                                               sum(1 for r in rows if r["_pl"] and r["_pl"] > FOLLOW_UP)),
        ("first-ever residential admission before window (should be excluded)",
                                               sum(1 for r in rows if r["_hist"] and r["_hist"] < WIN_START)),
        ("demand event outside window",        sum(1 for r in rows if not (WIN_START <= r["_dem"] < WIN_END))),
        ("placed after death date",            sum(1 for r in rows if r["_pl"] and r["_dth"] and r["_pl"] > r["_dth"])),
        ("cohort assigned but never approved", sum(1 for r in rows if r["_coh"] and not r["_app"])),
        ("cohort A/C/D but residency_any3 not Town",
                                               sum(1 for r in rows if r["_coh"] in ("A","C","D") and r["_resA"] != "Town of Cochrane")),
        ("cohort D but has a placement",       sum(1 for r in rows if r["_coh"]=="D" and r["_pl"])),
        ("cohort D with no D class",           sum(1 for r in rows if r["_coh"]=="D" and not r["_dcls"])),
        ("cohort A/B but first placement not in Cochrane",
                                               sum(1 for r in rows if r["_coh"] in ("A","B") and not r["_inc"])),
        ("approved Town resident with no cohort",
                                               sum(1 for r in rows if r["_app"] and r["_resA"]=="Town of Cochrane" and not r["_coh"])),
        ("D1 (still waiting) but not on list at follow-up",
                                               sum(1 for r in rows if r["_dcls"].startswith("D1") and col(r,"ON_LIST_AT_FOLLOWUP","0")!="1")),
    ]
    bad = 0
    for label, c in checks:
        bad += c > 0
        print(f"  {label:66s} {c:7,}  {'ok' if c == 0 else 'FAIL'}")
    print()
    return bad == 0

# ── 2. cohorts, D split ─────────────────────────────────────────────────────
def cohorts(rows):
    print("2. COHORTS — person-level. A/C/D are Town of Cochrane residents (METHOD A residency)")
    c = Counter(r["_coh"] for r in rows if r["_coh"]); res = c["A"]+c["C"]+c["D"]
    print(f"  A  resident, placed in Cochrane          {c['A']:6,}   {pct(c['A'],res)} of resident demand")
    print(f"  C  resident, placed outside              {c['C']:6,}   {pct(c['C'],res)}")
    print(f"  D  resident, no placement in source      {c['D']:6,}   {pct(c['D'],res)}")
    print(f"     resident demand  A + C + D            {res:6,}")
    print(f"  B  non-resident, placed in Cochrane      {c['B']:6,}")
    dc = Counter(r["_dcls"] for r in rows if r["_coh"]=="D")
    print("\n  D by class — different findings, never one word:")
    for k in sorted(dc): print(f"    {k:48s} {dc[k]:6,}   {pct(dc[k],c['D'])} of D")
    na = sum(1 for r in rows if not r["_app"])
    print(f"\n  never approved, excluded from A-D: {na:,}  (on the list, never ready for a bed)")
    l3 = sum(1 for r in rows if r["_coh"]=="D" and col(r,"FIRST_LEVEL3_DT"))
    if l3: print(f"  of D, received a Level 3 bed instead: {l3:,}  (a bed, not the Type A/B bed approved)")
    af = sum(1 for r in rows if r["_coh"]=="D" and r["_plaf"])
    print(f"  of D, placed AFTER follow-up end (sensitivity only): {af:,}")
    print(f"\n  ZONE COVERAGE WARNING: the admissions source carries only CAL- and EDM- care")
    print(f"  types. A resident placed in another zone appears here as D3. D3 is an upper")
    print(f"  bound on unmet demand until sql/10_coverage_checks is run and ALA confirms.\n")

# ── 3. residency: method A vs B ─────────────────────────────────────────────
def residency_methods(rows):
    print("3. RESIDENCY — METHOD A (published: any Town address in 3 prior FY) vs METHOD B (latest address)")
    tr = Counter((r["_resA"], r["_resB"]) for r in rows if r["_app"])
    moved = sum(v for (a,b),v in tr.items() if a != b); tot = sum(tr.values())
    print(f"  people whose verdict differs between methods: {moved:,} of {tot:,}  ({pct(moved,tot).strip()})")
    for (a,b),v in sorted(tr.items(), key=lambda x:-x[1]):
        if a != b: print(f"    A: {a:30s} -> B: {b:30s} {v:6,}")
    # cohort impact
    def coh(r, res):
        if not r["_app"]: return None
        if res=="Town of Cochrane" and r["_inc"]: return "A"
        if res=="Not a Cochrane-area resident" and r["_inc"]: return "B"
        if res=="Town of Cochrane" and r["_pl"]: return "C"
        if res=="Town of Cochrane": return "D"
        return None
    ca = Counter(coh(r, r["_resA"]) for r in rows); cb = Counter(coh(r, r["_resB"]) for r in rows)
    print(f"\n  {'cohort':8s} {'method A':>10} {'method B':>10} {'diff':>7}")
    for k in ("A","B","C","D"): print(f"  {k:8s} {ca[k]:10,} {cb[k]:10,} {cb[k]-ca[k]:+7,}")
    print("  The published rule is not changed here. This is the measured effect of changing it.\n")

# ── 4. missingness ──────────────────────────────────────────────────────────
def missingness(rows):
    print("4. REGISTRY MISSINGNESS — four classes; each is a different fix")
    n = len(rows)
    for k, v in Counter(col(r,"RESIDENCY_MISSING_REASON") for r in rows).most_common():
        d = sum(1 for r in rows if col(r,"RESIDENCY_MISSING_REASON")==k and not r["_pl"] and r["_app"])
        print(f"  {k:44s} {v:6,}  {pct(v,n)}   approved & unplaced {d:5,}")
    cD = sum(1 for r in rows if r["_coh"]=="D")
    un_all = [r for r in rows if r["_resA"]=="UNRESOLVED" and not r["_pl"] and r["_app"]]
    if "RATED_COCHRANE" in rows[0]:
        un = sum(1 for r in un_all if col(r,"RATED_COCHRANE","0")=="1")
        print(f"\n  unresolved, approved, unplaced, WITH a recorded Cochrane request: {un:,}.")
        print(f"  Upper bound on D: {cD+un:,} vs {cD:,}. ({len(un_all)-un:,} further unresolved carry no Cochrane signal")
        print(f"  and are not counted - an extract from a rev < 2.2 query keeps province-wide noise here.)\n")
    else:
        print(f"\n  unresolved, approved, unplaced: {len(un_all):,} - but this extract has no RATED_COCHRANE column,")
        print(f"  so most of these are province-wide people with no Cochrane link. Re-run sql/09 rev 2.2;")
        print(f"  do NOT read {cD+len(un_all):,} as an upper bound on D.\n")

# ── 5. left-truncation, by year ─────────────────────────────────────────────
def truncation_and_year(rows):
    print("5. LEFT-TRUNCATION and FISCAL YEAR")
    for lab, sel in (("all", rows), ("excluding left-truncated", [r for r in rows if not r["_lt"]])):
        c = Counter(r["_coh"] for r in sel if r["_coh"]); res = c["A"]+c["C"]+c["D"]
        print(f"  {lab:28s} A {c['A']:5,}  C {c['C']:5,}  D {c['D']:5,}   D share {pct(c['D'],res)}")
    lt = sum(1 for r in rows if r["_lt"])
    print(f"  flagged left-truncated: {lt:,}. With approval as the demand event, pre-window approvals are")
    print(f"  EXCLUDED rather than flagged, so this flag marks almost nobody. See the reconciliation.")
    print(f"\n   {'FYE':>6} {'A':>6} {'C':>6} {'D1':>6} {'D2':>6} {'D3':>6}   censoring rises to the right")
    for y in sorted({r["DEMAND_FYE"] for r in rows if r["_coh"]}):
        g = [r for r in rows if r["DEMAND_FYE"]==y and r["_coh"]]
        c = Counter(r["_coh"] for r in g); d = Counter(r["_dcls"][:2] for r in g if r["_coh"]=="D")
        print(f"   {y:>6} {c['A']:6,} {c['C']:6,} {d['D1']:6,} {d['D2']:6,} {d['D3']:6,}")
    print()

# ── 6. waits, ties, null sources ────────────────────────────────────────────
def waits_and_quality(rows):
    print("6. DAYS FROM DEMAND EVENT (approval) TO FIRST PLACEMENT — placed only")
    for coh in ("A","B","C"):
        d = sorted(int(col(r,"DAYS_TO_PLACEMENT")) for r in rows if r["_coh"]==coh and col(r,"DAYS_TO_PLACEMENT"))
        if d: print(f"   {coh}  n {len(d):5,}   median {int(st.median(d)):4d}   p90 {d[int(len(d)*.9)]:4d}")
    ties = sum(1 for r in rows if col(r,"N_SAMEDAY_FIRST","0") not in ("","0","1"))
    print(f"\n   same-day placement ties on the first placement day: {ties:,}  (tiebreak: Cochrane first, then site)")
    print( "   NULL source_location admissions are retained by the query (is distinct from); count them in sql/10.\n")

# ── 7. reconciliation ───────────────────────────────────────────────────────
def reconcile(rows, pub_path):
    P = [x for x in csv.DictReader(open(pub_path)) if x["PATIENT_ID"]]
    pub = {}
    for x in P:
        if (x["ADMISSION_SEQ"]=="1" and x["PHN"].strip() and x["FIRST_AB_ADMISSION_DATE"][:10] >= "2021-04-01"
            and x["CARE_STREAM"] != "Type B - Level 3"):
            town, area, inc = x["TOWN_3YR"]=="1", x["AREA_3YR"]=="1", x["PLACED_IN_COCHRANE"]=="1"
            pub[phn(x["PHN"])] = "A" if town and inc else "C" if town else "B" if (inc and not area) else None
    mas = {r["_phn"]: r["_coh"] for r in rows}
    print("7. RECONCILIATION vs published A/B/C (query 02 demand basis). Not expected to match exactly.")
    pc = Counter(v for v in pub.values() if v); mc = Counter(v for v in mas.values() if v)
    for k in ("A","B","C"): print(f"   {k}  published {pc[k]:6,}   master {mc[k]:6,}   {mc[k]-pc[k]:+6,}")
    print(f"   D  published      —   master {mc['D']:6,}")
    tr = Counter((c, mas.get(p,"absent")) for p,c in pub.items() if c)
    print("   published -> master, person by person:")
    for (a,b),v in sorted(tr.items(), key=lambda x:-x[1]):
        print(f"     {a} -> {str(b):8s} {v:6,}{'' if a==b else '   <- explain'}")
    print()

def main(a):
    rows = load(a.master_csv)
    print(f"\n{a.master_csv}\n{len(rows):,} people\n")
    if not integrity(rows):
        sys.exit("INTEGRITY CHECKS FAILED — nothing else is printed. Fix the query first.")
    cohorts(rows); residency_methods(rows); missingness(rows); truncation_and_year(rows); waits_and_quality(rows)
    if a.published: reconcile(rows, a.published)
    print("A clean run is a data-integrity result, not a methodological sign-off.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("master_csv"); ap.add_argument("--published")
    main(ap.parse_args())
