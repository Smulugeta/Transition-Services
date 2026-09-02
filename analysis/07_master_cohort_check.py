#!/usr/bin/env python3
"""
Validate and tabulate the master demand cohort (output of sql/09, rev 2.3).

Revision 6 (seven sign-off gates):
  G1 approval-precedence sensitivity: people whose demand date changes,
     crossing a fiscal year, entering/leaving the window, changing residency,
     and the exact A/B/C/D impact (from the …_ALT columns of sql/09 rev 2.6).
  G2 addresses active on the demand date: how many people had more than one,
     whether they disagree on class, whether the tiebreak changes a cohort.
  G3 the Surrey proof case printed from the extract.
  G4 facility audit: concurrent-occupancy distribution, every blocked address
     with 3-5 people, and how many of the remaining unresolved are blocked by
     the guard alone.
  Remaining unresolved, approved, unplaced clients listed (PHN masked).
  Final validation table: registry-only / registry+Strata / approval-precedence.
  Cohorts are gated on IN_WINDOW where the extract carries it (rev 2.6 admits
  alt-anchor-only people to the universe).

Revision 5 (Strata address history as a secondary residency source):
  - Cohorts recomputed on RESIDENCY_FINAL (registry, else Strata address
    active at demand); COHORT_REGISTRY_ONLY kept so Strata's effect is shown.
  - Rule-10 report: previously unresolved people resolved by Strata, their
    Town / catchment / non-Town split, the unplaced subset, the change to
    A/B/C/D, and the remaining unresolved.
  - Integrity: Strata used only where the registry was unresolved; no Strata
    address effective after the demand date; facility addresses never
    classified; cohort consistent with residency_final.
  - Facility-guard, creation-date and out-of-province counts reported.

Revision 4 after fourth review:
  - Hard checks: placeholder / malformed PHN inside A-D = 0; death before
    demand inside A-D = 0. Both are also counted across the universe.
  - Cohort B = any NON-TOWN resident placed in Cochrane. Catchment residents
    are B (sub-counted); unresolved-residency Cochrane placements are their
    own category.
  - The residency fallback is reported as HISTORICAL EVIDENCE ONLY. The
    maximum on D is primary D plus every valid unresolved approved-unplaced
    person; fallback does not reduce it.
  - registry_history_depth replaces confidence; residency_evidence reported.

Revision 3 after third review:
  - PRIMARY residency = latest mapped address in the lookback (RESIDENCY_LATEST).
    The published any-address-in-three-years rule is the SENSITIVITY.
  - Cohorts are RECOMPUTED here from residency x placement x location and
    compared against the SQL's COHORT column; a mismatch is an integrity fail.
  - The published->master reconciliation is a full TRANSITION MATRIX with row
    and column totals. Nothing is summarised by hand.
  - Residency uncertainty has NO request-based gate. It is reported in tiers:
    D on the primary rule; + unresolved people the FALLBACK address resolves to
    Town; + truly unresolved (mathematical maximum). The share of known Town
    demand that ever recorded a Cochrane request is printed alongside, as the
    reason a request gate is wrong.
  - Already-in-care is tested against the demand event, not the window start.
  - Runs on the full audit universe; COCHRANE_FACING is reported, never used
    as a filter.

A clean run is a data-integrity result. It is NOT a methodological sign-off.

USAGE
    python3 07_master_cohort_check.py master.csv [--published client_level.csv]
"""
import csv, sys, argparse, datetime as dt, statistics as st
from collections import Counter, defaultdict

WIN_START, WIN_END, FOLLOW_UP = dt.date(2021,4,1), dt.date(2026,4,1), dt.date(2026,3,31)
TOWN, AREA, NOT, UNRES = "Town of Cochrane", "Cochrane catchment", "Not a Cochrane-area resident", "UNRESOLVED"

def day(s):
    s = (s or "").strip(); return dt.datetime.strptime(s[:10], "%Y-%m-%d").date() if s else None
def phn(s):
    d = "".join(c for c in (s or "") if c.isdigit()); return d.zfill(9) if d else None
def pct(a, b): return f"{a/b*100:5.1f}%" if b else "   —  "
def col(r, k, default=""): return (r.get(k) or default).strip()

def cohort_of(r, res, b_rule="nontown", pl=None, inc=None, inw=None):
    """The one rule, applied to whichever residency verdict is passed in.
    b_rule 'nontown' (rev 2.4+): B = Not-Cochrane-area OR catchment, placed in Cochrane.
    b_rule 'nonarea'  (rev <=2.3): B = Not-Cochrane-area only.
    pl / inc / inw default to the primary anchor's placement, location and window flag."""
    pl  = r["_pl"]  if pl  is None else pl
    inc = r["_inc"] if inc is None else inc
    inw = r["_inw"] if inw is None else inw
    if not inw or not r["_app"] or not r["_valid"]: return None
    if res == TOWN and inc:           return "A"
    if inc and (res == NOT or (b_rule == "nontown" and res == AREA)): return "B"
    if res == TOWN and pl:            return "C"
    if res == TOWN:                   return "D"
    return None

