#!/usr/bin/env python3
"""
Build the final Cochrane planning deliverable from the deliverable extracts.

Three grains, kept apart:
  PERSON    one row per person (unique demand)            sql/14  --person
  WAITLIST  one row per waitlist spell (list activity)     sql/16  --waitlist
  EVENT     one row per qualifying Type A/B admission      sql/15  --events

Optional: --epic-demo (sql/17) Epic DOB/sex, used ONLY to review Strata-vs-
Registry DOB conflicts. --salt file holds the project STUDY_ID salt (created on
first run; keep it outside the repository, never change it). --expect is the
accepted A,B,C,D; the build STOPS if the extract disagrees.

Outputs (--out, git-ignored)
  COCHRANE_DEMAND_INTERNAL_QA.csv          person grain, QA population (1,139), all identifiers
  COCHRANE_DEMAND_CONSULTANT.csv           person grain, IN_CONSULTANT_SCOPE = 1, STUDY_ID only
  COCHRANE_WAITLIST_ACTIVITY_INTERNAL/_CONSULTANT.csv   spell grain
  COCHRANE_PLACEMENT_ACTIVITY_INTERNAL/_CONSULTANT.csv  event grain
  COCHRANE_SUMMARY.md                      FY2022-FY2026 tables, demand-year and placement-year apart
  REVIEWER_PRECHECK.md                     the QA results the reviewer asked for before anything is external

Rules carried from the validated methodology
  · COHORT and D_CLASS come from the extract as validated by analysis/07; never recomputed here.
  · Ages are completed years at the event date (birthday test), never at today's date.
  · DAYS_TO_PLACEMENT is NULL without an observed placement by 31 March 2026;
    DAYS_WAITING_AS_OF_FOLLOWUP is a separate, labelled censoring field (D1 only).
  · Community comes only from the address that decided RESIDENCY_FINAL, with the
    reference fiscal year / version date carried so a registry year is never
    presented as an exact address on the demand date.
  · Origin = setting at FIRST list entry; ties on that day are reported, never broken.
  · Requested facility = observed frequency of ratings, never "preferred".
  · Occupancy / building flags are QA only.
"""
import csv, sys, os, argparse, hmac, hashlib, secrets, datetime as dt, statistics as st
from collections import Counter, defaultdict, OrderedDict

WIN_START, WIN_END, FOLLOW_UP = dt.date(2021,4,1), dt.date(2026,4,1), dt.date(2026,3,31)
TOWN, AREA, NOT, UNRES = "Town of Cochrane", "Cochrane catchment", "Not a Cochrane-area resident", "UNRESOLVED"
FYES = [2022, 2023, 2024, 2025, 2026]
COCHRANE_SITES = {"CAL - Bethany Cochrane LTC_", "CAL - Hawthorne SL4_", "CAL - Hawthorne SL4D"}

def day(s):
    s = (s or "").strip(); return dt.datetime.strptime(s[:10], "%Y-%m-%d").date() if s else None
def col(r, k, default=""): return (r.get(k) or default).strip()
def fye(d): return None if d is None else (d.year + 1 if d.month >= 4 else d.year)
def age_at(dob, d):
    """completed years: birthday test, not DATEDIFF('year')"""
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
def rclass(res): return "Town" if res == TOWN else "Cochrane catchment" if res == AREA else "non-Town" if res == NOT else "unresolved"

# ── origin-setting normalisation (reviewer categories) ────────────────────────
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
    if any(k in u for k in ("ASSISTED LIVING", "SL4", "DSL", "SUPPORTIVE LIVING", "DAL")): return "Supportive / assisted living"
    if any(k in u for k in ("LTC", "LONG TERM CARE", "CAPITAL CARE", "CAREWEST", "NURSING")): return "Long-term care"
    if "ZONE" in u: return "Other (zone-level)"
    return "Other"
COARSE = {"Own home": "Community", "Emergency department": "Acute Care", "Acute hospital": "Acute Care",
          "Sub-acute / transition / rehab": "Acute Care", "Lodge": "Lodge",
          "Continuing-care ALC bed": "Assisted Living or Other Continuing Care", "Supportive / assisted living": "Assisted Living or Other Continuing Care",
          "Long-term care": "Assisted Living or Other Continuing Care", "Hospice / palliative": "Assisted Living or Other Continuing Care",
          "Out of province": "Out of Province", "Out of region": "Other", "Other (zone-level)": "Other", "Other": "Other", "Unknown": "Unknown"}
def normalise_origin(raw, lst, conflict):
    """single value -> its category. Tied values -> the category if every value maps to the same one, else Unknown."""
    if conflict and lst:
        cats = {COARSE[origin_detail(v.strip())] for v in lst.split("|") if v.strip()}
        dets = {origin_detail(v.strip()) for v in lst.split("|") if v.strip()}
        if len(cats) == 1: return cats.pop(), (dets.pop() if len(dets) == 1 else "tied values, same category"), "tied values agree on category"
        return "Unknown", "tied values, different categories", "tied values disagree; not classified"
    d = origin_detail(raw); return COARSE[d], d, ""

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
def study_id(salt, phn): return "CD-" + hmac.new(salt.encode(), phn.encode(), hashlib.sha256).hexdigest()[:12].upper()

def read(path):
    rd = csv.DictReader(open(path)); rd.fieldnames = [h.strip().upper() for h in rd.fieldnames]
    return [{k: (v or "").strip() for k, v in r.items()} for r in rd]

