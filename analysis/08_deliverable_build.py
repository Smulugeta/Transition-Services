#!/usr/bin/env python3
"""
Build the final Cochrane planning deliverable from the master cohort extract.

Two grains, kept apart:
  PERSON  — one row per person (unique demand). Controlling table.
  EVENT   — one row per qualifying Type A/B admission (placement activity).

Inputs
  --person   sql/14 deliverable extract (or, provisionally, the sql/09 rev 2.9
             export: every field it lacks is reported as NOT IN EXTRACT, never
             invented)
  --events   sql/15 placement-event extract (optional until it exists)
  --salt     file holding the project STUDY_ID salt (created on first run;
             keep it outside the repository and never change it)
  --expect   accepted production A,B,C,D (default 89,148,192,69). The build
             STOPS if the extract disagrees: enrichment joins must never move
             a cohort.
  --out      output directory (default deliverables/, git-ignored)

Outputs (all in --out)
  COCHRANE_DEMAND_INTERNAL_QA.csv   person grain, all identifiers and QA flags
  COCHRANE_DEMAND_CONSULTANT.csv    person grain, STUDY_ID only
  COCHRANE_PLACEMENT_ACTIVITY_INTERNAL.csv / _CONSULTANT.csv  (when --events)
  COCHRANE_SUMMARY.md               demand-year, placement-year, wait-time,
                                    demographic, residence, origin tables
  REVIEWER_PRECHECK.md              the 12 items the reviewer asked to see
                                    before anything is published

Rules carried from the validated methodology
  · COHORT and D_CLASS are taken from the extract as validated by
    analysis/07; they are never recomputed here.
  · DAYS_TO_PLACEMENT is NULL for anyone without an observed placement by
    31 March 2026. DAYS_WAITING_AS_OF_FOLLOWUP is a separate, labelled field.
  · Ages are computed at the event date, never at today's date.
  · Community of residence comes only from the address that decided
    RESIDENCY_FINAL. Fallback registry addresses are evidence, not residence.
  · Occupancy / building flags are QA only.
"""
import csv, sys, os, argparse, hmac, hashlib, secrets, datetime as dt, statistics as st
from collections import Counter, defaultdict, OrderedDict

WIN_START, WIN_END, FOLLOW_UP = dt.date(2021,4,1), dt.date(2026,4,1), dt.date(2026,3,31)
TOWN, AREA, NOT, UNRES = "Town of Cochrane", "Cochrane catchment", "Not a Cochrane-area resident", "UNRESOLVED"
FYES = [2022, 2023, 2024, 2025, 2026]

def day(s):
    s = (s or "").strip(); return dt.datetime.strptime(s[:10], "%Y-%m-%d").date() if s else None
def col(r, k, default=""): return (r.get(k) or default).strip()
def fye(d): return None if d is None else (d.year + 1 if d.month >= 4 else d.year)
def age_at(dob, d):
    if not dob or not d: return None
    return d.year - dob.year - ((d.month, d.day) < (dob.month, dob.day))
def age_band(a):
    if a is None: return ""
    return "<65" if a < 65 else "65-74" if a < 75 else "75-84" if a < 85 else "85+"
def pct(a, b): return f"{a/b*100:.1f}%" if b else "—"
def q(xs, p):
    xs = sorted(xs); n = len(xs)
    if n == 0: return None
    k = (n - 1) * p; f = int(k); c = min(f + 1, n - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)

# ── origin-setting normalisation (built from the real vocabulary in the extract) ──
def origin_detail(v):
    u = (v or "").upper().strip()
    if not u: return "Unknown"
    if "OUT OF PROVINCE" in u: return "Out of province"
    if u == "OUT OF REGION": return "Out of region"
    if any(k in u for k in ("EMERG", " ED ", "- ED", "EMERGENCY")): return "Emergency department"
    if any(k in u for k in ("HOME", "PERSONAL RESIDENCE")) and "LODGE" not in u: return "Own home"
    if "HOSPICE" in u or "PALLIAT" in u: return "Hospice / palliative"
    if any(k in u for k in ("RCTP", "REHAB", "TRANSITION", "SUBACUTE", "SUB-ACUTE", "SUB ACUTE", "RESTORATIVE",
                            "STEP DOWN", " IT /", "IT / RCTP", "GLENROSE", "LEVEL 5")): return "Sub-acute / transition / rehab"
    if any(k in u for k in ("HOSPITAL", "MEDICAL CENTRE", "HEALTH CAMPUS", "HEALTH CENTRE", "PETER LOUGHEED",
                            "FOOTHILLS", "ROCKYVIEW", "VILLA CARITAS", "ACUTE", "STURGEON")): return "Acute hospital"
    if "ALC" in u: return "Continuing-care ALC bed"
    if "LODGE" in u: return "Lodge"
    if any(k in u for k in ("ASSISTED LIVING", "SL4", "DSL", "SUPPORTIVE LIVING", "DAL")): return "Supportive living"
    if any(k in u for k in ("LTC", "LONG TERM CARE", "CAPITAL CARE", "CAREWEST", "NURSING")): return "Long-term care"
    if "ZONE" in u: return "Other (zone-level)"
    return "Other"