def load(path):
    rd = csv.DictReader(open(path)); rd.fieldnames = [h.strip().upper() for h in rd.fieldnames]
    rows = list(rd)
    for r in rows:
        r["_phn"]  = phn(r["PHN"]);            r["_dem"]  = day(r["DEMAND_DT"])
        r["_pl"]   = day(col(r,"FIRST_PLACEMENT_DT")); r["_plaf"] = day(col(r,"FIRST_PLACEMENT_AFTER_FOLLOWUP"))
        r["_dth"]  = day(col(r,"DEATH_DT"));    r["_hist"] = day(col(r,"FIRST_RESIDENTIAL_EVER"))
        r["_lt"]   = col(r,"LEFT_TRUNCATED","0") == "1"
        r["_app"]  = col(r,"WAS_APPROVED","1") == "1"
        r["_inc"]  = col(r,"FIRST_PLACEMENT_IN_COCHRANE","0") == "1"
        r["_resA"] = col(r,"RESIDENCY_ANY3");  r["_resL"] = col(r,"RESIDENCY_LATEST")
        r["_resFin"] = col(r,"RESIDENCY_FINAL") or r["_resL"]      # rev 2.5: registry, else Strata
        r["_src"]  = col(r,"RESIDENCY_SOURCE") or ("REGISTRY" if r["_resL"] != UNRES else "UNRESOLVED")
        r["_strat"] = col(r,"STRATA_RESIDENCY") or None
        r["_seff"]  = day(col(r,"STRATA_EFFECTIVE_FROM"))
        r["_inw"]   = col(r,"IN_WINDOW","1") == "1"
        r["_inwA"]  = col(r,"IN_WINDOW_ALT","") == "1"
        r["_demA"]  = day(col(r,"DEMAND_DT_ALT"))
        r["_resFinA"] = col(r,"RESIDENCY_FINAL_ALT") or None
        r["_plA"]   = day(col(r,"FIRST_PLACEMENT_DT_ALT"))
        r["_incA"]  = col(r,"FIRST_PLACEMENT_IN_COCHRANE_ALT","0") == "1"
        r["_sqlcohA"] = col(r,"COHORT_ALT") or None
        r["_resF"] = col(r,"RESIDENCY_FALLBACK") or None
        r["_dcls"] = col(r,"D_CLASS")
        r["_sqlcoh"] = col(r,"COHORT") or None
        r["_badphn"] = (not r["_phn"]) or set(r["_phn"]) == {"0"} or len(col(r,"PHN")) != 9 or not col(r,"PHN").isdigit()
        r["_dbd"]  = bool(r["_dth"] and r["_dem"] and r["_dth"] < r["_dem"])
        r["_valid"] = col(r,"RECORD_VALID","1") == "1" and not r["_dbd"] and not r["_badphn"]
        r["_req"]  = col(r,"RATED_COCHRANE","0") == "1"
        r["_depth"] = col(r,"REGISTRY_HISTORY_DEPTH") or col(r,"CONFIDENCE")
        r["_evid"]  = col(r,"RESIDENCY_EVIDENCE")
    for r in rows:
        r["_coh"]  = cohort_of(r, r["_resFin"])        # PRIMARY, recomputed on residency_final, B = non-Town
        r["_cohR"] = cohort_of(r, r["_resL"])          # registry only
        r["_cohA"] = cohort_of(r, r["_resA"])          # SENSITIVITY, recomputed
        r["_cohAlt"] = (cohort_of(r, r["_resFinA"], pl=r["_plA"], inc=r["_incA"], inw=r["_inwA"])
                        if r["_resFinA"] else None)     # G1: approval-precedence anchor
    return rows