# ── person grain ──────────────────────────────────────────────────────────────
def load_person(path, salt, epic):
    rows = read(path); have = set(rows[0]) if rows else set(); P = []
    for r in rows:
        phn = "".join(c for c in col(r, "PHN") if c.isdigit()); d = OrderedDict()
        d["STUDY_ID"] = study_id(salt, phn) if phn else ""; d["PHN"] = phn; d["PATIENT_ID"] = col(r, "PATIENT_ID")
        d["COHORT"] = col(r, "COHORT"); d["D_CLASS"] = col(r, "D_CLASS")
        d["_dem"] = day(col(r, "DEMAND_DT")); d["_demA"] = day(col(r, "DEMAND_DT_ALT"))
        d["DEMAND_DT"] = col(r, "DEMAND_DT")[:10]; d["DEMAND_FYE"] = fye(d["_dem"]) or ""; d["DEMAND_EVENT_TYPE"] = col(r, "DEMAND_EVENT_TYPE")
        d["FIRST_WAITLIST_APPEARANCE"] = col(r, "FIRST_LIST_APPEARANCE")[:10]; d["FIRST_APPROVAL_DT"] = col(r, "FIRST_APPROVAL_DT")[:10]
        d["LAST_SEEN_ON_LIST"] = col(r, "LAST_SEEN_ON_LIST")[:10]; d["ON_LIST_AT_FOLLOWUP"] = col(r, "ON_LIST_AT_FOLLOWUP", "0")
        d["RATED_COCHRANE"] = col(r, "RATED_COCHRANE", "0")
        # rated / requested (observed frequency, never preference)
        d["MOST_FREQUENTLY_OBSERVED_RATED_SITE"] = col(r, "MOST_FREQUENTLY_OBSERVED_RATED_SITE") or col(r, "REQUESTED_SITE") or ("(no site rated)" if col(r, "N_SITES_REQUESTED") == "0" else "")
        d["REQUESTED_CARE_STREAM"] = col(r, "REQUESTED_CARE_STREAM"); d["N_SITES_REQUESTED"] = col(r, "N_SITES_REQUESTED")
        d["REQUESTED_COCHRANE_FLAG"] = col(r, "REQUESTED_COCHRANE_FLAG") or d["RATED_COCHRANE"]; d["REQUESTED_COCHRANE_SITES"] = col(r, "REQUESTED_COCHRANE_SITES")
        # demographics: DOB (Strata primary, Registry fallback) and SEX (Registry only); sources split
        dob = day(col(r, "DOB")); d["DOB"] = col(r, "DOB")[:10]; d["_dob"] = dob
        d["DOB_SOURCE"] = col(r, "DEMOGRAPHIC_SOURCE"); d["SEX"] = col(r, "SEX"); d["SEX_SOURCE"] = "REGISTRY" if d["SEX"] else ""
        d["DOB_STRATA"] = col(r, "DOB_STRATA")[:10]; d["DOB_REGISTRY"] = col(r, "DOB_REGISTRY")[:10]
        ds, dr = day(d["DOB_STRATA"]), day(d["DOB_REGISTRY"])
        d["DOB_DIFFERENCE_DAYS"] = abs((ds - dr).days) if (ds and dr) else ""
        d["DOB_CONFLICT_FLAG"] = "1" if (ds and dr and ds != dr) else "0"
        d["DOB_CONFLICT_OVER_1Y"] = "1" if (ds and dr and abs((ds - dr).days) > 366) else "0"
        e = epic.get(phn) if epic else None
        d["DOB_EPIC"] = e["EPIC_DOB"][:10] if e else ""; d["SEX_EPIC"] = (e["EPIC_SEX"] if e else "")
        de = day(d["DOB_EPIC"])
        d["DOB_EPIC_AGREES_WITH"] = ("STRATA" if (de and ds and de == ds) else "") + ("+" if (de and ds and de == ds and dr and de == dr) else "") + ("REGISTRY" if (de and dr and de == dr) else "") if de else ""
        d["SEX_CONFLICT_REGISTRY"] = col(r, "SEX_CONFLICT_REGISTRY")
        d["_pl"] = day(col(r, "FIRST_PLACEMENT_DT")); d["_fw"] = day(col(r, "FIRST_LIST_APPEARANCE")); d["_plA"] = day(col(r, "FIRST_PLACEMENT_DT_ALT"))
        d["AGE_AT_DEMAND"] = age_at(dob, d["_dem"]); d["AGE_AT_FIRST_WAITLIST"] = age_at(dob, d["_fw"]); d["AGE_AT_PLACEMENT"] = age_at(dob, d["_pl"])
        d["AGE_GROUP_AT_DEMAND"] = age_band(d["AGE_AT_DEMAND"])
        d["AGE_BAND_DEPENDS_ON_DOB_SOURCE"] = "1" if (ds and dr and age_band(age_at(ds, d["_dem"])) != age_band(age_at(dr, d["_dem"]))) else "0"
        # residence
        d["RESIDENCY_FINAL"] = col(r, "RESIDENCY_FINAL") or col(r, "RESIDENCY_LATEST"); d["RESIDENCY_SOURCE"] = col(r, "RESIDENCY_SOURCE")
        d["RESIDENCE_CLASS"] = rclass(d["RESIDENCY_FINAL"])
        d["RESIDENCE_POSTAL_CODE_AT_DEMAND"] = col(r, "RESIDENCE_POSTAL_CODE_AT_DEMAND")
        comm = col(r, "RESIDENCE_COMMUNITY_AT_DEMAND"); src_lab = "Alberta postal geography (Statistics Canada CSD)" if comm else ""
        if not comm and d["RESIDENCY_SOURCE"] == "STRATA_ADDRESS_H":
            city = col(r, "STRATA_CITY_AT_DEMAND")
            if city: comm = city.upper() + " (Strata city; postal code outside the Alberta lookup)"; src_lab = "Strata city_name (labelled fallback)"
            elif d["RESIDENCE_POSTAL_CODE_AT_DEMAND"] and d["RESIDENCE_POSTAL_CODE_AT_DEMAND"][0].upper() != "T":
                comm = "Outside Alberta (postal " + d["RESIDENCE_POSTAL_CODE_AT_DEMAND"][:3].upper() + ")"; src_lab = "postal prefix only"
        d["RESIDENCE_COMMUNITY_AT_DEMAND"] = comm; d["RESIDENCE_COMMUNITY_SOURCE"] = src_lab
        d["RESIDENCE_LOCAL_NAME_AT_DEMAND"] = col(r, "RESIDENCE_LOCAL_NAME_AT_DEMAND")
        if d["RESIDENCY_SOURCE"] == "REGISTRY":
            d["RESIDENCE_REFERENCE_TYPE"] = "Registry address of fiscal year (not an exact date)"; d["RESIDENCE_REFERENCE_FYE"] = col(r, "RESIDENCE_REFERENCE_FYE"); d["RESIDENCE_REFERENCE_DATE"] = ""
        elif d["RESIDENCY_SOURCE"] == "STRATA_ADDRESS_H":
            d["RESIDENCE_REFERENCE_TYPE"] = "Strata address version effective on the demand date"; d["RESIDENCE_REFERENCE_FYE"] = ""; d["RESIDENCE_REFERENCE_DATE"] = col(r, "STRATA_ADDRESS_EFFECTIVE_FROM")[:10]
        else: d["RESIDENCE_REFERENCE_TYPE"] = ""; d["RESIDENCE_REFERENCE_FYE"] = ""; d["RESIDENCE_REFERENCE_DATE"] = ""
        d["COCHRANE_TOWN_FLAG"] = "1" if d["RESIDENCY_FINAL"] == TOWN else "0"; d["COCHRANE_CATCHMENT_FLAG"] = "1" if d["RESIDENCY_FINAL"] == AREA else "0"
        d["RESIDENCY_EVIDENCE"] = col(r, "RESIDENCY_EVIDENCE")
        # origin at FIRST list entry, tie-audited (provisional on extracts that predate the audit columns)
        if "N_ORIGIN_LOCATIONS_AT_ENTRY" in have:
            raw = col(r, "ORIGIN_SETTING_RAW"); lst = col(r, "ORIGIN_LOCATION_LIST"); n = col(r, "N_ORIGIN_LOCATIONS_AT_ENTRY") or "1"
            conflict = col(r, "ORIGIN_CONFLICT_FLAG", "0") == "1"; src = col(r, "ORIGIN_SOURCE")
        else:
            raw = col(r, "SETTING_AT_LIST_ENTRY"); lst = raw; n = "1"; conflict = False
            src = "PROVISIONAL: first list appearance, ties broken by min_by (sql/14 re-run supplies the audited value)"
        d["ORIGIN_SETTING_RAW"] = raw; d["ORIGIN_LOCATION_LIST"] = lst; d["N_ORIGIN_LOCATIONS_AT_ENTRY"] = n; d["ORIGIN_CONFLICT_FLAG"] = "1" if conflict else "0"
        d["ORIGIN_SETTING"], d["ORIGIN_SETTING_DETAIL"], d["ORIGIN_CONFLICT_NOTE"] = normalise_origin(raw, lst, conflict)
        d["ORIGIN_SITE"] = raw or lst; d["ORIGIN_SOURCE"] = src; d["ORIGIN_ENTRY_CENSUS_DATE"] = col(r, "ORIGIN_ENTRY_CENSUS_DATE")[:10]
        d["LOCATION_NEAREST_DEMAND_RAW"] = col(r, "LOCATION_NEAREST_DEMAND_RAW")
        # placement
        d["FIRST_PLACEMENT_DT"] = col(r, "FIRST_PLACEMENT_DT")[:10]; d["PLACEMENT_FYE"] = fye(d["_pl"]) or ""
        d["FIRST_PLACEMENT_SITE"] = col(r, "FIRST_PLACEMENT_SITE"); d["FIRST_PLACEMENT_STREAM"] = col(r, "FIRST_PLACEMENT_STREAM")
        d["FIRST_PLACEMENT_IN_COCHRANE"] = col(r, "FIRST_PLACEMENT_IN_COCHRANE", "0")
        d["DAYS_TO_PLACEMENT"] = (d["_pl"] - d["_dem"]).days if (d["_pl"] and d["_dem"]) else ""
        d["DAYS_TO_PLACEMENT_ALT"] = (d["_plA"] - d["_demA"]).days if (d["_plA"] and d["_demA"]) else ""
        d["DAYS_WAITING_AS_OF_FOLLOWUP"] = ((FOLLOW_UP - d["_dem"]).days if (not d["_pl"] and d["_dem"] and d["ON_LIST_AT_FOLLOWUP"] == "1") else "")
        d["FIRST_PLACEMENT_AFTER_FOLLOWUP"] = col(r, "FIRST_PLACEMENT_AFTER_FOLLOWUP")[:10]; d["DEATH_DT"] = col(r, "DEATH_DT")[:10]
        # gating and QA
        d["IN_WINDOW"] = col(r, "IN_WINDOW", "1"); d["WAS_APPROVED"] = col(r, "WAS_APPROVED", "1"); d["RECORD_VALID"] = col(r, "RECORD_VALID", "1")
        d["STRATA_ADDRESS_IS_PLACEHOLDER"] = col(r, "STRATA_ADDRESS_IS_PLACEHOLDER"); d["STRATA_RESIDENCY"] = col(r, "STRATA_RESIDENCY")
        d["COCHRANE_PLACEMENT_RESIDENCY_UNRESOLVED"] = col(r, "COCHRANE_PLACEMENT_RESIDENCY_UNRESOLVED", "0"); d["B_CATCHMENT"] = col(r, "B_CATCHMENT", "0")
        d["COCHRANE_FACING"] = col(r, "COCHRANE_FACING", "1")
        d["PHN_PATIENT_ID_MULTIPLICITY"] = col(r, "PHN_PATIENT_ID_MULTIPLICITY"); d["PATIENT_ID_ALL"] = col(r, "PATIENT_ID_ALL"); d["N_PATIENT_IDS"] = col(r, "N_PATIENT_IDS")
        d["PHN_IS_AUTOGEN_ANY"] = col(r, "PHN_IS_AUTOGEN_ANY")
        d["_valid"] = d["IN_WINDOW"] == "1" and d["WAS_APPROVED"] == "1" and d["RECORD_VALID"] == "1"
        if d["COHORT"]: pop = d["COHORT"]
        elif d["_valid"] and d["COCHRANE_PLACEMENT_RESIDENCY_UNRESOLVED"] == "1": pop = "X1 Cochrane placement, residency unresolved"
        elif d["_valid"] and d["REQUESTED_COCHRANE_FLAG"] == "1" and d["FIRST_PLACEMENT_IN_COCHRANE"] != "1" and d["RESIDENCY_FINAL"] in (NOT, AREA): pop = "X2 requested Cochrane, not placed in Cochrane, non-Town resident"
        elif d["_valid"] and d["REQUESTED_COCHRANE_FLAG"] == "1" and d["FIRST_PLACEMENT_IN_COCHRANE"] != "1" and d["RESIDENCY_FINAL"] == UNRES: pop = "X3 requested Cochrane, not placed in Cochrane, residency unresolved"
        else: pop = ""
        d["POPULATION"] = pop
        P.append(d)
    return P, have