COARSE = {"Own home": "Community", "Emergency department": "Emergency/ED", "Acute hospital": "Acute care",
          "Sub-acute / transition / rehab": "Acute care (sub-acute / transition)",
          "Continuing-care ALC bed": "Other continuing care", "Lodge": "Other continuing care",
          "Supportive living": "Other continuing care", "Long-term care": "Other continuing care",
          "Hospice / palliative": "Other continuing care", "Out of province": "Out of province",
          "Out of region": "Other", "Other (zone-level)": "Other", "Other": "Other", "Unknown": "Unknown"}

# ── STUDY_ID ──────────────────────────────────────────────────────────────────
def load_salt(path):
    if os.path.exists(path):
        s = open(path).read().strip()
        if len(s) < 32: sys.exit(f"salt file {path} is too short; refuse to run")
        return s
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    s = secrets.token_hex(32); open(path, "w").write(s + "\n")
    print(f"NEW STUDY_ID salt written to {path}. Keep it; STUDY_IDs are only stable while it is unchanged.")
    return s
def study_id(salt, phn):
    return "CD-" + hmac.new(salt.encode(), phn.encode(), hashlib.sha256).hexdigest()[:12].upper()

# ── load person grain ─────────────────────────────────────────────────────────
def load_person(path, salt):
    rd = csv.DictReader(open(path)); rd.fieldnames = [h.strip().upper() for h in rd.fieldnames]
    rows = [{k: (v or "").strip() for k, v in r.items()} for r in rd]
    have = set(rows[0]) if rows else set()
    P = []
    for r in rows:
        phn = "".join(c for c in col(r, "PHN") if c.isdigit())
        d = OrderedDict()
        d["STUDY_ID"] = study_id(salt, phn) if phn else ""
        d["PHN"] = phn
        d["PATIENT_ID"] = col(r, "PATIENT_ID")
        d["COHORT"] = col(r, "COHORT"); d["D_CLASS"] = col(r, "D_CLASS")
        d["_dem"] = day(col(r, "DEMAND_DT")); d["_demA"] = day(col(r, "DEMAND_DT_ALT"))
        d["DEMAND_DT"] = col(r, "DEMAND_DT")[:10]; d["DEMAND_FYE"] = fye(d["_dem"]) or ""
        d["DEMAND_EVENT_TYPE"] = col(r, "DEMAND_EVENT_TYPE")
        d["FIRST_WAITLIST_APPEARANCE"] = col(r, "FIRST_LIST_APPEARANCE")[:10]
        d["FIRST_APPROVAL_DT"] = col(r, "FIRST_APPROVAL_DT")[:10]
        d["SETTING_AT_LIST_ENTRY"] = col(r, "SETTING_AT_LIST_ENTRY")
        d["LAST_SEEN_ON_LIST"] = col(r, "LAST_SEEN_ON_LIST")[:10]
        d["ON_LIST_AT_FOLLOWUP"] = col(r, "ON_LIST_AT_FOLLOWUP", "0")
        d["RATED_COCHRANE"] = col(r, "RATED_COCHRANE", "0")
        d["REQUESTED_SITE"] = col(r, "REQUESTED_SITE"); d["REQUESTED_CARE_STREAM"] = col(r, "REQUESTED_CARE_STREAM")
        d["REQUESTED_COCHRANE_FLAG"] = col(r, "REQUESTED_COCHRANE_FLAG") or d["RATED_COCHRANE"]
        d["N_SITES_REQUESTED"] = col(r, "N_SITES_REQUESTED")
        # demographics — only from the extract, never derived from today
        d["SEX"] = col(r, "SEX") or col(r, "GENDER"); d["DEMOGRAPHIC_SOURCE"] = col(r, "DEMOGRAPHIC_SOURCE")
        dob = day(col(r, "DOB")); d["DOB"] = col(r, "DOB")[:10]; d["_dob"] = dob
        d["_pl"] = day(col(r, "FIRST_PLACEMENT_DT")); d["_fw"] = day(col(r, "FIRST_LIST_APPEARANCE"))
        d["AGE_AT_DEMAND"] = age_at(dob, d["_dem"]); d["AGE_AT_FIRST_WAITLIST"] = age_at(dob, d["_fw"])
        d["AGE_AT_PLACEMENT"] = age_at(dob, d["_pl"]); d["AGE_GROUP_AT_DEMAND"] = age_band(d["AGE_AT_DEMAND"])
        # residence
        d["RESIDENCY_FINAL"] = col(r, "RESIDENCY_FINAL") or col(r, "RESIDENCY_LATEST")
        d["RESIDENCY_SOURCE"] = col(r, "RESIDENCY_SOURCE")
        d["RESIDENCE_COMMUNITY_AT_DEMAND"] = col(r, "RESIDENCE_COMMUNITY_AT_DEMAND")
        d["RESIDENCE_POSTAL_CODE_AT_DEMAND"] = col(r, "RESIDENCE_POSTAL_CODE_AT_DEMAND")
        d["COCHRANE_TOWN_FLAG"] = "1" if d["RESIDENCY_FINAL"] == TOWN else "0"
        d["COCHRANE_CATCHMENT_FLAG"] = "1" if d["RESIDENCY_FINAL"] == AREA else "0"
        d["RESIDENCY_EVIDENCE"] = col(r, "RESIDENCY_EVIDENCE")
        # origin setting — nearest the demand event when sql/14 supplies it; provisional otherwise
        raw = col(r, "ORIGIN_SETTING_RAW"); src = col(r, "ORIGIN_SOURCE")
        if not raw and "ORIGIN_SETTING_RAW" not in have:
            raw = d["SETTING_AT_LIST_ENTRY"]; src = "PROVISIONAL waitlist current_location at first list appearance (sql/14 replaces with the census row nearest DEMAND_DT)"
        d["ORIGIN_SETTING_RAW"] = raw; d["ORIGIN_SETTING_DETAIL"] = origin_detail(raw)
        d["ORIGIN_SETTING"] = COARSE[d["ORIGIN_SETTING_DETAIL"]]
        d["ORIGIN_SITE"] = col(r, "ORIGIN_SITE") or raw; d["ORIGIN_SOURCE"] = src
        # placement
        d["FIRST_PLACEMENT_DT"] = col(r, "FIRST_PLACEMENT_DT")[:10]; d["PLACEMENT_FYE"] = fye(d["_pl"]) or ""
        d["FIRST_PLACEMENT_SITE"] = col(r, "FIRST_PLACEMENT_SITE"); d["FIRST_PLACEMENT_STREAM"] = col(r, "FIRST_PLACEMENT_STREAM")
        d["FIRST_PLACEMENT_IN_COCHRANE"] = col(r, "FIRST_PLACEMENT_IN_COCHRANE", "0")
        d["DAYS_TO_PLACEMENT"] = (d["_pl"] - d["_dem"]).days if (d["_pl"] and d["_dem"]) else ""
        d["DAYS_WAITING_AS_OF_FOLLOWUP"] = ((FOLLOW_UP - d["_dem"]).days if (not d["_pl"] and d["_dem"] and d["ON_LIST_AT_FOLLOWUP"] == "1") else "")
        d["FIRST_PLACEMENT_AFTER_FOLLOWUP"] = col(r, "FIRST_PLACEMENT_AFTER_FOLLOWUP")[:10]
        d["_plA"] = day(col(r, "FIRST_PLACEMENT_DT_ALT"))
        d["DEATH_DT"] = col(r, "DEATH_DT")[:10]
        # QA / gating fields
        d["IN_WINDOW"] = col(r, "IN_WINDOW", "1"); d["WAS_APPROVED"] = col(r, "WAS_APPROVED", "1")
        d["RECORD_VALID"] = col(r, "RECORD_VALID", "1"); d["RECORD_INVALID_REASON"] = col(r, "RECORD_INVALID_REASON")
        d["STRATA_ADDRESS_AT_DEMAND"] = col(r, "STRATA_ADDRESS_AT_DEMAND"); d["STRATA_RESIDENCY"] = col(r, "STRATA_RESIDENCY")
        d["STRATA_OCCUPANCY_FLAG"] = col(r, "STRATA_OCCUPANCY_FLAG"); d["STRATA_NAMED_FACILITY_CANDIDATE"] = col(r, "STRATA_NAMED_FACILITY_CANDIDATE")
        d["STRATA_ADDRESS_IS_PLACEHOLDER"] = col(r, "STRATA_ADDRESS_IS_PLACEHOLDER")
        d["COCHRANE_PLACEMENT_RESIDENCY_UNRESOLVED"] = col(r, "COCHRANE_PLACEMENT_RESIDENCY_UNRESOLVED", "0")
        d["B_CATCHMENT"] = col(r, "B_CATCHMENT", "0")
        d["PHN_PATIENT_ID_MULTIPLICITY"] = col(r, "PHN_PATIENT_ID_MULTIPLICITY")
        d["PATIENT_ID_ALL"] = col(r, "PATIENT_ID_ALL"); d["N_PATIENT_IDS"] = col(r, "N_PATIENT_IDS")
        d["DOB_STRATA"] = col(r, "DOB_STRATA")[:10]; d["DOB_REGISTRY"] = col(r, "DOB_REGISTRY")[:10]
        d["DOB_SOURCES_AGREE"] = col(r, "DOB_SOURCES_AGREE"); d["SEX_CONFLICT_REGISTRY"] = col(r, "SEX_CONFLICT_REGISTRY")
        d["RESIDENCE_LOCAL_NAME_AT_DEMAND"] = col(r, "RESIDENCE_LOCAL_NAME_AT_DEMAND"); d["ORIGIN_CENSUS_DATE"] = col(r, "ORIGIN_CENSUS_DATE")[:10]
        d["REQUESTED_COCHRANE_SITES"] = col(r, "REQUESTED_COCHRANE_SITES")
        d["_valid"] = d["IN_WINDOW"] == "1" and d["WAS_APPROVED"] == "1" and d["RECORD_VALID"] == "1"
        # population label: the cohorts plus the two descriptive groups the request implies
        if d["COHORT"]: pop = d["COHORT"]
        elif d["_valid"] and d["COCHRANE_PLACEMENT_RESIDENCY_UNRESOLVED"] == "1": pop = "X1 Cochrane placement, residency unresolved"
        elif d["_valid"] and d["RATED_COCHRANE"] == "1" and d["FIRST_PLACEMENT_IN_COCHRANE"] != "1" and d["RESIDENCY_FINAL"] in (NOT, AREA): pop = "X2 requested Cochrane, not placed in Cochrane, non-Town resident"
        elif d["_valid"] and d["RATED_COCHRANE"] == "1" and d["FIRST_PLACEMENT_IN_COCHRANE"] != "1" and d["RESIDENCY_FINAL"] == UNRES: pop = "X3 requested Cochrane, not placed in Cochrane, residency unresolved"
        else: pop = ""
        d["POPULATION"] = pop
        P.append(d)
    return P, have