# ── 1. integrity — gate ──────────────────────────────────────────────────────
def integrity(rows):
    print("1. INTEGRITY — the script stops if any of these fail")
    n = len(rows)
    has_any3 = "COHORT_ANY3" in rows[0]; has_b24 = "B_CATCHMENT" in rows[0]; has_25 = "RESIDENCY_FINAL" in rows[0]
    # which rule did the SQL use for COHORT?  rev>=2.5: residency_final + non-Town B;
    # rev 2.4: latest + non-Town B; rev 2.3: latest + non-area B; earlier: any3 + non-area B
    if has_25:    expect = lambda r: r["_coh"]
    elif has_b24: expect = lambda r: r["_cohR"]
    elif has_any3: expect = lambda r: cohort_of(r, r["_resL"], "nonarea")
    else:          expect = lambda r: cohort_of(r, r["_resA"], "nonarea")
    sql_rule = "rev2.5 rule" if has_25 else "rev2.4 rule" if has_b24 else "rev2.3 rule" if has_any3 else "rev<=2.2 rule"
    mismatch = sum(1 for r in rows if (r["_sqlcoh"] or None) != (expect(r) or None))
    checks = [
        ("duplicate PHNs (one row per person)", n - len({r["_phn"] for r in rows})),
        ("placeholder or malformed PHN inside A-D", sum(1 for r in rows if r["_badphn"] and r["_coh"])),
        ("death date before demand event inside A-D", sum(1 for r in rows if r["_dbd"] and r["_coh"])),
        ("placement before demand event",      sum(1 for r in rows if r["_pl"] and r["_pl"] < r["_dem"])),
        ("placement after follow-up end counted as placed", sum(1 for r in rows if r["_pl"] and r["_pl"] > FOLLOW_UP)),
        ("first residential admission BEFORE the demand event (already in care)",
                                               sum(1 for r in rows if r["_hist"] and r["_hist"] < r["_dem"])),
        ("demand event outside window",        sum(1 for r in rows if not (WIN_START <= r["_dem"] < WIN_END))),
        ("placed after death date",            sum(1 for r in rows if r["_pl"] and r["_dth"] and r["_pl"] > r["_dth"])),
        (f"SQL COHORT disagrees with recomputed cohort ({sql_rule} rule)", mismatch),
        ("cohort assigned but never approved", sum(1 for r in rows if r["_coh"] and not r["_app"])),
        ("cohort D but has a placement",       sum(1 for r in rows if r["_coh"]=="D" and r["_pl"])),
        ("cohort D with no D class",           sum(1 for r in rows if r["_coh"]=="D" and not r["_dcls"])),
        ("cohort A/B but first placement not in Cochrane", sum(1 for r in rows if r["_coh"] in ("A","B") and not r["_inc"])),
        ("D1 (still waiting) but not on list at follow-up",
                                               sum(1 for r in rows if r["_dcls"].startswith("D1") and col(r,"ON_LIST_AT_FOLLOWUP","0")!="1")),
        ("Strata used where the registry had a verdict (rule 1)",
                                               sum(1 for r in rows if r["_src"]=="STRATA_ADDRESS_H" and r["_resL"]!=UNRES)),
        ("Strata address effective AFTER the demand date used (rule 8)",
                                               sum(1 for r in rows if r["_src"]=="STRATA_ADDRESS_H" and r["_seff"] and r["_seff"] > r["_dem"])),
        ("facility address used to classify residency",
                                               sum(1 for r in rows if r["_src"]=="STRATA_ADDRESS_H" and col(r,"STRATA_ADDRESS_IS_FACILITY","0")=="1")),
        ("residency_final not in {registry verdict, strata verdict, UNRESOLVED}",
                                               sum(1 for r in rows if has_25 and r["_resFin"] not in (r["_resL"], r["_strat"] or "", UNRES))),
        ("SQL COHORT_ALT disagrees with recomputed alt cohort (G1)",
                                               sum(1 for r in rows if "COHORT_ALT" in rows[0] and (r["_sqlcohA"] or None) != (r["_cohAlt"] or None))),
        ("cohort assigned to a person outside the window (G1 gating)",
                                               sum(1 for r in rows if r["_coh"] and not r["_inw"])),
    ]
    bad = 0
    for label, c in checks:
        bad += c > 0; print(f"  {label:70s} {c:7,}  {'ok' if c == 0 else 'FAIL'}")
    bp = sum(1 for r in rows if r["_badphn"]); bd = sum(1 for r in rows if r["_dbd"])
    print(f"  across the whole universe: placeholder/malformed PHN {bp:,}; death before demand {bd:,}  (rev 2.4 rejects/flags these)")
    if not has_b24:
        print("  note: extract predates rev 2.4; primary cohorts below are recomputed with B = non-Town.")
        if not has_any3: print("        (also predates rev 2.3: no fallback residency column)")
    print(); return bad == 0

# ── 2. cohorts ──────────────────────────────────────────────────────────────
def cohorts(rows):
    print("2. COHORTS — NEW TYPE A/B DEMAND ARISING FY2022-FY2026, person-level")
    print("   PRIMARY = latest pre-demand address in the lookback.  SENSITIVITY = any Town address in 3 prior FY.")
    cP = Counter(r["_coh"] for r in rows if r["_coh"]); cS = Counter(r["_cohA"] for r in rows if r["_cohA"])
    rP = cP["A"]+cP["C"]+cP["D"]; rS = cS["A"]+cS["C"]+cS["D"]
    print(f"   {'':40s} {'PRIMARY':>9} {'':>8}   {'SENSITIVITY':>11}")
    for k, lab in (("A","resident, placed in Cochrane"),("C","resident, placed outside"),("D","resident, no placement in source")):
        print(f"   {k}  {lab:36s} {cP[k]:9,} {pct(cP[k],rP):>8}   {cS[k]:11,} {pct(cS[k],rS):>8}")
    print(f"      {'resident demand A + C + D':36s} {rP:9,} {'':>8}   {rS:11,}")
    print(f"   B  {'NON-TOWN resident, placed in Cochrane':36s} {cP['B']:9,} {'':>8}   {cS['B']:11,}")
    bc = sum(1 for r in rows if r["_coh"]=="B" and r["_resL"]==AREA)
    bu = sum(1 for r in rows if r["_inc"] and r["_app"] and r["_valid"] and r["_resL"]==UNRES)
    print(f"        of which Cochrane catchment          {bc:9,}")
    print(f"      Cochrane placement, residency UNRESOLVED {bu:9,}   (own category; never A or B)")
    print(f"      A + B = every Cochrane placement with known residency: {cP['A']+cP['B']:,}")
    dc = Counter(r["_dcls"] for r in rows if r["_coh"]=="D")
    print("\n   D by class (primary) — different findings, never one word:")
    for k in sorted(dc): print(f"     {k:48s} {dc[k]:6,}   {pct(dc[k],cP['D'])} of D")
    print(f"\n   never approved, excluded from A-D: {sum(1 for r in rows if not r['_app']):,}")
    print(f"   of D, placed AFTER follow-up end (sensitivity only): {sum(1 for r in rows if r['_coh']=='D' and r['_plaf']):,}")
    print(f"   of D, received a Level 3 bed instead: {sum(1 for r in rows if r['_coh']=='D' and col(r,'FIRST_LEVEL3_DT')):,}")
    print("\n   SOURCE COVERAGE — applies to ALL of D, not only D3: the placement source is the Calgary and")
    print("   Edmonton Strata instances. D means no Type A/B placement observed IN THAT SOURCE by 2026-03-31.\n")
    return cP