def scope_flags(P, E):
    """IN_CONSULTANT_SCOPE from the literal request: Town residence OR any Cochrane/Hawthorne rated site OR an actual Type A/B placement in a Cochrane facility."""
    coch_ev = {e["PHN"] for e in E if e["PLACEMENT_IN_COCHRANE"] == "1"} if E else set()
    for p in P:
        p["ANY_COCHRANE_PLACEMENT_EVENT"] = "1" if p["PHN"] in coch_ev else ""
        town = p["RESIDENCY_FINAL"] == TOWN; req = p["REQUESTED_COCHRANE_FLAG"] == "1"
        placed = p["FIRST_PLACEMENT_IN_COCHRANE"] == "1" or p["PHN"] in coch_ev
        p["SCOPE_REASON"] = "+".join(k for k, v in (("Town resident", town), ("rated Cochrane site", req), ("placed in Cochrane facility", placed)) if v)
        p["IN_CONSULTANT_SCOPE"] = "1" if (p["_valid"] and (town or req or placed)) else "0"
        p["SCOPE_EXCLUDED_BY_GATE"] = "1" if ((town or req or placed) and not p["_valid"]) else "0"
        if p["IN_CONSULTANT_SCOPE"] == "1" and not p["POPULATION"]:
            p["POPULATION"] = "X4 later Type A/B move into a Cochrane facility, first placed elsewhere, no Cochrane rating"