# ── QA assertions (item 12) ───────────────────────────────────────────────────
def qa(P, expect, have, E=None):
    out = []; fail = 0
    def chk(label, n, must_zero=True):
        nonlocal fail
        ok = (n == 0) if must_zero else True
        fail += (not ok); out.append((label, n, "ok" if ok else "FAIL")); return ok
    D = [p for p in P if p["POPULATION"]]
    coh = [p for p in P if p["COHORT"]]
    chk("duplicate STUDY_ID", len(D) - len({p["STUDY_ID"] for p in D}))
    chk("duplicate PHN", len(D) - len({p["PHN"] for p in D}))
    chk("empty / placeholder PHN in deliverable", sum(1 for p in D if len(p["PHN"]) != 9 or set(p["PHN"]) == {"0"}))
    chk("death before demand inside A-D", sum(1 for p in coh if p["DEATH_DT"] and day(p["DEATH_DT"]) < p["_dem"]))
    chk("placement before demand", sum(1 for p in coh if p["_pl"] and p["_pl"] < p["_dem"]))
    chk("placement after 2026-03-31 used for A/C", sum(1 for p in coh if p["COHORT"] in ("A", "C") and p["_pl"] and p["_pl"] > FOLLOW_UP))
    chk("D with a placement observed by follow-up", sum(1 for p in coh if p["COHORT"] == "D" and p["_pl"]))
    chk("A placement not in Cochrane", sum(1 for p in coh if p["COHORT"] == "A" and p["FIRST_PLACEMENT_IN_COCHRANE"] != "1"))
    chk("C placement in Cochrane", sum(1 for p in coh if p["COHORT"] == "C" and p["FIRST_PLACEMENT_IN_COCHRANE"] == "1"))
    chk("B not (non-Town and placed in Cochrane)", sum(1 for p in coh if p["COHORT"] == "B" and not (p["RESIDENCY_FINAL"] in (NOT, AREA) and p["FIRST_PLACEMENT_IN_COCHRANE"] == "1")))
    chk("A/C/D not Town resident", sum(1 for p in coh if p["COHORT"] in ("A", "C", "D") and p["RESIDENCY_FINAL"] != TOWN))
    c = Counter(p["COHORT"] for p in coh)
    chk("A+C+D != resident demand", 0 if c["A"] + c["C"] + c["D"] == sum(1 for p in coh if p["COHORT"] in "ACD") else 1)
    dc = Counter(p["D_CLASS"][:2] for p in coh if p["COHORT"] == "D")
    chk("D1+D2+D3 != D", 0 if dc["D1"] + dc["D2"] + dc["D3"] == c["D"] else 1)
    chk("DAYS_TO_PLACEMENT populated for an unplaced person", sum(1 for p in D if p["DAYS_TO_PLACEMENT"] != "" and not p["_pl"]))
    chk("negative DAYS_TO_PLACEMENT", sum(1 for p in D if p["DAYS_TO_PLACEMENT"] != "" and p["DAYS_TO_PLACEMENT"] < 0))
    chk("implausible age (<18 or >110) at demand", sum(1 for p in D if p["AGE_AT_DEMAND"] is not None and not (18 <= p["AGE_AT_DEMAND"] <= 110)))
    chk("negative age at any event", sum(1 for p in D for k in ("AGE_AT_DEMAND", "AGE_AT_FIRST_WAITLIST", "AGE_AT_PLACEMENT") if p[k] is not None and p[k] < 0))
    chk("Strata placeholder address used to resolve residency", sum(1 for p in D if p["RESIDENCY_SOURCE"] == "STRATA_ADDRESS_H" and p["STRATA_ADDRESS_IS_PLACEHOLDER"] == "1"))
    chk("community populated from a non-deciding address (source unresolved but community set)", sum(1 for p in D if p["RESIDENCY_FINAL"] == UNRES and p["RESIDENCE_COMMUNITY_AT_DEMAND"]))
    if E is not None:
        first_ev = {(e["PHN"], e["_ad"]) for e in E}
        placed = [p for p in coh if p["_pl"]]
        chk("placed A-D people whose first placement is absent from the event table", sum(1 for p in placed if (p["PHN"], p["_pl"]) not in first_ev))
        chk("event rows flagged IS_FIRST_PLACEMENT != placed A-D people", abs(sum(1 for e in E if e["IS_FIRST_PLACEMENT"] == "1" and e["PERSON_COHORT"]) - len(placed)))
        chk("event before 2021-04-01 or after 2026-03-31", sum(1 for e in E if e["_ad"] and not (WIN_START <= e["_ad"] <= FOLLOW_UP)))
        chk("event with no PHN", sum(1 for e in E if not e["PHN"]))
    if "PATIENT_ID" in have:
        chk("deliverable person without a Strata PATIENT_ID", sum(1 for p in D if not p["PATIENT_ID"]))
    if "DOB_SOURCES_AGREE" in have:
        pass
    # the validated headline must be reproduced exactly
    got = (c["A"], c["B"], c["C"], c["D"])
    chk(f"A/B/C/D differs from accepted {expect} (got {got})", 0 if got == tuple(expect) else 1)
    return out, fail == 0