# ── 3. residency uncertainty, no request gate ───────────────────────────────
def uncertainty(rows, cP):
    print("3. RESIDENCY UNCERTAINTY AROUND D — tiers, no request-based gate")
    town = [r for r in rows if r["_coh"] in ("A","C","D")]
    req = sum(1 for r in town if r["_req"]); pl = [r for r in town if r["_coh"] in ("A","C")]
    reqpl = sum(1 for r in pl if r["_req"])
    print(f"   known Town demand with a recorded Cochrane request: {req:,} of {len(town):,} ({pct(req,len(town)).strip()});")
    print(f"   among those placed (A+C): {reqpl:,} of {len(pl):,} ({pct(reqpl,len(pl)).strip()}).")
    print( "   -> absence of a request says nothing about residency; it must not narrow the pool.")
    un_all = [r for r in rows if r["_resFin"]==UNRES and r["_app"] and not r["_pl"]]
    un = [r for r in un_all if r["_valid"]]
    print(f"\n   unresolved after registry AND Strata, approved, unplaced: {len(un_all):,}  (valid records {len(un):,})")
    print(f"\n   D:  primary {cP['D']:,}    mathematical maximum {cP['D']+len(un):,}  = primary + every valid unresolved person counted as Town")
    print( "   Neither the fallback nor a proportional allocation reduces that maximum. It is not an estimate.")
    if any(r["_resF"] for r in rows):
        f = Counter(r["_resF"] for r in un)
        yrs = sorted(int(col(r,"FALLBACK_YEARS_BEFORE_DEMAND")) for r in un if r["_resF"]!=UNRES and col(r,"FALLBACK_YEARS_BEFORE_DEMAND"))
        print(f"\n   fallback residency — HISTORICAL EVIDENCE ONLY (addresses {min(yrs) if yrs else '-'}-{max(yrs) if yrs else '-'} years old, median {st.median(yrs) if yrs else '-'}):")
        for k, v in f.most_common(): print(f"       {k:36s} {v:6,}")
        print( "   A decade-old non-Cochrane address is evidence, not resolution. Reported, not subtracted.")
    byr = Counter(col(r,"RESIDENCY_MISSING_REASON") for r in un)
    print("   unresolved by reason: " + "; ".join(f"{k} {v}" for k, v in byr.most_common()) + "\n")