# ── QA assertions ─────────────────────────────────────────────────────────────
def qa(P, expect, have, E=None, W=None):
    out = []; fail = 0
    def chk(label, n):
        nonlocal fail
        ok = n == 0; fail += (not ok); out.append((label, n, "ok" if ok else "FAIL")); return ok
    D = [p for p in P if p["IN_CONSULTANT_SCOPE"] == "1"]; coh = [p for p in P if p["COHORT"]]
    chk("duplicate STUDY_ID (QA population)", len(P) - len({p["STUDY_ID"] for p in P})); chk("duplicate PHN (QA population)", len(P) - len({p["PHN"] for p in P}))
    chk("empty / placeholder PHN in consultant scope", sum(1 for p in D if len(p["PHN"]) != 9 or set(p["PHN"]) == {"0"}))
    chk("cohort member not in consultant scope", sum(1 for p in coh if p["IN_CONSULTANT_SCOPE"] != "1"))
    chk("death before demand inside A-D", sum(1 for p in coh if p["DEATH_DT"] and day(p["DEATH_DT"]) < p["_dem"]))
    chk("placement before demand", sum(1 for p in coh if p["_pl"] and p["_pl"] < p["_dem"]))
    chk("placement after 2026-03-31 used for A/C", sum(1 for p in coh if p["COHORT"] in ("A", "C") and p["_pl"] and p["_pl"] > FOLLOW_UP))
    chk("D with a placement observed by follow-up", sum(1 for p in coh if p["COHORT"] == "D" and p["_pl"]))
    chk("A placement not in Cochrane", sum(1 for p in coh if p["COHORT"] == "A" and p["FIRST_PLACEMENT_IN_COCHRANE"] != "1"))
    chk("C placement in Cochrane", sum(1 for p in coh if p["COHORT"] == "C" and p["FIRST_PLACEMENT_IN_COCHRANE"] == "1"))
    chk("B not (non-Town and placed in Cochrane)", sum(1 for p in coh if p["COHORT"] == "B" and not (p["RESIDENCY_FINAL"] in (NOT, AREA) and p["FIRST_PLACEMENT_IN_COCHRANE"] == "1")))
    chk("A/C/D not Town resident", sum(1 for p in coh if p["COHORT"] in ("A", "C", "D") and p["RESIDENCY_FINAL"] != TOWN))
    c = Counter(p["COHORT"] for p in coh); dc = Counter(p["D_CLASS"][:2] for p in coh if p["COHORT"] == "D")
    chk("D1+D2+D3 != D", 0 if dc["D1"] + dc["D2"] + dc["D3"] == c["D"] else 1)
    chk("DAYS_TO_PLACEMENT populated for an unplaced person", sum(1 for p in D if p["DAYS_TO_PLACEMENT"] != "" and not p["_pl"]))
    chk("negative DAYS_TO_PLACEMENT", sum(1 for p in D if p["DAYS_TO_PLACEMENT"] != "" and p["DAYS_TO_PLACEMENT"] < 0))
    chk("implausible age (<18 or >110) at demand", sum(1 for p in D if p["AGE_AT_DEMAND"] is not None and not (18 <= p["AGE_AT_DEMAND"] <= 110)))
    chk("negative age at any event", sum(1 for p in D for k in ("AGE_AT_DEMAND", "AGE_AT_FIRST_WAITLIST", "AGE_AT_PLACEMENT") if p[k] is not None and p[k] < 0))
    chk("age at placement < age at demand", sum(1 for p in D if p["AGE_AT_PLACEMENT"] is not None and p["AGE_AT_DEMAND"] is not None and p["AGE_AT_PLACEMENT"] < p["AGE_AT_DEMAND"]))
    chk("Strata placeholder address used to resolve residency", sum(1 for p in D if p["RESIDENCY_SOURCE"] == "STRATA_ADDRESS_H" and p["STRATA_ADDRESS_IS_PLACEHOLDER"] == "1"))
    chk("community set while residency unresolved", sum(1 for p in D if p["RESIDENCY_FINAL"] == UNRES and p["RESIDENCE_COMMUNITY_AT_DEMAND"]))
    chk("origin conflict resolved by arbitrary choice (raw set while tied)", sum(1 for p in D if p["ORIGIN_CONFLICT_FLAG"] == "1" and p["ORIGIN_SETTING_RAW"]))
    if "PATIENT_ID" in have: chk("cohort member without a Strata PATIENT_ID", sum(1 for p in coh if not p["PATIENT_ID"]))
    if E is not None:
        first_ev = {(e["PHN"], e["_ad"]) for e in E}; placed = [p for p in coh if p["_pl"]]
        chk("placed A-D person whose first placement is absent from the event table", sum(1 for p in placed if (p["PHN"], p["_pl"]) not in first_ev))
        chk("event rows flagged IS_FIRST_PLACEMENT != placed A-D people", abs(sum(1 for e in E if e["IS_FIRST_PLACEMENT"] == "1" and e["PERSON_COHORT"]) - len(placed)))
        chk("event outside 2021-04-01..2026-03-31", sum(1 for e in E if e["_ad"] and not (WIN_START <= e["_ad"] <= FOLLOW_UP))); chk("event with no PHN", sum(1 for e in E if not e["PHN"]))
    if W is not None:
        byp = defaultdict(list)
        for w in W: byp[w["PHN"]].append(w)
        listed = [p for p in coh if p["_fw"]]
        chk("A-D person with a waitlist record but no spell in the waitlist table", sum(1 for p in listed if p["PHN"] not in byp))
        chk("A-D person whose first spell entry != FIRST_WAITLIST_APPEARANCE", sum(1 for p in listed if p["PHN"] in byp and min(w["_entry"] for w in byp[p["PHN"]]) != p["_fw"]))
        chk("waitlist spell outside the window", sum(1 for w in W if not (WIN_START <= w["_entry"] < WIN_END)))
    got = (c["A"], c["B"], c["C"], c["D"]); chk(f"A/B/C/D differs from accepted {expect} (got {got})", 0 if got == tuple(expect) else 1)
    return out, fail == 0

# ── other grains ──────────────────────────────────────────────────────────────
def load_events(path, salt, byphn):
    E = []
    for r in read(path):
        phn = "".join(c for c in col(r, "PHN") if c.isdigit()); p = byphn.get(phn); d = OrderedDict()
        d["STUDY_ID"] = study_id(salt, phn); d["PHN"] = phn; d["PATIENT_ID"] = col(r, "PATIENT_ID"); d["ADMISSION_NOTICE_ID"] = col(r, "ADMISSION_NOTICE_ID")
        ad = day(col(r, "ADMISSION_DT")); d["ADMISSION_DT"] = col(r, "ADMISSION_DT")[:10]; d["PLACEMENT_FYE"] = fye(ad) or ""
        d["PLACEMENT_SITE"] = col(r, "PLACEMENT_SITE"); d["CARE_STREAM"] = col(r, "CARE_STREAM"); d["PLACEMENT_IN_COCHRANE"] = col(r, "PLACEMENT_IN_COCHRANE", "0")
        d["SOURCE_LOCATION"] = col(r, "SOURCE_LOCATION"); d["ORIGIN_SETTING_DETAIL"] = origin_detail(d["SOURCE_LOCATION"]); d["ORIGIN_SETTING"] = COARSE[d["ORIGIN_SETTING_DETAIL"]]
        d["DISCHARGE_DT"] = col(r, "DISCHARGE_DT")[:10]; d["DISCHARGE_DESTINATION"] = col(r, "DISCHARGE_DESTINATION"); d["EVENT_SEQ_FOR_PERSON"] = col(r, "EVENT_SEQ_FOR_PERSON")
        d["IS_FIRST_PLACEMENT"] = "1" if (p and p["_pl"] == ad) else "0"
        d["RESIDENCY_FINAL"] = p["RESIDENCY_FINAL"] if p else ""; d["RESIDENCE_CLASS"] = rclass(p["RESIDENCY_FINAL"]) if p else "not in person table"
        d["RESIDENCE_COMMUNITY_AT_DEMAND"] = p["RESIDENCE_COMMUNITY_AT_DEMAND"] if p else ""
        d["PERSON_COHORT"] = p["COHORT"] if p else ""; d["PERSON_POPULATION"] = p["POPULATION"] if p else ""; d["PERSON_DEMAND_DT"] = p["DEMAND_DT"] if p else ""
        d["_ad"] = ad; E.append(d)
    return E
def load_waitlist(path, salt, byphn):
    W = []
    for r in read(path):
        phn = "".join(c for c in col(r, "PHN") if c.isdigit()); p = byphn.get(phn); d = OrderedDict()
        d["STUDY_ID"] = study_id(salt, phn); d["PHN"] = phn; d["PATIENT_ID"] = col(r, "PATIENT_ID"); d["PATIENT_TRANSFER_ID"] = col(r, "PATIENT_TRANSFER_ID"); d["SPELL_NO"] = col(r, "SPELL_NO")
        en = day(col(r, "LIST_ENTRY_DT")); d["LIST_ENTRY_DT"] = col(r, "LIST_ENTRY_DT")[:10]; d["LIST_ENTRY_FYE"] = fye(en) or ""
        d["LIST_LAST_SEEN_DT"] = col(r, "LIST_LAST_SEEN_DT")[:10]; d["DAYS_OBSERVED"] = col(r, "DAYS_OBSERVED")
        d["CARE_STREAM_AT_ENTRY"] = col(r, "CARE_STREAM_AT_ENTRY"); d["CARE_TYPE_AT_ENTRY"] = col(r, "CARE_TYPE_AT_ENTRY")
        loc = col(r, "LOCATION_AT_ENTRY"); lst = col(r, "LOCATION_LIST_AT_ENTRY"); n = col(r, "N_LOCATIONS_AT_ENTRY") or "1"
        d["LOCATION_AT_ENTRY"] = loc; d["N_LOCATIONS_AT_ENTRY"] = n; d["LOCATION_LIST_AT_ENTRY"] = lst; d["ORIGIN_CONFLICT_FLAG"] = "1" if (n not in ("", "1")) else "0"
        d["ORIGIN_SETTING"], d["ORIGIN_SETTING_DETAIL"], _ = normalise_origin(loc, lst, d["ORIGIN_CONFLICT_FLAG"] == "1")
        d["FIRST_APPROVED_DT_IN_SPELL"] = col(r, "FIRST_APPROVED_DT_IN_SPELL")[:10]; d["RATED_COCHRANE_IN_SPELL"] = col(r, "RATED_COCHRANE_IN_SPELL", "0")
        d["LEFT_TRUNCATED"] = col(r, "LEFT_TRUNCATED", "0"); d["ON_LIST_AT_FOLLOWUP"] = col(r, "ON_LIST_AT_FOLLOWUP", "0"); d["SPELL_SEQ_FOR_PERSON"] = col(r, "SPELL_SEQ_FOR_PERSON")
        d["RESIDENCE_CLASS"] = rclass(p["RESIDENCY_FINAL"]) if p else "not in person table"; d["PERSON_COHORT"] = p["COHORT"] if p else ""
        d["PERSON_IN_CONSULTANT_SCOPE"] = p["IN_CONSULTANT_SCOPE"] if p else "0"
        d["_entry"] = en; W.append(d)
    return W