# ── summaries ─────────────────────────────────────────────────────────────────
def md_table(headers, rows):
    s = "| " + " | ".join(headers) + " |\n|" + "|".join("---" for _ in headers) + "|\n"
    for r in rows: s += "| " + " | ".join(str(x) for x in r) + " |\n"
    return s

def summaries(P, E):
    S = []
    coh = [p for p in P if p["COHORT"]]
    # demand-year
    S.append("## 1. Demand-year view — by DEMAND_FYE (fiscal year the Type A/B demand arose)\n")
    rows = []
    for y in FYES:
        ys = [p for p in coh if p["DEMAND_FYE"] == y]; c = Counter(p["COHORT"] for p in ys); dc = Counter(p["D_CLASS"][:2] for p in ys if p["COHORT"] == "D")
        rows.append([y, len(ys), c["A"], c["C"], c["D"], c["A"] + c["C"] + c["D"], dc["D1"], dc["D2"], dc["D3"], c["B"]])
    c = Counter(p["COHORT"] for p in coh); dc = Counter(p["D_CLASS"][:2] for p in coh if p["COHORT"] == "D")
    rows.append(["**Total**", len(coh), c["A"], c["C"], c["D"], c["A"] + c["C"] + c["D"], dc["D1"], dc["D2"], dc["D3"], c["B"]])
    S.append(md_table(["FYE", "unique people A+B+C+D", "A", "C", "D", "A+C+D resident demand", "D1", "D2", "D3", "B"], rows))
    S.append("D = no Type A/B placement observed in the Calgary/Edmonton Strata placement source by 31 March 2026; D1 rises to the right by censoring.\n")
    for lab, key in (("age group at demand", "AGE_GROUP_AT_DEMAND"), ("sex/gender", "SEX"), ("origin setting", "ORIGIN_SETTING")):
        vals = sorted({p[key] or "(missing)" for p in coh}, key=lambda v: (v == "(missing)", v))
        rows = [[y] + [sum(1 for p in coh if p["DEMAND_FYE"] == y and (p[key] or "(missing)") == v) for v in vals] for y in FYES]
        rows.append(["**Total**"] + [sum(1 for p in coh if (p[key] or "(missing)") == v) for v in vals])
        S.append(f"### 1.{lab} of A+B+C+D by DEMAND_FYE\n" + md_table(["FYE"] + vals, rows))
    # placement-year
    S.append("## 2. Placement-year view — by PLACEMENT_FYE (fiscal year of the FIRST observed Type A/B placement)\n")
    S.append("Person grain: each person counted once at their first placement. Event totals (all admissions) come from the placement-event table when supplied.\n")
    rows = []
    for y in FYES + ["**Total**"]:
        ys = [p for p in coh if p["_pl"] and (y == "**Total**" or p["PLACEMENT_FYE"] == y)]
        inc = [p for p in ys if p["FIRST_PLACEMENT_IN_COCHRANE"] == "1"]
        ev = [e for e in E if y == "**Total**" or e["ADMISSION_FYE"] == y] if E else None
        ev_abcd = [e for e in ev if e["PERSON_COHORT"]] if ev is not None else None
        ev_coch = [e for e in ev if e["PLACEMENT_IN_COCHRANE"] == "1"] if ev is not None else None
        rows.append([y, len(ys), (len(ev_abcd) if ev_abcd is not None else "n/a"),
                     (f"{len(ev_coch)} events / {len({e['PHN'] for e in ev_coch})} people" if ev_coch is not None else "n/a"), len(inc),
                     sum(1 for p in ys if p["FIRST_PLACEMENT_STREAM"] == "Type A"), sum(1 for p in ys if p["FIRST_PLACEMENT_STREAM"] == "Type B"),
                     sum(1 for p in inc if p["COHORT"] == "A"), sum(1 for p in inc if p["COHORT"] == "B"), sum(1 for p in inc if p["B_CATCHMENT"] == "1")])
    S.append(md_table(["FYE", "unique people placed (first placement)", "placement events of A-D people (all sites)", "Cochrane-site events, all people (events / people)", "Cochrane first placements (A+B)", "Type A", "Type B",
                       "Town residents placed in Cochrane (A)", "non-Town placed in Cochrane (B)", "of B: catchment"], rows))
    # wait time
    S.append("## 3. Time to placement — people with an observed qualifying placement only (A, B, C)\n")
    def wt(rows_, k="DAYS_TO_PLACEMENT"):
        xs = [r[k] for r in rows_ if r[k] != "" and r[k] is not None]
        if not xs: return ["—"] * 5
        return [len(xs), round(st.median(xs)), round(q(xs, .25)), round(q(xs, .75)), round(st.mean(xs), 1)]
    placed = [p for p in coh if p["_pl"]]
    H = ["group", "n", "median days", "P25", "P75", "mean"]
    rows = [["all placed"] + wt(placed)]
    for k in ("A", "B", "C"): rows.append([f"cohort {k}"] + wt([p for p in placed if p["COHORT"] == k]))
    for s_ in ("Type A", "Type B"): rows.append([s_] + wt([p for p in placed if p["FIRST_PLACEMENT_STREAM"] == s_]))
    for y in FYES: rows.append([f"demand FYE {y}"] + wt([p for p in placed if p["DEMAND_FYE"] == y]))
    S.append(md_table(H, rows))
    S.append("Waits are measured from DEMAND_DT to the first observed placement, placed people only. Later demand years are right-censored at 31 March 2026: only the shorter waits of FYE 2025-2026 demand have completed, so their medians are biased low and are not comparable with earlier years.\n")
    # approval-precedence sensitivity on wait time
    alt = [p for p in placed if p["_demA"] and p["_plA"]]
    for p in alt: p["_dalt"] = (p["_plA"] - p["_demA"]).days
    if alt:
        rows = [["all placed (primary)"] + wt(placed), ["all placed (DEMAND_DT_ALT)"] + wt(alt, "_dalt")]
        for k in ("A", "B", "C"):
            rows.append([f"cohort {k} (primary)"] + wt([p for p in placed if p["COHORT"] == k]))
            rows.append([f"cohort {k} (DEMAND_DT_ALT)"] + wt([p for p in alt if p["COHORT"] == k], "_dalt"))
        moved = sum(1 for p in alt if p["_dalt"] != p["DAYS_TO_PLACEMENT"])
        S.append(f"### 3a. Approval-precedence sensitivity (person-level coalesce(min assess, min calculated)) — {moved} of {len(alt)} placed people have a different wait\n" + md_table(H, rows))
    # demographics / residence / origin completeness
    S.append("## 4. Completeness (A+B+C+D)\n")
    rows = []
    for lab, f in (("DOB", lambda p: p["DOB"]), ("sex/gender", lambda p: p["SEX"]), ("age at demand", lambda p: p["AGE_AT_DEMAND"] is not None),
                   ("community of residence", lambda p: p["RESIDENCE_COMMUNITY_AT_DEMAND"]), ("origin setting known", lambda p: p["ORIGIN_SETTING"] not in ("Unknown", "")),
                   ("first placement site (placed only)", lambda p: (not p["_pl"]) or p["FIRST_PLACEMENT_SITE"]), ("requested site", lambda p: p["REQUESTED_SITE"])):
        n = sum(1 for p in coh if f(p)); rows.append([lab, n, len(coh) - n, pct(n, len(coh))])
    S.append(md_table(["field", "present", "missing", "% present"], rows))
    S.append("### 4a. Residence — RESIDENCY_FINAL and community, A+B+C+D\n")
    cm = Counter((p["RESIDENCY_FINAL"], p["RESIDENCE_COMMUNITY_AT_DEMAND"] or "(not in extract)") for p in coh)
    S.append(md_table(["RESIDENCY_FINAL", "community", "people"], [[a, b, n] for (a, b), n in cm.most_common(25)]))
    S.append("### 4b. Origin setting — detail and coarse category, A+B+C+D\n")
    om = Counter((p["ORIGIN_SETTING"], p["ORIGIN_SETTING_DETAIL"]) for p in coh)
    S.append(md_table(["ORIGIN_SETTING", "detail", "people"], [[a, b, n] for (a, b), n in om.most_common()]))
    S.append("Origin source: " + "; ".join(f"{k} ({v})" for k, v in Counter(p["ORIGIN_SOURCE"] for p in coh).most_common()) + "\n")
    S.append("### 4c. Descriptive groups outside A-D (reported, not in any cohort)\n")
    S.append(md_table(["POPULATION", "people"], [[k, v] for k, v in sorted(Counter(p["POPULATION"] for p in P if p["POPULATION"] and p["POPULATION"] not in "ABCD").items())]))
    return "\n".join(S)