# ── 3a. Strata secondary source — rule 10 ───────────────────────────────────
def strata(rows):
    if "RESIDENCY_FINAL" not in rows[0]:
        print("3a. STRATA SECONDARY SOURCE — not in this extract (pre rev 2.5).\n"); return
    print("3a. STRATA address_h AS SECONDARY RESIDENCY SOURCE (rule 10)")
    prev = [r for r in rows if r["_resL"]==UNRES]
    res  = [r for r in prev if r["_src"]=="STRATA_ADDRESS_H"]
    print(f"   previously unresolved on the registry: {len(prev):,}   resolved by Strata: {len(res):,}   remaining unresolved: {len(prev)-len(res):,}")
    for k, v in Counter(r["_resFin"] for r in res).most_common(): print(f"     {k:36s} {v:6,}")
    ru = [r for r in res if r["_app"] and not r["_pl"] and r["_valid"]]
    print(f"   of the resolved, approved & unplaced: {len(ru):,}  -> " + ", ".join(f"{k} {v}" for k,v in Counter(r["_resFin"] for r in ru).most_common()))
    cR = Counter(r["_cohR"] for r in rows if r["_cohR"]); cF = Counter(r["_coh"] for r in rows if r["_coh"])
    print(f"\n   {'cohort':8s} {'registry only':>14} {'with Strata':>12} {'diff':>6}")
    for k in ("A","B","C","D"): print(f"   {k:8s} {cR[k]:14,} {cF[k]:12,} {cF[k]-cR[k]:+6,}")
    unp = [r for r in prev if r["_app"] and not r["_pl"] and r["_valid"]]
    still = [r for r in unp if r["_src"]!="STRATA_ADDRESS_H"]
    print(f"\n   unresolved+approved+unplaced: before {len(unp):,}  after {len(still):,}   -> maximum on D falls from {cR['D']+len(unp):,} to {cF['D']+len(still):,}")
    # why the rest stayed unresolved — four DISJOINT classes that must sum to the remainder
    rem = [r for r in prev if r["_src"]!="STRATA_ADDRESS_H"]
    def cls(r):
        if col(r,"STRATA_ADDRESS_IS_FACILITY","0")=="1":            return "facility address at demand (shared by 3+ people) — not used"
        if r["_strat"]==UNRES and col(r,"STRATA_POSTAL_CODE_AT_DEMAND"): return "Alberta postal code at demand fails the geography lookup"
        if r["_strat"]==UNRES:                                        return "address at demand but no postal code"
        if col(r,"STRATA_HISTORICAL_POSTAL_CODE"):                    return "no address active at demand; older address only (rule 9)"
        return "no Strata address row at all"
    part = Counter(cls(r) for r in rem)
    print(f"\n   why {len(rem):,} stayed unresolved (disjoint; sums to {sum(part.values()):,}):")
    for k, v in part.most_common(): print(f"     {k:66s} {v:5,}")
    ys = sorted(int(col(r,"STRATA_HISTORICAL_YEARS_BEFORE_DEMAND")) for r in rem if cls(r).startswith("no address active"))
    if ys: print(f"       rule-9 staleness: {min(ys)}-{max(ys)} years before demand, median {st.median(ys)}")
    # the Cochrane resolutions must be private homes, never a facility under the threshold
    coch = [r for r in res if r["_resFin"] in (TOWN, AREA)]
    if coch:
        sb = Counter(col(r,"STRATA_ADDRESS_SHARED_BY_N") for r in coch)
        print(f"   Strata resolutions TO Cochrane/catchment: {len(coch):,}; address shared by N people: {dict(sb)}  (all must be 1)")
    oop = sum(1 for r in res if col(r,"STRATA_POSTAL_CODE_AT_DEMAND") and not col(r,"STRATA_POSTAL_CODE_AT_DEMAND").startswith("T"))
    cre = sum(1 for r in res if col(r,"STRATA_FROM_EQUALS_CREATION","0")=="1")
    print(f"   of the {len(res):,} Strata resolutions: out-of-province postal code {oop:,}; effective_from equals record creation date {cre:,}\n")

# ── G1. approval-precedence sensitivity ─────────────────────────────────────
def gate1(rows):
    print("G1. APPROVAL-DATE PRECEDENCE — row-level coalesce (current) vs person-level coalesce(min,min)")
    if "DEMAND_DT_ALT" not in rows[0]:
        print("   not in this extract (pre rev 2.6). Preview on a 777-person extract: 8 dates change (1.0%), 5 cross a FY, 2 enter/leave the window.\n"); return
    both = [r for r in rows if r["_dem"] and r["_demA"]]
    chg = [r for r in both if r["_dem"] != r["_demA"]]
    fye = lambda d: d.year+1 if d.month>=4 else d.year
    fy  = sum(1 for r in chg if fye(r["_dem"]) != fye(r["_demA"]))
    enter = sum(1 for r in rows if r["_inwA"] and not r["_inw"]); leave = sum(1 for r in rows if r["_inw"] and not r["_inwA"])
    resch = sum(1 for r in chg if r["_resFin"] != (r["_resFinA"] or r["_resFin"]))
    later = sum(1 for r in chg if r["_demA"] > r["_dem"])
    print(f"   people with both anchors {len(both):,}; demand date changes {len(chg):,} ({pct(len(chg),len(both)).strip()}), of which later {later:,}")
    print(f"   crossing a fiscal-year boundary {fy:,};  entering the window {enter:,};  leaving it {leave:,};  residency class changes {resch:,}")
    cP = Counter(r["_coh"] for r in rows if r["_coh"]); cA = Counter(r["_cohAlt"] for r in rows if r["_cohAlt"])
    print(f"\n   {'cohort':8s} {'current':>9} {'alt':>9} {'diff':>6}")
    for k in ("A","B","C","D"): print(f"   {k:8s} {cP[k]:9,} {cA[k]:9,} {cA[k]-cP[k]:+6,}")
    rp = cP["A"]+cP["C"]+cP["D"]; ra = cA["A"]+cA["C"]+cA["D"]
    print(f"   {'A+C+D':8s} {rp:9,} {ra:9,} {ra-rp:+6,}")
    tr = Counter((r["_coh"] or "-", r["_cohAlt"] or "-") for r in rows if (r["_coh"] or r["_cohAlt"]) and r["_coh"] != r["_cohAlt"])
    if tr:
        print("   person-level moves:"); [print(f"     {a} -> {b} {v:5,}") for (a,b),v in tr.most_common()]
    print()