# ── summaries ─────────────────────────────────────────────────────────────────
def md_table(headers, rows):
    s = "| " + " | ".join(headers) + " |\n|" + "|".join("---" for _ in headers) + "|\n"
    for r in rows: s += "| " + " | ".join(str(x) for x in r) + " |\n"
    return s
def wt(rows_, k="DAYS_TO_PLACEMENT"):
    xs = [r[k] for r in rows_ if r[k] != "" and r[k] is not None]
    if not xs: return ["—"] * 5
    return [len(xs), round(st.median(xs)), round(q(xs, .25)), round(q(xs, .75)), round(st.mean(xs), 1)]
def by_fye(items, key, fn):
    rows = []
    for y in FYES + ["**Total**"]:
        ys = [i for i in items if y == "**Total**" or i[key] == y]; rows.append([y] + fn(ys))
    return rows

def summaries(P, E, W):
    S = []; coh = [p for p in P if p["COHORT"]]; D = [p for p in P if p["IN_CONSULTANT_SCOPE"] == "1"]
    S.append("## 1. Demand-year view — by DEMAND_FYE (the fiscal year the Type A/B demand arose). Person grain.\n")
    S.append(md_table(["FYE", "A+B+C+D people", "A", "C", "D", "A+C+D resident demand", "D1", "D2", "D3", "B", "consultant-scope people (all)"],
        by_fye(coh, "DEMAND_FYE", lambda ys: [len(ys)] + [Counter(p["COHORT"] for p in ys)[k] for k in "ACD"] + [sum(1 for p in ys if p["COHORT"] in "ACD")]
               + [Counter(p["D_CLASS"][:2] for p in ys if p["COHORT"] == "D")[k] for k in ("D1", "D2", "D3")] + [Counter(p["COHORT"] for p in ys)["B"]]
               + [sum(1 for p in D if p["DEMAND_FYE"] == (ys[0]["DEMAND_FYE"] if ys else None)) if ys and ys[0]["DEMAND_FYE"] in FYES and len({p["DEMAND_FYE"] for p in ys}) == 1 else len(D)])))
    S.append("D = no Type A/B placement observed in the Calgary/Edmonton Strata placement source by 31 March 2026; D1 rises to the right by censoring.\n")
    for lab, key in (("Age band at demand", "AGE_GROUP_AT_DEMAND"), ("Sex (Registry)", "SEX"), ("Origin setting at first list entry", "ORIGIN_SETTING"), ("Residence class", "RESIDENCE_CLASS")):
        vals = sorted({p[key] or "(missing)" for p in D}, key=lambda v: (v == "(missing)", v))
        S.append(f"### 1.{lab} — consultant-scope people by DEMAND_FYE\n" + md_table(["FYE"] + vals,
            by_fye(D, "DEMAND_FYE", lambda ys: [sum(1 for p in ys if (p[key] or "(missing)") == v) for v in vals])))
    # waitlist-year
    S.append("## 2. Waitlist-year view — by LIST_ENTRY_FYE (fiscal year a waitlist spell began). Spell grain, consultant-scope people.\n")
    if W:
        Ws = [w for w in W if w["PERSON_IN_CONSULTANT_SCOPE"] == "1"]
        S.append(md_table(["FYE", "spells", "unique people entering the list", "Type A spells", "Type B spells", "spells rating a Cochrane site", "Town residents", "non-Town", "left-truncated (already listed at 2021-04-01)"],
            by_fye(Ws, "LIST_ENTRY_FYE", lambda ys: [len(ys), len({w["PHN"] for w in ys}), sum(1 for w in ys if w["CARE_STREAM_AT_ENTRY"] == "Type A"), sum(1 for w in ys if w["CARE_STREAM_AT_ENTRY"] == "Type B"),
                sum(1 for w in ys if w["RATED_COCHRANE_IN_SPELL"] == "1"), sum(1 for w in ys if w["RESIDENCE_CLASS"] == "Town"), sum(1 for w in ys if w["RESIDENCE_CLASS"] == "non-Town"), sum(1 for w in ys if w["LEFT_TRUNCATED"] == "1")])))
        S.append(f"All spells in the source, any person: {len(W):,} spells, {len({w['PHN'] for w in W}):,} people. Origin at entry tied on the entry day: {sum(1 for w in Ws if w['ORIGIN_CONFLICT_FLAG']=='1'):,} of {len(Ws):,} consultant-scope spells.\n")
    else: S.append("Waitlist-activity table not supplied (sql/16).\n")
    # placement-year
    S.append("## 3. Placement-year view — by PLACEMENT_FYE (fiscal year of the admission). Event grain: every qualifying Type A/B admission.\n")
    if E:
        Es = [e for e in E if e["PERSON_POPULATION"] or e["PLACEMENT_IN_COCHRANE"] == "1"]
        Ec = [e for e in E if e["PLACEMENT_IN_COCHRANE"] == "1"]
        S.append("### 3a. Cochrane facilities — all admissions to Bethany Cochrane LTC, Hawthorne SL4, Hawthorne SL4D, whoever the person is\n")
        S.append(md_table(["FYE", "placement events", "unique people placed", "Bethany Cochrane LTC", "Hawthorne SL4", "Hawthorne SL4D", "Type A", "Type B", "Town residents", "Cochrane catchment", "non-Town", "residency unresolved", "outside demand universe"],
            by_fye(Ec, "PLACEMENT_FYE", lambda ys: [len(ys), len({e["PHN"] for e in ys})] + [sum(1 for e in ys if e["PLACEMENT_SITE"] == s_) for s_ in ("CAL - Bethany Cochrane LTC_", "CAL - Hawthorne SL4_", "CAL - Hawthorne SL4D")]
                + [sum(1 for e in ys if e["CARE_STREAM"] == s_) for s_ in ("Type A", "Type B")] + [Counter(e["RESIDENCE_CLASS"] for e in ys)[k] for k in ("Town", "Cochrane catchment", "non-Town", "unresolved", "not in person table")])))
        def cat(e):
            if e["PERSON_COHORT"] in ("A", "B"): return "first placement of A/B" if e["IS_FIRST_PLACEMENT"] == "1" else "later move of an A/B person"
            if e["PERSON_COHORT"] == "C": return "later move of a C person into Cochrane"
            if e["PERSON_POPULATION"].startswith("X1"): return "first placement, residency unresolved (X1)"
            if e["PERSON_POPULATION"]: return "later move into Cochrane of a non-Town person first placed elsewhere"
            return "person outside the demand universe"
        cats = [c for c in ["first placement of A/B", "first placement, residency unresolved (X1)", "later move of an A/B person", "later move of a C person into Cochrane", "later move into Cochrane of a non-Town person first placed elsewhere", "person outside the demand universe"] if any(cat(e) == c for e in Ec)]
        S.append("Who the Cochrane-site admissions are (reconciles 3a to the person grain: A+B first placements = 237):\n" + md_table(["FYE"] + cats, by_fye(Ec, "PLACEMENT_FYE", lambda ys: [sum(1 for e in ys if cat(e) == c) for c in cats])))
        S.append("### 3b. All qualifying Type A/B admissions of consultant-scope people, any site\n")
        Ep = [e for e in E if e["PHN"] in {p["PHN"] for p in D}]
        S.append(md_table(["FYE", "placement events", "unique people placed", "in Cochrane", "outside Cochrane", "Type A", "Type B", "first placements", "later moves"],
            by_fye(Ep, "PLACEMENT_FYE", lambda ys: [len(ys), len({e["PHN"] for e in ys}), sum(1 for e in ys if e["PLACEMENT_IN_COCHRANE"] == "1"), sum(1 for e in ys if e["PLACEMENT_IN_COCHRANE"] != "1"),
                sum(1 for e in ys if e["CARE_STREAM"] == "Type A"), sum(1 for e in ys if e["CARE_STREAM"] == "Type B"), sum(1 for e in ys if e["IS_FIRST_PLACEMENT"] == "1"), sum(1 for e in ys if e["IS_FIRST_PLACEMENT"] != "1")])))
        S.append("Origin (admission source_location) of consultant-scope placement events: " + "; ".join(f"{k} {v}" for k, v in Counter(e["ORIGIN_SETTING"] for e in Ep).most_common()) + ".\n")
    else: S.append("Placement-event table not supplied (sql/15).\n")
    S.append("### 3c. Person grain for comparison — FIRST placement of A/B/C people by PLACEMENT_FYE\n")
    S.append(md_table(["FYE", "people first placed", "in Cochrane (A+B)", "Type A", "Type B", "A", "B", "of B: catchment", "C"],
        by_fye([p for p in coh if p["_pl"]], "PLACEMENT_FYE", lambda ys: [len(ys), sum(1 for p in ys if p["FIRST_PLACEMENT_IN_COCHRANE"] == "1"), sum(1 for p in ys if p["FIRST_PLACEMENT_STREAM"] == "Type A"), sum(1 for p in ys if p["FIRST_PLACEMENT_STREAM"] == "Type B"),
            sum(1 for p in ys if p["COHORT"] == "A"), sum(1 for p in ys if p["COHORT"] == "B"), sum(1 for p in ys if p["B_CATCHMENT"] == "1"), sum(1 for p in ys if p["COHORT"] == "C")])))
    # wait time
    S.append("## 4. Time to placement — DEMAND_DT to first observed placement, placed people only (A, B, C)\n")
    placed = [p for p in coh if p["_pl"]]; H = ["group", "n", "median days", "P25", "P75", "mean"]
    rows = [["all placed"] + wt(placed)] + [[f"cohort {k}"] + wt([p for p in placed if p["COHORT"] == k]) for k in "ABC"]
    rows += [[s_] + wt([p for p in placed if p["FIRST_PLACEMENT_STREAM"] == s_]) for s_ in ("Type A", "Type B")] + [[f"demand FYE {y}"] + wt([p for p in placed if p["DEMAND_FYE"] == y]) for y in FYES]
    S.append(md_table(H, rows))
    S.append("Later demand years are right-censored at 31 March 2026: only the shorter waits of FYE 2025-2026 demand have completed, so their medians are biased low.\n")
    alt = [p for p in placed if p["DAYS_TO_PLACEMENT_ALT"] != ""]
    if alt:
        moved = sum(1 for p in alt if p["DAYS_TO_PLACEMENT_ALT"] != p["DAYS_TO_PLACEMENT"])
        rows = [["all placed (DAYS_TO_PLACEMENT)"] + wt(placed), ["all placed (DAYS_TO_PLACEMENT_ALT)"] + wt(alt, "DAYS_TO_PLACEMENT_ALT")]
        for k in "ABC": rows += [[f"cohort {k} (primary)"] + wt([p for p in placed if p["COHORT"] == k]), [f"cohort {k} (ALT)"] + wt([p for p in alt if p["COHORT"] == k], "DAYS_TO_PLACEMENT_ALT")]
        S.append(f"### 4a. Approval-precedence sensitivity — DAYS_TO_PLACEMENT_ALT uses DEMAND_DT_ALT; {moved} of {len(alt)} placed people change individual wait\n" + md_table(H, rows))
    # completeness
    S.append("## 5. Completeness and QA — consultant-scope people\n")
    rows = []
    for lab, f in (("DOB", lambda p: p["DOB"]), ("sex", lambda p: p["SEX"]), ("age at demand", lambda p: p["AGE_AT_DEMAND"] is not None), ("community of residence", lambda p: p["RESIDENCE_COMMUNITY_AT_DEMAND"]),
                   ("origin setting classified (not Unknown)", lambda p: p["ORIGIN_SETTING"] != "Unknown"), ("first placement site (placed only)", lambda p: (not p["_pl"]) or p["FIRST_PLACEMENT_SITE"]),
                   ("at least one rated site", lambda p: p["MOST_FREQUENTLY_OBSERVED_RATED_SITE"] and not p["MOST_FREQUENTLY_OBSERVED_RATED_SITE"].startswith("("))):
        n = sum(1 for p in D if f(p)); rows.append([lab, n, len(D) - n, pct(n, len(D))])
    S.append(md_table(["field", "present", "missing", "% present"], rows))
    S.append("DOB: " + f"conflict between Strata and Registry {sum(1 for p in D if p['DOB_CONFLICT_FLAG']=='1')} of {sum(1 for p in D if p['DOB_DIFFERENCE_DAYS']!='')} with both; over a year apart {sum(1 for p in D if p['DOB_CONFLICT_OVER_1Y']=='1')}; age band at demand depends on the source for {sum(1 for p in D if p['AGE_BAND_DEPENDS_ON_DOB_SOURCE']=='1')}"
             + (f"; Epic DOB available for {sum(1 for p in D if p['DOB_EPIC'])}, agreeing with " + "; ".join(f"{k or 'neither'} {v}" for k, v in Counter(p['DOB_EPIC_AGREES_WITH'] for p in D if p['DOB_EPIC']).most_common()) if any(p["DOB_EPIC"] for p in D) else "; Epic DOB not supplied") + ".\n")
    S.append("Origin at first list entry: " + f"tied locations on the entry day {sum(1 for p in D if p['ORIGIN_CONFLICT_FLAG']=='1')} of {len(D)}; " + "; ".join(f"{k} {v}" for k, v in Counter(p["ORIGIN_CONFLICT_NOTE"] for p in D if p["ORIGIN_CONFLICT_FLAG"] == "1").most_common()) + ". Source: " + "; ".join(f"{k[:60]} ({v})" for k, v in Counter(p["ORIGIN_SOURCE"].split(" 20")[0] for p in D).most_common()) + "\n")
    S.append("### 5a. Residence — RESIDENCY_FINAL and community, consultant scope\n" + md_table(["RESIDENCY_FINAL", "community", "reference", "people"],
        [[a, b, c_, n] for (a, b, c_), n in Counter((p["RESIDENCY_FINAL"], p["RESIDENCE_COMMUNITY_AT_DEMAND"] or "(missing)", p["RESIDENCE_REFERENCE_TYPE"][:22]) for p in D).most_common(30)]))
    S.append("### 5b. Origin setting — detail and category, consultant scope\n" + md_table(["ORIGIN_SETTING", "detail", "people"], [[a, b, n] for (a, b), n in Counter((p["ORIGIN_SETTING"], p["ORIGIN_SETTING_DETAIL"]) for p in D).most_common()]))
    S.append("### 5c. Consultant scope — reason for inclusion\n" + md_table(["SCOPE_REASON", "POPULATION", "people"], [[a, b or "(no cohort: valid, none of A-D/X)", n] for (a, b), n in Counter((p["SCOPE_REASON"], p["POPULATION"]) for p in D).most_common()]))
    return "\n".join(S)