# ── events ────────────────────────────────────────────────────────────────────
def load_events(path, salt, byphn):
    rd = csv.DictReader(open(path)); rd.fieldnames = [h.strip().upper() for h in rd.fieldnames]
    E = []
    for r in rd:
        phn = "".join(c for c in col(r, "PHN") if c.isdigit()); p = byphn.get(phn)
        d = OrderedDict(); d["STUDY_ID"] = study_id(salt, phn); d["PHN"] = phn; d["PATIENT_ID"] = col(r, "PATIENT_ID")
        ad = day(col(r, "ADMISSION_DT")); d["ADMISSION_DT"] = col(r, "ADMISSION_DT")[:10]; d["ADMISSION_FYE"] = fye(ad) or ""
        d["PLACEMENT_SITE"] = col(r, "PLACEMENT_SITE"); d["CARE_STREAM"] = col(r, "CARE_STREAM")
        d["PLACEMENT_IN_COCHRANE"] = col(r, "PLACEMENT_IN_COCHRANE", "0"); d["SOURCE_LOCATION"] = col(r, "SOURCE_LOCATION")
        d["ORIGIN_SETTING_DETAIL"] = origin_detail(d["SOURCE_LOCATION"]); d["ORIGIN_SETTING"] = COARSE[d["ORIGIN_SETTING_DETAIL"]]
        d["IS_FIRST_PLACEMENT"] = "1" if (p and p["_pl"] == ad) else "0"
        d["RESIDENCY_FINAL"] = p["RESIDENCY_FINAL"] if p else ""; d["RESIDENCY_SOURCE"] = p["RESIDENCY_SOURCE"] if p else ""
        d["RESIDENCE_CLASS"] = ("Town" if d["RESIDENCY_FINAL"] == TOWN else "Cochrane catchment" if d["RESIDENCY_FINAL"] == AREA else "non-Town" if d["RESIDENCY_FINAL"] == NOT else "unresolved") if p else "not in person table"
        d["PERSON_COHORT"] = p["COHORT"] if p else ""; d["PERSON_DEMAND_DT"] = p["DEMAND_DT"] if p else ""
        d["PERSON_POPULATION"] = p["POPULATION"] if p else ""
        d["PERSON_IN_DELIVERABLE"] = "1" if (p and p["POPULATION"]) else "0"
        d["_ad"] = ad
        E.append(d)
    return E