# ── G2. addresses active on the demand date ─────────────────────────────────
def gate2(rows):
    print("G2. STRATA ADDRESSES ACTIVE ON THE DEMAND DATE")
    if "STRATA_N_ACTIVE_AT_DEMAND" not in rows[0]:
        print("   not in this extract (pre rev 2.6); see sql/11 block A2.\n"); return
    used = [r for r in rows if r["_src"]=="STRATA_ADDRESS_H"]
    na = Counter(int(col(r,"STRATA_N_ACTIVE_AT_DEMAND","0") or 0) for r in used)
    print(f"   among the {len(used):,} people Strata resolved, active versions on the demand date: {dict(sorted(na.items()))}")
    multi = [r for r in used if int(col(r,"STRATA_N_ACTIVE_AT_DEMAND","0") or 0) > 1]
    dis = [r for r in multi if col(r,"STRATA_ACTIVE_CLASSES_DISAGREE","0")=="1"]
    print(f"   more than one active: {len(multi):,};  competing versions DISAGREE on class: {len(dis):,}")
    coh = Counter(r["_coh"] or "-" for r in dis)
    print(f"   of the disagreeing, cohort under the tiebreak: {dict(coh)}  <- these are the only assignments the tiebreak could change\n")

# ── G3. Surrey proof ────────────────────────────────────────────────────────
def gate3(rows):
    print("G3. PROOF CASE — PHN 49833-8261")
    r = next((r for r in rows if r["_phn"]=="498338261"), None)
    if not r: print("   NOT IN THE EXTRACT\n"); return
    print(f"   demand {r['_dem']}  registry {r['_resL']}  ->  Strata '{col(r,'STRATA_ADDRESS_AT_DEMAND')}' {col(r,'STRATA_CITY_AT_DEMAND')} "
          f"{col(r,'STRATA_POSTAL_CODE_AT_DEMAND')} effective {col(r,'STRATA_EFFECTIVE_FROM')[:10]}  ->  {r['_strat']}")
    ok = r["_resL"]==UNRES and r["_src"]=="STRATA_ADDRESS_H" and r["_resFin"]==NOT
    print(f"   residency_source {r['_src']}   residency_final {r['_resFin']}   {'PROVEN' if ok else 'FAILS'}\n")

# ── G4. facility audit ──────────────────────────────────────────────────────
def gate4(rows):
    print("G4. FACILITY GUARD AUDIT")
    prev = [r for r in rows if r["_resL"]==UNRES]
    fac = [r for r in prev if col(r,"STRATA_ADDRESS_IS_FACILITY","0")=="1"]
    key = "STRATA_ADDRESS_CONCURRENT_N" if "STRATA_ADDRESS_CONCURRENT_N" in rows[0] else "STRATA_ADDRESS_SHARED_BY_N"
    basis = "CONCURRENT occupants on the demand date" if key.endswith("CONCURRENT_N") else "EVER shared by (pre rev 2.6 — over-blocks apartment units)"
    print(f"   guard basis: {basis}")
    print(f"   blocked: {len(fac):,};  distribution of {key}: {dict(sorted(Counter(int(col(r,key,'0') or 0) for r in fac).items()))}")
    ph = [r for r in prev if col(r,"STRATA_ADDRESS_IS_PLACEHOLDER","0")=="1"]
    if ph: print(f"   placeholder addresses (NO FIXED ADDRESS, EVACUEE …), separate class: {len(ph):,}")
    small = [r for r in fac if 3 <= int(col(r,key,"0") or 0) <= 5]
    print(f"   every blocked address with 3-5 people ({len(small):,}):")
    for r in sorted(small, key=lambda x: int(col(x,key,"0") or 0)):
        print(f"     n={col(r,key)}  {col(r,'STRATA_ADDRESS_AT_DEMAND')[:38]:38s} {col(r,'STRATA_CITY_AT_DEMAND')[:14]:14s} {col(r,'STRATA_POSTAL_CODE_AT_DEMAND'):7s}  approved&unplaced {int(r['_app'] and not r['_pl'])}")
    rem = [r for r in rows if r["_resFin"]==UNRES and r["_app"] and not r["_pl"] and r["_valid"] and r["_inw"]]
    sole = [r for r in rem if col(r,"STRATA_ADDRESS_IS_FACILITY","0")=="1"]
    print(f"   remaining unresolved+approved+unplaced: {len(rem):,}; unresolved SOLELY because of the guard: {len(sole):,}")
    print( "   A facility reference table confirmed by ALA is preferable to any threshold; sql/11 block E lists candidates.\n")