# ── write ─────────────────────────────────────────────────────────────────────
CONSULTANT = ["STUDY_ID", "IN_CONSULTANT_SCOPE", "SCOPE_REASON", "POPULATION", "COHORT", "D_CLASS", "DEMAND_DT", "DEMAND_FYE", "DEMAND_EVENT_TYPE", "FIRST_WAITLIST_APPEARANCE", "FIRST_APPROVAL_DT",
              "LAST_SEEN_ON_LIST", "ON_LIST_AT_FOLLOWUP", "AGE_AT_DEMAND", "AGE_AT_FIRST_WAITLIST", "AGE_AT_PLACEMENT", "AGE_GROUP_AT_DEMAND", "SEX", "SEX_SOURCE",
              "RESIDENCY_FINAL", "RESIDENCE_CLASS", "RESIDENCE_COMMUNITY_AT_DEMAND", "RESIDENCE_COMMUNITY_SOURCE", "RESIDENCE_REFERENCE_TYPE", "RESIDENCE_REFERENCE_FYE", "COCHRANE_TOWN_FLAG", "COCHRANE_CATCHMENT_FLAG",
              "ORIGIN_SETTING", "ORIGIN_SETTING_DETAIL", "ORIGIN_SITE", "ORIGIN_CONFLICT_FLAG", "MOST_FREQUENTLY_OBSERVED_RATED_SITE", "REQUESTED_CARE_STREAM", "N_SITES_REQUESTED", "REQUESTED_COCHRANE_FLAG", "REQUESTED_COCHRANE_SITES",
              "FIRST_PLACEMENT_DT", "PLACEMENT_FYE", "FIRST_PLACEMENT_SITE", "FIRST_PLACEMENT_STREAM", "FIRST_PLACEMENT_IN_COCHRANE", "ANY_COCHRANE_PLACEMENT_EVENT", "DAYS_TO_PLACEMENT", "DAYS_TO_PLACEMENT_ALT", "DAYS_WAITING_AS_OF_FOLLOWUP"]