# ── write ─────────────────────────────────────────────────────────────────────
INTERNAL_DROP = {k for k in ()}   # everything stays in the internal file
CONSULTANT = ["STUDY_ID", "POPULATION", "COHORT", "D_CLASS", "DEMAND_DT", "DEMAND_FYE", "DEMAND_EVENT_TYPE", "FIRST_WAITLIST_APPEARANCE",
              "FIRST_APPROVAL_DT", "LAST_SEEN_ON_LIST", "ON_LIST_AT_FOLLOWUP", "AGE_AT_DEMAND", "AGE_AT_FIRST_WAITLIST", "AGE_AT_PLACEMENT",
              "AGE_GROUP_AT_DEMAND", "SEX", "RESIDENCY_FINAL", "RESIDENCE_COMMUNITY_AT_DEMAND", "COCHRANE_TOWN_FLAG", "COCHRANE_CATCHMENT_FLAG",
              "RESIDENCE_LOCAL_NAME_AT_DEMAND", "ORIGIN_SETTING", "ORIGIN_SETTING_DETAIL", "ORIGIN_SITE", "REQUESTED_SITE", "REQUESTED_CARE_STREAM", "REQUESTED_COCHRANE_FLAG",
              "N_SITES_REQUESTED", "FIRST_PLACEMENT_DT", "PLACEMENT_FYE", "FIRST_PLACEMENT_SITE", "FIRST_PLACEMENT_STREAM", "FIRST_PLACEMENT_IN_COCHRANE",
              "DAYS_TO_PLACEMENT", "DAYS_WAITING_AS_OF_FOLLOWUP"]