# ── remaining unresolved clients ────────────────────────────────────────────
def remaining(rows):
    rem = [r for r in rows if r["_resFin"]==UNRES and r["_app"] and not r["_pl"] and r["_valid"] and r["_inw"]]
    print(f"REMAINING UNRESOLVED, APPROVED, UNPLACED — {len(rem):,} people (PHN masked)")
    for r in sorted(rem, key=lambda x: x["_dem"]):
        st_ = ("placeholder" if col(r,"STRATA_ADDRESS_IS_PLACEHOLDER","0")=="1" else "facility" if col(r,"STRATA_ADDRESS_IS_FACILITY","0")=="1"
               else "no postal" if col(r,"STRATA_ADDRESS_AT_DEMAND") and not col(r,"STRATA_POSTAL_CODE_AT_DEMAND")
               else "no strata row" if not col(r,"STRATA_ADDRESS_AT_DEMAND") else "unmapped T-code")
        print(f"   …{r['_phn'][-4:]}  demand {r['_dem']}  registry: {col(r,'RESIDENCY_MISSING_REASON')[:36]:36s} strata: {st_:13s} {r['_dcls'][:2] or '-'}")
    print()

# ── final validation table ──────────────────────────────────────────────────
def final_table(rows):
    print("FINAL VALIDATION TABLE")
    cR = Counter(r["_cohR"] for r in rows if r["_cohR"]); cF = Counter(r["_coh"] for r in rows if r["_coh"])
    cA = Counter(r["_cohAlt"] for r in rows if r["_cohAlt"]); cS = Counter(r["_cohA"] for r in rows if r["_cohA"])
    hasalt = "DEMAND_DT_ALT" in rows[0]
    def unres(res_key, inw_key="_inw"):
        return sum(1 for r in rows if r[res_key]==UNRES and r["_app"] and not r["_pl"] and r["_valid"] and r[inw_key])
    uR, uF = unres("_resL"), unres("_resFin")
    uA = sum(1 for r in rows if (r["_resFinA"] or "")==UNRES and r["_app"] and not r["_plA"] and r["_valid"] and r["_inwA"]) if hasalt else None
    hdr = f"   {'':34s} {'registry only':>14} {'registry+Strata':>16} {'approval-prec.':>15} {'any-3-yr sens.':>15}"
    print(hdr)
    def row(lab, a, b, c, d): print(f"   {lab:34s} {a:>14} {b:>16} {(c if c is not None else '—'):>15} {d:>15}")
    for k, lab in (("A","A  resident, placed in Cochrane"),("B","B  non-Town, placed in Cochrane"),("C","C  resident, placed outside"),("D","D  resident, no placement in source")):
        row(lab, f"{cR[k]:,}", f"{cF[k]:,}", f"{cA[k]:,}" if hasalt else None, f"{cS[k]:,}")
    row("resident demand A+C+D", f"{cR['A']+cR['C']+cR['D']:,}", f"{cF['A']+cF['C']+cF['D']:,}", f"{cA['A']+cA['C']+cA['D']:,}" if hasalt else None, f"{cS['A']+cS['C']+cS['D']:,}")
    row("unresolved, approved, unplaced", f"{uR:,}", f"{uF:,}", f"{uA:,}" if hasalt else None, "—")
    row("D mathematical maximum", f"{cR['D']+uR:,}", f"{cF['D']+uF:,}", f"{cA['D']+uA:,}" if hasalt else None, "—")
    print("   B = any non-Town resident placed in Cochrane (b_catchment kept). Fallback registry addresses are evidence only.\n")

# ── 3b. residency evidence ──────────────────────────────────────────────────
def evidence(rows):
    print("3b. RESIDENCY EVIDENCE for the verdicts actually used (A/C/D people)")
    g = [r for r in rows if r["_coh"] in ("A","C","D")]
    if any(r["_evid"] for r in g):
        for k, v in Counter(r["_evid"] for r in g).most_common(): print(f"   {k:64s} {v:6,}  {pct(v,len(g))}")
        stab = sum(1 for r in g if col(r,"RESIDENCY_STABLE_IN_LOOKBACK","0")=="1")
        print(f"   stable across the lookback (all mapped years agree on Town / not Town): {stab:,} of {len(g):,}")
    else:
        print("   RESIDENCY_EVIDENCE not in this extract (pre rev 2.4).")
    dep = Counter(r["_depth"] for r in rows if r["_resL"]==UNRES)
    print(f"   registry history depth among UNRESOLVED (depth is not confidence): {dict(dep)}\n")

# ── 4. method matrix ────────────────────────────────────────────────────────
def methods(rows):
    print("4. PRIMARY vs SENSITIVITY residency — person-level transition (approved only)")
    tr = Counter((r["_resA"], r["_resL"]) for r in rows if r["_app"])
    moved = sum(v for (a,b),v in tr.items() if a != b)
    print(f"   verdict differs: {moved:,} of {sum(tr.values()):,}")
    for (a,b),v in sorted(tr.items(), key=lambda x:-x[1]):
        if a != b: print(f"     any3 {a:30s} -> latest {b:30s} {v:6,}")
    print()