EVENT_CONSULTANT = ["STUDY_ID", "ADMISSION_DT", "PLACEMENT_FYE", "PLACEMENT_SITE", "CARE_STREAM", "PLACEMENT_IN_COCHRANE", "ORIGIN_SETTING", "ORIGIN_SETTING_DETAIL", "IS_FIRST_PLACEMENT", "EVENT_SEQ_FOR_PERSON", "RESIDENCE_CLASS", "RESIDENCE_COMMUNITY_AT_DEMAND", "PERSON_COHORT", "PERSON_POPULATION"]
WAIT_CONSULTANT = ["STUDY_ID", "SPELL_SEQ_FOR_PERSON", "LIST_ENTRY_DT", "LIST_ENTRY_FYE", "LIST_LAST_SEEN_DT", "DAYS_OBSERVED", "CARE_STREAM_AT_ENTRY", "ORIGIN_SETTING", "ORIGIN_SETTING_DETAIL", "ORIGIN_CONFLICT_FLAG", "FIRST_APPROVED_DT_IN_SPELL", "RATED_COCHRANE_IN_SPELL", "LEFT_TRUNCATED", "ON_LIST_AT_FOLLOWUP", "RESIDENCE_CLASS", "PERSON_COHORT"]
def write_csv(path, rows, fields):
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(fields)
        for r in rows: w.writerow(["" if r.get(k) is None else r.get(k, "") for k in fields])