EVENT_CONSULTANT = ["STUDY_ID", "ADMISSION_DT", "ADMISSION_FYE", "PLACEMENT_SITE", "CARE_STREAM", "PLACEMENT_IN_COCHRANE", "ORIGIN_SETTING",
                    "ORIGIN_SETTING_DETAIL", "IS_FIRST_PLACEMENT", "RESIDENCE_CLASS", "PERSON_COHORT", "PERSON_POPULATION"]
def write_csv(path, rows, fields):
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(fields)
        for r in rows: w.writerow(["" if r.get(k) is None else r.get(k, "") for k in fields])

def main(a):
    salt = load_salt(a.salt)
    P, have = load_person(a.person, salt)
    byphn = {p["PHN"]: p for p in P}
    E = load_events(a.events, salt, byphn) if a.events else None
    checks, ok = qa(P, tuple(int(x) for x in a.expect.split(",")), have, E)
    os.makedirs(a.out, exist_ok=True)
    D = [p for p in P if p["POPULATION"]]
    coh = [p for p in P if p["COHORT"]]
    missing_fields = [f for f in ("PATIENT_ID", "DOB", "SEX", "RESIDENCE_COMMUNITY_AT_DEMAND", "RESIDENCE_POSTAL_CODE_AT_DEMAND", "ORIGIN_SETTING_RAW",
                                  "REQUESTED_SITE", "REQUESTED_CARE_STREAM", "N_SITES_REQUESTED", "PHN_PATIENT_ID_MULTIPLICITY") if f not in have and not (f == "SEX" and "GENDER" in have)]
    # reviewer pre-check
    c = Counter(p["COHORT"] for p in coh); dc = Counter(p["D_CLASS"][:2] for p in coh if p["COHORT"] == "D")
    R = ["# Reviewer pre-check — Cochrane planning deliverable\n", f"Person extract: `{os.path.basename(a.person)}`" + (f"; event extract: `{os.path.basename(a.events)}`" if a.events else "; event extract: not yet supplied") + "\n"]
    if missing_fields: R.append("**Fields not in this extract (reported as missing, never invented):** " + ", ".join(f"`{f}`" for f in missing_fields) + "\n")
    R.append(f"1. **Person-level rows:** universe {len(P):,}; deliverable population (A-D plus descriptive groups) {len(D):,}; A+B+C+D {len(coh):,}\n")
    R.append(f"2. **A/B/C/D:** {c['A']} / {c['B']} / {c['C']} / {c['D']} — resident demand {c['A']+c['C']+c['D']}\n")
    R.append(f"3. **D1/D2/D3:** {dc['D1']} / {dc['D2']} / {dc['D3']}\n")
    R.append("4. **Annual demand counts** and 5. **annual placement counts**: sections 1 and 2 of COCHRANE_SUMMARY.md"
             + (f" — event table {len(E):,} qualifying admissions, {len({e['PHN'] for e in E}):,} people; Cochrane-site events {sum(1 for e in E if e['PLACEMENT_IN_COCHRANE']=='1'):,}; events of A-D people {sum(1 for e in E if e['PERSON_COHORT']):,}" if E else " — event table not supplied") + "\n")
    R.append(f"6. **Demographic completeness (A-D):** DOB {sum(1 for p in coh if p['DOB'])}/{len(coh)} (source: " + ", ".join(f"{k or 'none'} {v}" for k, v in Counter(p['DEMOGRAPHIC_SOURCE'] for p in coh).most_common()) + f"); sex/gender {sum(1 for p in coh if p['SEX'])}/{len(coh)}"
             + (f"; DOB in both sources {sum(1 for p in coh if p['DOB_SOURCES_AGREE'] != '')}, agree {sum(1 for p in coh if p['DOB_SOURCES_AGREE'] == '1')}, disagree {sum(1 for p in coh if p['DOB_SOURCES_AGREE'] == '0')}" if "DOB_SOURCES_AGREE" in have else "")
             + (f"; registry sex conflicts {sum(1 for p in coh if p['SEX_CONFLICT_REGISTRY'] == '1')}" if "SEX_CONFLICT_REGISTRY" in have else "") + "\n")
    R.append("7. **Age distribution:** " + (", ".join(f"{k} {v}" for k, v in sorted(Counter(p['AGE_GROUP_AT_DEMAND'] or '(missing)' for p in coh).items())) ) + "\n")
    R.append(f"8. **Residence-community completeness (A-D):** {sum(1 for p in coh if p['RESIDENCE_COMMUNITY_AT_DEMAND'])}/{len(coh)}; RESIDENCY_FINAL known {sum(1 for p in coh if p['RESIDENCY_FINAL'] != UNRES)}/{len(coh)}\n")
    R.append(f"9. **Origin-setting completeness (A-D):** {sum(1 for p in coh if p['ORIGIN_SETTING'] != 'Unknown')}/{len(coh)}; source = " + "; ".join(f"{k} ({v})" for k, v in Counter(p['ORIGIN_SOURCE'] for p in coh).most_common()) + "\n")
    R.append("10. **PHN <-> Strata PATIENT_ID linkage (A-D):** " + ("; ".join(f"{k or 'unstated'} {v}" for k, v in Counter(p['PHN_PATIENT_ID_MULTIPLICITY'] for p in coh).most_common())
             + f"; universe: " + "; ".join(f"{k or 'unstated'} {v}" for k, v in Counter(p['PHN_PATIENT_ID_MULTIPLICITY'] for p in P).most_common())
             + ". PATIENT_ID -> PHN is one-to-one by construction (one IDENTIFIER1 per patient row). Canonical ID = the one carrying waitlist/admission activity, never MIN." if "PHN_PATIENT_ID_MULTIPLICITY" in have else "not in this extract — sql/13 block 1 reports it") + "\n")
    R.append("11. **Reconciliation checks:**\n\n" + md_table(["check", "n", "result"], [[l, n, s] for l, n, s in checks]))
    R.append(f"12. **Change to the validated headline caused by enrichment:** " + ("none — A/B/C/D reproduced exactly" if ok else "**STOP — see failed checks above**") + "\n")
    open(os.path.join(a.out, "REVIEWER_PRECHECK.md"), "w").write("\n".join(R))
    if not ok:
        print("\n".join(R)); sys.exit("QA FAILED — no deliverable files written. Diagnose the extract; do not accept new numbers.")
    # deliverable files
    internal_fields = [k for k in D[0].keys() if not k.startswith("_")]
    write_csv(os.path.join(a.out, "COCHRANE_DEMAND_INTERNAL_QA.csv"), D, internal_fields)
    write_csv(os.path.join(a.out, "COCHRANE_DEMAND_CONSULTANT.csv"), D, CONSULTANT)
    if E:
        Ev = [e for e in E if e["PLACEMENT_IN_COCHRANE"] == "1" or e["PERSON_IN_DELIVERABLE"] == "1"]
        write_csv(os.path.join(a.out, "COCHRANE_PLACEMENT_ACTIVITY_INTERNAL.csv"), Ev, [k for k in E[0].keys() if not k.startswith("_")])
        write_csv(os.path.join(a.out, "COCHRANE_PLACEMENT_ACTIVITY_CONSULTANT.csv"), Ev, EVENT_CONSULTANT)
    head = "# Cochrane continuing-care demand — summary tables\n\nTwo time bases are used and never mixed: **DEMAND_FYE** (year the Type A/B demand arose) and **PLACEMENT_FYE** (year of the first observed placement). Person grain unless a column says events.\n\n"
    open(os.path.join(a.out, "COCHRANE_SUMMARY.md"), "w").write(head + summaries(P, E))
    print("\n".join(R)); print(f"\nwritten to {a.out}/: " + ", ".join(sorted(os.listdir(a.out))))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--person", required=True); ap.add_argument("--events"); ap.add_argument("--salt", default="secrets/study_id_salt.txt")
    ap.add_argument("--expect", default="89,148,192,69"); ap.add_argument("--out", default="deliverables")
    main(ap.parse_args())