# ── 5. year, truncation, waits ──────────────────────────────────────────────
def year_waits(rows):
    print("5. BY FISCAL YEAR OF DEMAND EVENT (primary) — censoring rises to the right")
    print(f"   {'FYE':>6} {'A':>6} {'C':>6} {'D1':>6} {'D2':>6} {'D3':>6}")
    for y in sorted({r["DEMAND_FYE"] for r in rows if r["_coh"]}):
        g = [r for r in rows if r["DEMAND_FYE"]==y and r["_coh"]]
        c = Counter(r["_coh"] for r in g); d = Counter(r["_dcls"][:2] for r in g if r["_coh"]=="D")
        print(f"   {y:>6} {c['A']:6,} {c['C']:6,} {d['D1']:6,} {d['D2']:6,} {d['D3']:6,}")
    print(f"   flagged left-truncated: {sum(1 for r in rows if r['_lt']):,} (pre-window approvals are excluded, not flagged)")
    print("\n6. DAYS FROM APPROVAL TO FIRST PLACEMENT (primary, placed only)")
    for coh in ("A","B","C"):
        d = sorted(int(col(r,"DAYS_TO_PLACEMENT")) for r in rows if r["_coh"]==coh and col(r,"DAYS_TO_PLACEMENT"))
        if d: print(f"   {coh}  n {len(d):5,}   median {int(st.median(d)):4d}   p90 {d[int(len(d)*.9)]:4d}")
    cf = sum(1 for r in rows if col(r,"COCHRANE_FACING","1")=="1")
    print(f"\n   audit universe {len(rows):,} rows; cochrane_facing presentation subset {cf:,} (reported, not filtered)\n")

# ── 7. reconciliation matrix ────────────────────────────────────────────────
def reconcile(rows, pub_path, cP):
    P = [x for x in csv.DictReader(open(pub_path)) if x["PATIENT_ID"]]
    pub = {}
    for x in P:
        if (x["ADMISSION_SEQ"]=="1" and x["PHN"].strip() and x["FIRST_AB_ADMISSION_DATE"][:10] >= "2021-04-01"
            and x["CARE_STREAM"] != "Type B - Level 3"):
            t, a, i = x["TOWN_3YR"]=="1", x["AREA_3YR"]=="1", x["PLACED_IN_COCHRANE"]=="1"
            c = "A" if t and i else "C" if t else "B" if (i and not a) else None
            if c: pub[phn(x["PHN"])] = c
    mas = {r["_phn"]: r for r in rows}
    cols_ = ["A","B","C","D","none","absent"]; rows_ = ["A","B","C"]
    M = {r_: Counter() for r_ in rows_}
    for p, c in pub.items():
        if p not in mas: M[c]["absent"] += 1
        else: M[c][mas[p]["_coh"] or "none"] += 1
    print("7. RECONCILIATION — published A/B/C (query 02 demand basis) -> master PRIMARY cohort")
    print("   Full transition matrix. Not expected to be diagonal; every off-diagonal cell needs a reason.")
    hdr = "published / master"
    print(f"   {hdr:22s}" + "".join(f"{c:>8}" for c in cols_) + f"{'TOTAL':>8}")
    tot = Counter()
    for r_ in rows_:
        line = f"   {r_:22s}" + "".join(f"{M[r_][c]:8,}" for c in cols_) + f"{sum(M[r_].values()):8,}"
        print(line); tot.update(M[r_])
    print(f"   {'TOTAL':22s}" + "".join(f"{tot[c]:8,}" for c in cols_) + f"{sum(tot.values()):8,}")
    kept = sum(M[r_][r_] for r_ in rows_); allp = sum(tot.values())
    print(f"\n   kept cohort {kept:,} of {allp:,}; changed or absent {allp-kept:,}")
    print(f"   master D = {cP['D']:,} (no published counterpart)\n")
    # reasons for the off-diagonal, from the data
    print("   off-diagonal reasons (from the master extract where present):")
    reasons = Counter()
    for p, c in pub.items():
        if p not in mas: reasons[(c,"absent","not in master: approval before window or already in care at demand")] += 1; continue
        m = mas[p]; mc = m["_coh"] or "none"
        if mc == c: continue
        if mc == "none" and m["_resL"] == UNRES: reasons[(c,mc,f"residency unresolved at earlier anchor ({col(m,'RESIDENCY_MISSING_REASON')})")] += 1
        elif mc == "none": reasons[(c,mc,f"residency now {m['_resL']}")] += 1
        else: reasons[(c,mc,f"residency now {m['_resL']} (any3 {m['_resA']})")] += 1
    for (a,b,why),v in sorted(reasons.items(), key=lambda x:-x[1]): print(f"     {a} -> {b:7s} {v:4,}  {why}")
    print()

def main(a):
    rows = load(a.master_csv)
    print(f"\n{a.master_csv}\n{len(rows):,} people in the audit universe\n")
    if not integrity(rows): sys.exit("INTEGRITY CHECKS FAILED — nothing else is printed. Fix the query first.")
    cP = cohorts(rows); uncertainty(rows, cP); strata(rows); evidence(rows); methods(rows); year_waits(rows)
    gate1(rows); gate2(rows); gate3(rows); gate4(rows); remaining(rows); final_table(rows)
    if a.published: reconcile(rows, a.published, cP)
    print("A clean run is a data-integrity result, not a methodological sign-off.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("master_csv"); ap.add_argument("--published")
    main(ap.parse_args())