def main(a):
    salt = load_salt(a.salt)
    epic = {"".join(c for c in col(r, "PHN") if c.isdigit()): r for r in read(a.epic_demo)} if a.epic_demo else None
    P, have = load_person(a.person, salt, epic); byphn = {p["PHN"]: p for p in P}
    E = load_events(a.events, salt, byphn) if a.events else None
    scope_flags(P, E)
    W = load_waitlist(a.waitlist, salt, byphn) if a.waitlist else None
    checks, ok = qa(P, tuple(int(x) for x in a.expect.split(",")), have, E, W)
    os.makedirs(a.out, exist_ok=True)
    D = [p for p in P if p["IN_CONSULTANT_SCOPE"] == "1"]; coh = [p for p in P if p["COHORT"]]
    c = Counter(p["COHORT"] for p in coh); dc = Counter(p["D_CLASS"][:2] for p in coh if p["COHORT"] == "D")
    prov = [f for f in ("N_ORIGIN_LOCATIONS_AT_ENTRY", "STRATA_CITY_AT_DEMAND", "RESIDENCE_REFERENCE_FYE", "MOST_FREQUENTLY_OBSERVED_RATED_SITE") if f not in have]
    R = ["# Reviewer pre-check — Cochrane planning deliverable\n",
         f"Person `{os.path.basename(a.person)}`; events " + (f"`{os.path.basename(a.events)}`" if a.events else "not supplied") + "; waitlist " + (f"`{os.path.basename(a.waitlist)}`" if a.waitlist else "not supplied") + "; Epic DOB " + (f"`{os.path.basename(a.epic_demo)}`" if a.epic_demo else "not supplied") + "\n"]
    if prov: R.append("**Extract predates these sql/14 columns; the affected fields are provisional:** " + ", ".join(f"`{f}`" for f in prov) + "\n")
    R.append(f"1. **Consultant-scope count:** {len(D):,} of the {len(P):,}-row QA population (IN_CONSULTANT_SCOPE = valid in-window demand AND [Town resident OR rated a Cochrane/Hawthorne site OR a Type A/B placement in a Cochrane facility]). "
             f"Reasons: " + "; ".join(f"{k} {v}" for k, v in Counter(p["SCOPE_REASON"] for p in D).most_common()) + f". Meeting a criterion but excluded by the validity gate (not in window / never approved / invalid record): {sum(1 for p in P if p['SCOPE_EXCLUDED_BY_GATE']=='1')}. "
             f"Against POPULATION (A-D + X1-X3 = {sum(1 for p in P if p['POPULATION'])}): in scope but no POPULATION label {sum(1 for p in D if not p['POPULATION'])}; labelled but out of scope {sum(1 for p in P if p['POPULATION'] and p['IN_CONSULTANT_SCOPE']!='1')}.\n")
    R.append(f"2. **A/B/C/D:** {c['A']} / {c['B']} / {c['C']} / {c['D']} — resident demand {c['A']+c['C']+c['D']}. **D1/D2/D3:** {dc['D1']} / {dc['D2']} / {dc['D3']}\n")
    R.append(f"3. **Age (scope):** complete {sum(1 for p in D if p['AGE_AT_DEMAND'] is not None)}/{len(D)}; bands " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(p['AGE_GROUP_AT_DEMAND'] or '(missing)' for p in D).items())) + f"; median age at demand {st.median([p['AGE_AT_DEMAND'] for p in D if p['AGE_AT_DEMAND'] is not None])}\n")
    R.append(f"4. **Sex (Registry, scope):** {sum(1 for p in D if p['SEX'])}/{len(D)}; " + ", ".join(f"{k or 'missing'} {v}" for k, v in Counter(p['SEX'] for p in D).most_common()) + "\n")
    R.append(f"5. **DOB conflicts (scope):** both sources {sum(1 for p in D if p['DOB_DIFFERENCE_DAYS']!='')}; differ {sum(1 for p in D if p['DOB_CONFLICT_FLAG']=='1')}; over 1 year {sum(1 for p in D if p['DOB_CONFLICT_OVER_1Y']=='1')}; age band depends on source {sum(1 for p in D if p['AGE_BAND_DEPENDS_ON_DOB_SOURCE']=='1')}; DOB source " + ", ".join(f"{k or 'none'} {v}" for k, v in Counter(p['DOB_SOURCE'] for p in D).most_common())
             + ("; Epic review: " + "; ".join(f"agrees with {k or 'neither'} {v}" for k, v in Counter(p['DOB_EPIC_AGREES_WITH'] for p in D if p['DOB_EPIC'] and p['DOB_CONFLICT_FLAG']=='1').most_common()) + " among the conflicts" if epic else "; Epic DOB not supplied (sql/17)") + "\n")
    R.append(f"6. **Origin at first list entry (scope):** tied on the entry day {sum(1 for p in D if p['ORIGIN_CONFLICT_FLAG']=='1')}; distribution " + ", ".join(f"{k} {v}" for k, v in Counter(p['ORIGIN_SETTING'] for p in D).most_common()) + "\n")
    R.append(f"7. **Community (scope):** {sum(1 for p in D if p['RESIDENCE_COMMUNITY_AT_DEMAND'])}/{len(D)}; source " + ", ".join(f"{k or 'none'} {v}" for k, v in Counter(p['RESIDENCE_COMMUNITY_SOURCE'] for p in D).most_common()) + "\n")
    R.append("8. **PHN <-> PATIENT_ID (scope):** " + "; ".join(f"{k or 'no Strata patient record'} {v}" for k, v in Counter(p['PHN_PATIENT_ID_MULTIPLICITY'] for p in D).most_common()) + "\n")
    if W:
        Ws = [w for w in W if w["PERSON_IN_CONSULTANT_SCOPE"] == "1"]
        R.append("9. **Annual waitlist (scope, LIST_ENTRY_FYE):** spells / unique people — " + "; ".join(f"{y}: {sum(1 for w in Ws if w['LIST_ENTRY_FYE']==y)} / {len({w['PHN'] for w in Ws if w['LIST_ENTRY_FYE']==y})}" for y in FYES) + "\n")
    else: R.append("9. **Annual waitlist:** waitlist table not supplied (sql/16)\n")
    if E:
        Ep = [e for e in E if e["PHN"] in {p["PHN"] for p in D}]; Ec = [e for e in E if e["PLACEMENT_IN_COCHRANE"] == "1"]
        R.append("9a. **People meeting a scope criterion but excluded by the validity gate:** " + "; ".join(f"{p['SCOPE_REASON']} — demand {p['DEMAND_DT']} (in window {p['IN_WINDOW']}, approved {p['WAS_APPROVED']}, valid {p['RECORD_VALID']})" for p in P if p["SCOPE_EXCLUDED_BY_GATE"] == "1") + "\n")
        R.append("10. **Annual placement (PLACEMENT_FYE):** scope people, events / unique — " + "; ".join(f"{y}: {sum(1 for e in Ep if e['PLACEMENT_FYE']==y)} / {len({e['PHN'] for e in Ep if e['PLACEMENT_FYE']==y})}" for y in FYES)
                 + ". Cochrane sites, all people, events / unique — " + "; ".join(f"{y}: {sum(1 for e in Ec if e['PLACEMENT_FYE']==y)} / {len({e['PHN'] for e in Ec if e['PLACEMENT_FYE']==y})}" for y in FYES) + "\n")
    else: R.append("10. **Annual placement:** event table not supplied (sql/15)\n")
    placed = [p for p in coh if p["_pl"]]; alt = [p for p in placed if p["DAYS_TO_PLACEMENT_ALT"] != ""]
    R.append(f"11. **Wait time (A/B/C placed, n={len(placed)}):** median {wt(placed)[1]} days (P25 {wt(placed)[2]}, P75 {wt(placed)[3]}); under DEMAND_DT_ALT median {wt(alt,'DAYS_TO_PLACEMENT_ALT')[1] if alt else '—'}; {sum(1 for p in alt if p['DAYS_TO_PLACEMENT_ALT']!=p['DAYS_TO_PLACEMENT'])} people change individual wait\n")
    R.append("12. **Reconciliation tests:**\n\n" + md_table(["check", "n", "result"], [[l, n, s_] for l, n, s_ in checks]))
    R.append("13. **Headline change caused by enrichment:** " + ("none — A/B/C/D reproduced exactly" if ok else "**STOP — see failed checks**") + "\n")
    open(os.path.join(a.out, "REVIEWER_PRECHECK.md"), "w").write("\n".join(R))
    if not ok: print("\n".join(R)); sys.exit("QA FAILED — no deliverable files written.")
    internal = [k for k in P[0].keys() if not k.startswith("_")]
    write_csv(os.path.join(a.out, "COCHRANE_DEMAND_INTERNAL_QA.csv"), P, internal)
    write_csv(os.path.join(a.out, "COCHRANE_DEMAND_CONSULTANT.csv"), D, CONSULTANT)
    if E:
        Ev = [e for e in E if e["PLACEMENT_IN_COCHRANE"] == "1" or e["PHN"] in {p["PHN"] for p in D}]
        write_csv(os.path.join(a.out, "COCHRANE_PLACEMENT_ACTIVITY_INTERNAL.csv"), Ev, [k for k in E[0].keys() if not k.startswith("_")])
        write_csv(os.path.join(a.out, "COCHRANE_PLACEMENT_ACTIVITY_CONSULTANT.csv"), Ev, EVENT_CONSULTANT)
    if W:
        Wv = [w for w in W if w["PERSON_IN_CONSULTANT_SCOPE"] == "1"]
        write_csv(os.path.join(a.out, "COCHRANE_WAITLIST_ACTIVITY_INTERNAL.csv"), Wv, [k for k in W[0].keys() if not k.startswith("_")])
        write_csv(os.path.join(a.out, "COCHRANE_WAITLIST_ACTIVITY_CONSULTANT.csv"), Wv, WAIT_CONSULTANT)
    head = "# Cochrane continuing-care demand — summary tables\n\nThree time bases, never mixed in one metric: **DEMAND_FYE** (year the Type A/B demand arose, person grain), **LIST_ENTRY_FYE** (year a waitlist spell began, spell grain), **PLACEMENT_FYE** (year of an admission, event grain).\n\n"
    open(os.path.join(a.out, "COCHRANE_SUMMARY.md"), "w").write(head + summaries(P, E, W))
    print("\n".join(R)); print(f"\nwritten to {a.out}/: " + ", ".join(sorted(os.listdir(a.out))))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--person", required=True); ap.add_argument("--events"); ap.add_argument("--waitlist"); ap.add_argument("--epic-demo")
    ap.add_argument("--salt", default="secrets/study_id_salt.txt"); ap.add_argument("--expect", default="89,148,192,69"); ap.add_argument("--out", default="deliverables")
    main(ap.parse_args())
