#!/usr/bin/env python3
"""
Build the final Cochrane planning deliverable. Two populations, three grains.

POPULATIONS (person grain)
  INCIDENT_DEMAND_SCOPE   new FY2022-FY2026 Type A/B demand: the validated A/B/C/D
                          universe gated on the demand event (sql/14). 987 people.
                          A/B/C/D and D1-D3 live here and are never recomputed.
  CONSULTANT_ACTIVITY_SCOPE  every person with qualifying Type A/B ACTIVITY in
                          FY2022-FY2026: a waitlist spell rated for a Cochrane /
                          Hawthorne site, a waitlist spell as a Town-of-Cochrane
                          resident, or an admission to a Cochrane site - with NO
                          gate on when demand first arose or on prior residential
                          care. Attributes at the activity anchor come from sql/18.
  The consultant person file is the UNION; ACTIVITY_STATUS says which.

GRAINS
  person    sql/14 (--person) + sql/18 (--activity-person)
  waitlist  sql/16 (--waitlist)   one row per spell
  event     sql/15 (--events)     one row per qualifying admission
  --epic-demo (sql/17) Epic DOB / sex: DOB two-of-three consensus, sex fallback.

Rules
  · A/B/C/D from the extract only. The build stops if they differ from --expect.
  · DOB = exact two-of-three consensus of Strata, Registry, Epic; Strata when no
    consensus; DOB_SOURCE records it. Ages = completed years at the event date.
  · SEX = Registry, else Epic (labelled fallback), else missing.
  · Community only from the address that decided residency; reference type kept.
  · Origin = setting at FIRST list entry; entry-day ties reported, never broken.
  · Rated sites are observed frequency; "rated for a Cochrane site", not requested.
  · An invalid postal code never establishes residency (sql rev 2.10).
"""
import csv, sys, os, re, argparse, hmac, hashlib, secrets, datetime as dt, statistics as st
from collections import Counter, defaultdict, OrderedDict

WIN_START, WIN_END, FOLLOW_UP = dt.date(2021,4,1), dt.date(2026,4,1), dt.date(2026,3,31)
TOWN, AREA, NOT, UNRES = "Town of Cochrane", "Cochrane catchment", "Not a Cochrane-area resident", "UNRESOLVED"
FYES = [2022, 2023, 2024, 2025, 2026]
SITES = ("CAL - Bethany Cochrane LTC_", "CAL - Hawthorne SL4_", "CAL - Hawthorne SL4D")

def day(s):
    s = (s or "").strip(); return dt.datetime.strptime(s[:10], "%Y-%m-%d").date() if s else None
def col(r, k, default=""): return (r.get(k) or default).strip()
def fye(d): return None if d is None else (d.year + 1 if d.month >= 4 else d.year)
def age_at(dob, d):
    if not dob or not d: return None
    return d.year - dob.year - ((d.month, d.day) < (dob.month, dob.day))
def age_band(a): return "" if a is None else "<65" if a < 65 else "65-74" if a < 75 else "75-84" if a < 85 else "85+"
def pct(a, b): return f"{a/b*100:.1f}%" if b else "—"
def q(xs, p):
    xs = sorted(xs); n = len(xs)
    if n == 0: return None
    k = (n - 1) * p; f = int(k); c = min(f + 1, n - 1); return xs[f] + (xs[c] - xs[f]) * (k - f)
def rclass(res): return "Town" if res == TOWN else "Cochrane catchment" if res == AREA else "non-Town" if res == NOT else "unresolved"
def read(path):
    rd = csv.DictReader(open(path)); rd.fieldnames = [h.strip().upper() for h in rd.fieldnames]
    return [{k: (v or "").strip() for k, v in r.items()} for r in rd]
def digits(s): return "".join(c for c in (s or "") if c.isdigit())

# ── origin normalisation ──────────────────────────────────────────────────────
def origin_detail(v):
    u = (v or "").upper().strip()
    if not u: return "Unknown"
    if "OUT OF PROVINCE" in u: return "Out of province"
    if u == "OUT OF REGION": return "Out of region"
    if any(k in u for k in ("EMERG", " ED ", "- ED", "EMERGENCY")): return "Emergency department"
    if any(k in u for k in ("HOME", "PERSONAL RESIDENCE")) and "LODGE" not in u: return "Own home"
    if "HOSPICE" in u or "PALLIAT" in u: return "Hospice / palliative"
    if any(k in u for k in ("RCTP", "REHAB", "TRANSITION", "SUBACUTE", "SUB-ACUTE", "SUB ACUTE", "RESTORATIVE", "STEP DOWN", " IT /", "IT / RCTP", "GLENROSE", "LEVEL 5")): return "Sub-acute / transition / rehab"
    if any(k in u for k in ("HOSPITAL", "MEDICAL CENTRE", "HEALTH CAMPUS", "HEALTH CENTRE", "PETER LOUGHEED", "FOOTHILLS", "ROCKYVIEW", "VILLA CARITAS", "ACUTE", "STURGEON")): return "Acute hospital"
    if "ALC" in u: return "Continuing-care ALC bed"
    if "LODGE" in u: return "Lodge"
    if any(k in u for k in ("ASSISTED LIVING", "SL4", "DSL", "SUPPORTIVE LIVING", "DAL")): return "Supportive / assisted living"
    if any(k in u for k in ("LTC", "LONG TERM CARE", "CAPITAL CARE", "CAREWEST", "NURSING")): return "Long-term care"
    if "ZONE" in u: return "Other (zone-level)"
    return "Other"
COARSE = {"Own home": "Community", "Emergency department": "Acute Care", "Acute hospital": "Acute Care", "Sub-acute / transition / rehab": "Acute Care", "Lodge": "Lodge",
          "Continuing-care ALC bed": "Assisted Living or Other Continuing Care", "Supportive / assisted living": "Assisted Living or Other Continuing Care",
          "Long-term care": "Assisted Living or Other Continuing Care", "Hospice / palliative": "Assisted Living or Other Continuing Care",
          "Out of province": "Out of Province", "Out of region": "Other", "Other (zone-level)": "Other", "Other": "Other", "Unknown": "Unknown"}
def normalise_origin(raw, lst, conflict):
    if conflict and lst:
        vals = [v.strip() for v in lst.split("|") if v.strip()]
        cats = {COARSE[origin_detail(v)] for v in vals}; dets = {origin_detail(v) for v in vals}
        if len(cats) == 1: return cats.pop(), (dets.pop() if len(dets) == 1 else "tied values, same category"), "tied values agree on category"
        return "Unknown", "tied values, different categories", "tied values disagree; not classified"
    d = origin_detail(raw); return COARSE[d], d, ""

# ── STUDY_ID ──────────────────────────────────────────────────────────────────
def load_salt(path):
    if os.path.exists(path):
        s = open(path).read().strip()
        if len(s) < 32: sys.exit(f"salt file {path} is too short; refuse to run")
        return s
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True); s = secrets.token_hex(32); open(path, "w").write(s + "\n")
    print(f"NEW STUDY_ID salt written to {path}. Keep it; STUDY_IDs are only stable while it is unchanged."); return s
def study_id(salt, phn): return "CD-" + hmac.new(salt.encode(), phn.encode(), hashlib.sha256).hexdigest()[:12].upper()

# ── demographics (shared by both person sources) ─────────────────────────────
def demographics(r, epic, anchor, fw, pl):
    d = OrderedDict()
    ds, dr = day(col(r, "DOB_STRATA")), day(col(r, "DOB_REGISTRY"))
    e = epic.get(digits(col(r, "PHN"))) if epic else None
    de = day(e["EPIC_DOB"]) if e else None
    # exact two-of-three consensus; Strata when none; single source when only one exists
    votes = [("STRATA", ds), ("REGISTRY", dr), ("EPIC", de)]; present = [(n, v) for n, v in votes if v]
    dob, src = None, ""
    if len(present) >= 2:
        for i in range(len(present)):
            agree = [n for n, v in present if v == present[i][1]]
            if len(agree) >= 2: dob, src = present[i][1], "CONSENSUS " + "+".join(agree); break
        if not dob: dob, src = (ds, "STRATA (no consensus among " + "+".join(n for n, _ in present) + ")") if ds else (present[0][1], present[0][0] + " (no consensus)")
    elif present: dob, src = present[0][1], present[0][0] + " (single source)"
    d["DOB"] = dob.isoformat() if dob else ""; d["DOB_SOURCE"] = src; d["_dob"] = dob
    d["DOB_STRATA"] = col(r, "DOB_STRATA")[:10]; d["DOB_REGISTRY"] = col(r, "DOB_REGISTRY")[:10]; d["DOB_EPIC"] = de.isoformat() if de else ""
    d["DOB_DIFFERENCE_DAYS"] = abs((ds - dr).days) if (ds and dr) else ""; d["DOB_CONFLICT_FLAG"] = "1" if (ds and dr and ds != dr) else "0"
    d["DOB_CONFLICT_OVER_1Y"] = "1" if (ds and dr and abs((ds - dr).days) > 366) else "0"
    d["DOB_EPIC_AGREES_WITH"] = "+".join(n for n, v in (("STRATA", ds), ("REGISTRY", dr)) if v and de and v == de) if de else ""
    sx = col(r, "SEX"); ex = (e["EPIC_SEX"] if e else "")[:1].upper() if e else ""
    if sx: d["SEX"], d["SEX_SOURCE"] = sx, "REGISTRY"
    elif ex in ("F", "M"): d["SEX"], d["SEX_SOURCE"] = ex, "EPIC (fallback; Registry missing)"
    else: d["SEX"], d["SEX_SOURCE"] = "", ""
    d["SEX_EPIC"] = ex if ex in ("F", "M") else ""; d["SEX_REGISTRY_EPIC_DISAGREE"] = "1" if (sx and ex in ("F", "M") and sx != ex) else "0"
    d["AGE_AT_ANCHOR"] = age_at(dob, anchor); d["AGE_AT_FIRST_WAITLIST"] = age_at(dob, fw); d["AGE_AT_PLACEMENT"] = age_at(dob, pl)
    d["AGE_GROUP_AT_ANCHOR"] = age_band(d["AGE_AT_ANCHOR"])
    d["AGE_BAND_DEPENDS_ON_DOB_SOURCE"] = "1" if (ds and dr and age_band(age_at(ds, anchor)) != age_band(age_at(dr, anchor))) else "0"
    return d

PC_OK = re.compile(r"^[ABCEGHJ-NPRSTVXY][0-9][ABCEGHJ-NPRSTV-Z][0-9][ABCEGHJ-NPRSTV-Z][0-9]$"); PC_DUMMY = {"Z1Z1Z1", "A1A1A1", "H0H0H0", "X0X0X0", "T0T0T0", "A0A0A0"}
def residence(r, suffix):
    d = OrderedDict()
    d["RESIDENCY_FINAL"] = col(r, "RESIDENCY_FINAL") or col(r, "RESIDENCY_LATEST"); d["RESIDENCY_SOURCE"] = col(r, "RESIDENCY_SOURCE"); d["RESIDENCE_CLASS"] = rclass(d["RESIDENCY_FINAL"])
    d["RESIDENCE_POSTAL_CODE"] = col(r, "RESIDENCE_POSTAL_CODE_AT_" + suffix)
    pcu = d["RESIDENCE_POSTAL_CODE"].upper().replace(" ", ""); d["RESIDENCE_POSTAL_CODE_INVALID"] = "1" if (pcu and (not PC_OK.match(pcu) or pcu in PC_DUMMY)) else "0"
    comm = col(r, "RESIDENCE_COMMUNITY_AT_" + suffix); src_lab = "Alberta postal geography (Statistics Canada CSD)" if comm else ""
    if not comm and d["RESIDENCY_SOURCE"] == "STRATA_ADDRESS_H":
        city = col(r, "STRATA_CITY_AT_" + suffix)
        if city: comm = city.upper() + " (Strata city; postal code outside the Alberta lookup)"; src_lab = "Strata city_name (labelled fallback)"
        elif d["RESIDENCE_POSTAL_CODE"] and d["RESIDENCE_POSTAL_CODE"][0].upper() != "T": comm = "Outside Alberta (postal " + d["RESIDENCE_POSTAL_CODE"][:3].upper() + ")"; src_lab = "postal prefix only"
    d["RESIDENCE_COMMUNITY"] = comm; d["RESIDENCE_COMMUNITY_SOURCE"] = src_lab; d["RESIDENCE_LOCAL_NAME"] = col(r, "RESIDENCE_LOCAL_NAME_AT_" + suffix)
    if d["RESIDENCY_SOURCE"] == "REGISTRY": d["RESIDENCE_REFERENCE_TYPE"], d["RESIDENCE_REFERENCE_FYE"], d["RESIDENCE_REFERENCE_DATE"] = "Registry address of fiscal year (not an exact date)", col(r, "RESIDENCE_REFERENCE_FYE"), ""
    elif d["RESIDENCY_SOURCE"] == "STRATA_ADDRESS_H": d["RESIDENCE_REFERENCE_TYPE"], d["RESIDENCE_REFERENCE_FYE"], d["RESIDENCE_REFERENCE_DATE"] = "Strata address version effective at the anchor", "", col(r, "STRATA_ADDRESS_EFFECTIVE_FROM")[:10]
    else: d["RESIDENCE_REFERENCE_TYPE"] = d["RESIDENCE_REFERENCE_FYE"] = d["RESIDENCE_REFERENCE_DATE"] = ""
    d["COCHRANE_TOWN_FLAG"] = "1" if d["RESIDENCY_FINAL"] == TOWN else "0"; d["COCHRANE_CATCHMENT_FLAG"] = "1" if d["RESIDENCY_FINAL"] == AREA else "0"
    d["RESIDENCY_EVIDENCE"] = col(r, "RESIDENCY_EVIDENCE"); d["STRATA_ADDRESS_IS_PLACEHOLDER"] = col(r, "STRATA_ADDRESS_IS_PLACEHOLDER"); d["STRATA_RESIDENCY"] = col(r, "STRATA_RESIDENCY")
    return d

def origin(r, have):
    d = OrderedDict()
    if "N_ORIGIN_LOCATIONS_AT_ENTRY" in have:
        raw = col(r, "ORIGIN_SETTING_RAW"); lst = col(r, "ORIGIN_LOCATION_LIST"); n = col(r, "N_ORIGIN_LOCATIONS_AT_ENTRY") or "1"; conflict = col(r, "ORIGIN_CONFLICT_FLAG", "0") == "1"; src = col(r, "ORIGIN_SOURCE")
    else:
        raw = col(r, "SETTING_AT_LIST_ENTRY"); lst = raw; n = "1"; conflict = False; src = "PROVISIONAL: first list appearance, ties broken by min_by"
    d["ORIGIN_SETTING_RAW"] = raw; d["ORIGIN_LOCATION_LIST"] = lst; d["N_ORIGIN_LOCATIONS_AT_ENTRY"] = n; d["ORIGIN_CONFLICT_FLAG"] = "1" if conflict else "0"
    d["ORIGIN_SETTING"], d["ORIGIN_SETTING_DETAIL"], d["ORIGIN_CONFLICT_NOTE"] = normalise_origin(raw, lst, conflict)
    d["ORIGIN_SITE"] = raw or lst; d["ORIGIN_SOURCE"] = src; d["ORIGIN_ENTRY_CENSUS_DATE"] = col(r, "ORIGIN_ENTRY_CENSUS_DATE")[:10]
    return d
def rated(r):
    d = OrderedDict()
    d["MOST_FREQUENTLY_OBSERVED_RATED_SITE"] = col(r, "MOST_FREQUENTLY_OBSERVED_RATED_SITE") or col(r, "REQUESTED_SITE") or ("(no site rated)" if col(r, "N_SITES_REQUESTED") == "0" else "")
    d["RATED_CARE_STREAM_MOST_FREQUENT"] = col(r, "REQUESTED_CARE_STREAM"); d["N_SITES_RATED"] = col(r, "N_SITES_REQUESTED")
    d["RATED_FOR_COCHRANE_SITE_FLAG"] = col(r, "REQUESTED_COCHRANE_FLAG") or col(r, "RATED_COCHRANE", "0"); d["COCHRANE_SITES_RATED"] = col(r, "REQUESTED_COCHRANE_SITES")
    return d

# ── person grain: incident (sql/14) ──────────────────────────────────────────
def load_incident(path, salt, epic):
    rows = read(path); have = set(rows[0]) if rows else set(); P = OrderedDict()
    for r in rows:
        phn = digits(col(r, "PHN")); d = OrderedDict()
        d["STUDY_ID"] = study_id(salt, phn); d["PHN"] = phn; d["PATIENT_ID"] = col(r, "PATIENT_ID"); d["PATIENT_ID_ALL"] = col(r, "PATIENT_ID_ALL"); d["N_PATIENT_IDS"] = col(r, "N_PATIENT_IDS")
        d["PHN_PATIENT_ID_MULTIPLICITY"] = col(r, "PHN_PATIENT_ID_MULTIPLICITY"); d["PHN_IS_AUTOGEN_ANY"] = col(r, "PHN_IS_AUTOGEN_ANY")
        d["COHORT"] = col(r, "COHORT"); d["D_CLASS"] = col(r, "D_CLASS")
        d["_dem"] = day(col(r, "DEMAND_DT")); d["_demA"] = day(col(r, "DEMAND_DT_ALT")); d["_fw"] = day(col(r, "FIRST_LIST_APPEARANCE")); d["_pl"] = day(col(r, "FIRST_PLACEMENT_DT")); d["_plA"] = day(col(r, "FIRST_PLACEMENT_DT_ALT"))
        d["DEMAND_DT"] = col(r, "DEMAND_DT")[:10]; d["DEMAND_FYE"] = fye(d["_dem"]) or ""; d["DEMAND_EVENT_TYPE"] = col(r, "DEMAND_EVENT_TYPE")
        d["FIRST_WAITLIST_APPEARANCE"] = col(r, "FIRST_LIST_APPEARANCE")[:10]; d["FIRST_APPROVAL_DT"] = col(r, "FIRST_APPROVAL_DT")[:10]; d["LAST_SEEN_ON_LIST"] = col(r, "LAST_SEEN_ON_LIST")[:10]; d["ON_LIST_AT_FOLLOWUP"] = col(r, "ON_LIST_AT_FOLLOWUP", "0")
        d.update(demographics(r, epic, d["_dem"], d["_fw"], d["_pl"])); d["AGE_AT_DEMAND"] = d["AGE_AT_ANCHOR"]; d["AGE_GROUP_AT_DEMAND"] = d["AGE_GROUP_AT_ANCHOR"]
        d.update(residence(r, "DEMAND")); d.update(origin(r, have)); d.update(rated(r))
        d["FIRST_PLACEMENT_DT"] = col(r, "FIRST_PLACEMENT_DT")[:10]; d["PLACEMENT_FYE"] = fye(d["_pl"]) or ""; d["FIRST_PLACEMENT_SITE"] = col(r, "FIRST_PLACEMENT_SITE"); d["FIRST_PLACEMENT_STREAM"] = col(r, "FIRST_PLACEMENT_STREAM")
        d["FIRST_PLACEMENT_IN_COCHRANE"] = col(r, "FIRST_PLACEMENT_IN_COCHRANE", "0")
        d["DAYS_TO_PLACEMENT"] = (d["_pl"] - d["_dem"]).days if (d["_pl"] and d["_dem"]) else ""; d["DAYS_TO_PLACEMENT_ALT"] = (d["_plA"] - d["_demA"]).days if (d["_plA"] and d["_demA"]) else ""
        d["DAYS_WAITING_AS_OF_FOLLOWUP"] = ((FOLLOW_UP - d["_dem"]).days if (not d["_pl"] and d["_dem"] and d["ON_LIST_AT_FOLLOWUP"] == "1") else "")
        d["FIRST_PLACEMENT_AFTER_FOLLOWUP"] = col(r, "FIRST_PLACEMENT_AFTER_FOLLOWUP")[:10]; d["DEATH_DT"] = col(r, "DEATH_DT")[:10]
        d["IN_WINDOW"] = col(r, "IN_WINDOW", "1"); d["WAS_APPROVED"] = col(r, "WAS_APPROVED", "1"); d["RECORD_VALID"] = col(r, "RECORD_VALID", "1"); d["RECORD_INVALID_REASON"] = col(r, "RECORD_INVALID_REASON")
        d["COCHRANE_PLACEMENT_RESIDENCY_UNRESOLVED"] = col(r, "COCHRANE_PLACEMENT_RESIDENCY_UNRESOLVED", "0"); d["B_CATCHMENT"] = col(r, "B_CATCHMENT", "0"); d["COCHRANE_FACING"] = col(r, "COCHRANE_FACING", "1")
        d["_valid"] = d["IN_WINDOW"] == "1" and d["WAS_APPROVED"] == "1" and d["RECORD_VALID"] == "1"; d["_src"] = "sql/14"
        P[phn] = d
    return P, have

def load_activity_person(path, salt, epic):
    rows = read(path); have = set(rows[0]) if rows else set(); A = OrderedDict()
    for r in rows:
        phn = digits(col(r, "PHN")); d = OrderedDict()
        d["STUDY_ID"] = study_id(salt, phn); d["PHN"] = phn; d["PATIENT_ID"] = col(r, "PATIENT_ID"); d["PATIENT_ID_ALL"] = col(r, "PATIENT_ID_ALL"); d["N_PATIENT_IDS"] = col(r, "N_PATIENT_IDS"); d["PHN_PATIENT_ID_MULTIPLICITY"] = col(r, "PHN_PATIENT_ID_MULTIPLICITY")
        an = day(col(r, "ACTIVITY_ANCHOR_DT")); fw = day(col(r, "FIRST_LIST_APPEARANCE"))
        d["ACTIVITY_ANCHOR_DT"] = col(r, "ACTIVITY_ANCHOR_DT")[:10]; d["ACTIVITY_ANCHOR_FYE"] = fye(an) or ""; d["ACTIVITY_ANCHOR_TYPE"] = col(r, "ACTIVITY_ANCHOR_TYPE")
        d["FIRST_WAITLIST_APPEARANCE"] = col(r, "FIRST_LIST_APPEARANCE")[:10]; d["FIRST_APPROVAL_DT"] = col(r, "FIRST_APPROVAL_DT")[:10]; d["LAST_SEEN_ON_LIST"] = col(r, "LAST_SEEN_ON_LIST")[:10]; d["ON_LIST_AT_FOLLOWUP"] = col(r, "ON_LIST_AT_FOLLOWUP", "0")
        d["PRIOR_RESIDENTIAL_CARE_BEFORE_WINDOW"] = "1" if (day(col(r, "FIRST_RESIDENTIAL_EVER")) and day(col(r, "FIRST_RESIDENTIAL_EVER")) < WIN_START) else "0"
        d.update(demographics(r, epic, an, fw, None)); d.update(residence(r, "ANCHOR")); d.update(origin(r, have)); d.update(rated(r)); d["DEATH_DT"] = col(r, "DEATH_DT")[:10]
        d["_anchor"] = an; d["_src"] = "sql/18"; A[phn] = d
    return A

def load_events(path, salt):
    E = []
    for r in read(path):
        phn = digits(col(r, "PHN")); d = OrderedDict(); ad = day(col(r, "ADMISSION_DT"))
        d["STUDY_ID"] = study_id(salt, phn); d["PHN"] = phn; d["PATIENT_ID"] = col(r, "PATIENT_ID"); d["ADMISSION_NOTICE_ID"] = col(r, "ADMISSION_NOTICE_ID")
        d["ADMISSION_DT"] = col(r, "ADMISSION_DT")[:10]; d["PLACEMENT_FYE"] = fye(ad) or ""; d["PLACEMENT_SITE"] = col(r, "PLACEMENT_SITE"); d["CARE_STREAM"] = col(r, "CARE_STREAM")
        d["PLACEMENT_IN_COCHRANE"] = col(r, "PLACEMENT_IN_COCHRANE", "0"); d["SOURCE_LOCATION"] = col(r, "SOURCE_LOCATION"); d["ORIGIN_SETTING_DETAIL"] = origin_detail(d["SOURCE_LOCATION"]); d["ORIGIN_SETTING"] = COARSE[d["ORIGIN_SETTING_DETAIL"]]
        d["DISCHARGE_DT"] = col(r, "DISCHARGE_DT")[:10]; d["DISCHARGE_DESTINATION"] = col(r, "DISCHARGE_DESTINATION"); d["EVENT_SEQ_FOR_PERSON"] = col(r, "EVENT_SEQ_FOR_PERSON"); d["_ad"] = ad; E.append(d)
    return E
def load_waitlist(path, salt):
    W = []
    for r in read(path):
        phn = digits(col(r, "PHN")); d = OrderedDict(); en = day(col(r, "LIST_ENTRY_DT"))
        d["STUDY_ID"] = study_id(salt, phn); d["PHN"] = phn; d["PATIENT_ID"] = col(r, "PATIENT_ID"); d["PATIENT_TRANSFER_ID"] = col(r, "PATIENT_TRANSFER_ID"); d["SPELL_NO"] = col(r, "SPELL_NO")
        d["LIST_ENTRY_DT"] = col(r, "LIST_ENTRY_DT")[:10]; d["LIST_ENTRY_FYE"] = fye(en) or ""; d["LIST_LAST_SEEN_DT"] = col(r, "LIST_LAST_SEEN_DT")[:10]; d["DAYS_OBSERVED"] = col(r, "DAYS_OBSERVED")
        d["CARE_STREAM_AT_ENTRY"] = col(r, "CARE_STREAM_AT_ENTRY"); d["CARE_TYPE_AT_ENTRY"] = col(r, "CARE_TYPE_AT_ENTRY")
        loc = col(r, "LOCATION_AT_ENTRY"); lst = col(r, "LOCATION_LIST_AT_ENTRY"); n = col(r, "N_LOCATIONS_AT_ENTRY") or "1"
        d["LOCATION_AT_ENTRY"] = loc; d["N_LOCATIONS_AT_ENTRY"] = n; d["LOCATION_LIST_AT_ENTRY"] = lst; d["ORIGIN_CONFLICT_FLAG"] = "1" if n not in ("", "1") else "0"
        d["ORIGIN_SETTING"], d["ORIGIN_SETTING_DETAIL"], _ = normalise_origin(loc, lst, d["ORIGIN_CONFLICT_FLAG"] == "1")
        d["FIRST_APPROVED_DT_IN_SPELL"] = col(r, "FIRST_APPROVED_DT_IN_SPELL")[:10]; d["RATED_COCHRANE_IN_SPELL"] = col(r, "RATED_COCHRANE_IN_SPELL", "0")
        d["LEFT_TRUNCATED"] = col(r, "LEFT_TRUNCATED", "0"); d["ON_LIST_AT_FOLLOWUP"] = col(r, "ON_LIST_AT_FOLLOWUP", "0"); d["SPELL_SEQ_FOR_PERSON"] = col(r, "SPELL_SEQ_FOR_PERSON"); d["_entry"] = en; W.append(d)
    return W

# ── scopes ────────────────────────────────────────────────────────────────────
STUDY_ID_FN = None
def build_scopes(P, A, E, W):
    coch_ev = {e["PHN"] for e in E if e["PLACEMENT_IN_COCHRANE"] == "1"} if E else set()
    rated_w = {w["PHN"] for w in W if w["RATED_COCHRANE_IN_SPELL"] == "1"} if W else set()
    with_spell = {w["PHN"] for w in W} if W else set()
    # incident scope (the validated new-demand population)
    for p in P.values():
        town = p["RESIDENCY_FINAL"] == TOWN; req = p["RATED_FOR_COCHRANE_SITE_FLAG"] == "1"; placed = p["FIRST_PLACEMENT_IN_COCHRANE"] == "1" or p["PHN"] in coch_ev
        p["INCIDENT_SCOPE_REASON"] = "+".join(k for k, v in (("Town resident", town), ("rated for a Cochrane site", req), ("placed in a Cochrane facility", placed)) if v)
        p["INCIDENT_DEMAND_SCOPE"] = "1" if (p["_valid"] and (town or req or placed)) else "0"
        p["INCIDENT_EXCLUDED_BY_GATE"] = "1" if ((town or req or placed) and not p["_valid"]) else "0"
        if p["COHORT"]: pop = p["COHORT"]
        elif p["INCIDENT_DEMAND_SCOPE"] == "1" and p["COCHRANE_PLACEMENT_RESIDENCY_UNRESOLVED"] == "1": pop = "X1 placed in Cochrane, residency unresolved"
        elif p["INCIDENT_DEMAND_SCOPE"] == "1" and req and p["FIRST_PLACEMENT_IN_COCHRANE"] != "1" and p["RESIDENCY_FINAL"] in (NOT, AREA): pop = "X2 rated for a Cochrane site, first placed elsewhere or unplaced, non-Town resident"
        elif p["INCIDENT_DEMAND_SCOPE"] == "1" and req and p["FIRST_PLACEMENT_IN_COCHRANE"] != "1" and p["RESIDENCY_FINAL"] == UNRES: pop = "X3 rated for a Cochrane site, first placed elsewhere or unplaced, residency unresolved"
        elif p["INCIDENT_DEMAND_SCOPE"] == "1": pop = "X4 later Type A/B move into a Cochrane facility, first placed elsewhere, no Cochrane rating"
        else: pop = ""
        p["POPULATION"] = pop
    # activity scope: from the activity records; residency at the activity anchor from sql/18 (or sql/14 for people it carries)
    U = OrderedDict()
    salt = None
    extra = [phn for phn in sorted(rated_w | coch_ev) if phn not in P and phn not in A]   # activity people with no attribute record yet
    for phn in list(P) + [a for a in A if a not in P] + extra:
        src = P.get(phn); act = A.get(phn); d = OrderedDict()
        base = src if src else act
        d["STUDY_ID"] = base["STUDY_ID"] if base else STUDY_ID_FN(phn); d["PHN"] = phn; d["PATIENT_ID"] = base["PATIENT_ID"] if base else ""; d["PHN_PATIENT_ID_MULTIPLICITY"] = base["PHN_PATIENT_ID_MULTIPLICITY"] if base else ""
        d["INCIDENT_DEMAND_SCOPE"] = src["INCIDENT_DEMAND_SCOPE"] if src else "0"; d["POPULATION"] = src["POPULATION"] if src else ""; d["COHORT"] = src["COHORT"] if src else ""; d["D_CLASS"] = src["D_CLASS"] if src else ""
        res_p = act if act else src   # residency at the ACTIVITY anchor when available; otherwise at the demand anchor (sql/14)
        d["ACTIVITY_RESIDENCY_FINAL"] = res_p["RESIDENCY_FINAL"] if res_p else ""; d["ACTIVITY_RESIDENCE_CLASS"] = rclass(res_p["RESIDENCY_FINAL"]) if res_p else "no attributes yet"
        d["ACTIVITY_RESIDENCY_ANCHOR"] = ("activity anchor " + act["ACTIVITY_ANCHOR_DT"] if act else ("demand anchor " + src["DEMAND_DT"] + " (sql/14)" if src else "pending sql/18"))
        town_act = bool(res_p) and res_p["RESIDENCY_FINAL"] == TOWN and phn in with_spell
        d["ACTIVITY_RATED_COCHRANE"] = "1" if phn in rated_w else "0"; d["ACTIVITY_TOWN_RESIDENT_WITH_SPELL"] = "1" if town_act else "0"; d["ACTIVITY_COCHRANE_ADMISSION"] = "1" if phn in coch_ev else "0"
        d["CONSULTANT_ACTIVITY_SCOPE"] = "1" if (phn in rated_w or town_act or phn in coch_ev) else "0"
        d["ACTIVITY_SCOPE_REASON"] = "+".join(k for k, v in (("rated for a Cochrane site", phn in rated_w), ("Town resident with a waitlist spell", town_act), ("admitted to a Cochrane facility", phn in coch_ev)) if v)
        if src and src["INCIDENT_DEMAND_SCOPE"] == "1": status = "incident demand FY2022-FY2026"
        elif src and src["INCIDENT_EXCLUDED_BY_GATE"] == "1" and src["IN_WINDOW"] != "1": status = "pre-window demand (carry-in): demand " + src["DEMAND_DT"]
        elif src: status = "in QA universe, outside incident scope"
        elif act and act["PRIOR_RESIDENTIAL_CARE_BEFORE_WINDOW"] == "1": status = "prior residential care before FY2022 (activity only)"
        elif act: status = "activity only (demand before FY2022 or not new demand)"
        else: status = "activity only; attributes pending sql/18"
        d["ACTIVITY_STATUS"] = status
        d["IN_CONSULTANT_DELIVERABLE"] = "1" if (d["INCIDENT_DEMAND_SCOPE"] == "1" or d["CONSULTANT_ACTIVITY_SCOPE"] == "1") else "0"
        # attributes for the consultant person file: incident anchor when in incident scope, else activity anchor
        attr = src if (src and src["INCIDENT_DEMAND_SCOPE"] == "1") else (act or src)
        d["ATTRIBUTE_ANCHOR"] = ("demand event " + src["DEMAND_DT"] if (attr is not None and attr is src) else ("activity anchor " + act["ACTIVITY_ANCHOR_DT"] + " (" + act["ACTIVITY_ANCHOR_TYPE"] + ")" if act else "pending sql/18"))
        for k in ("DEMAND_DT", "DEMAND_FYE", "DEMAND_EVENT_TYPE", "FIRST_PLACEMENT_DT", "PLACEMENT_FYE", "FIRST_PLACEMENT_SITE", "FIRST_PLACEMENT_STREAM", "FIRST_PLACEMENT_IN_COCHRANE", "DAYS_TO_PLACEMENT", "DAYS_TO_PLACEMENT_ALT", "DAYS_WAITING_AS_OF_FOLLOWUP", "AGE_AT_DEMAND", "AGE_GROUP_AT_DEMAND", "AGE_AT_PLACEMENT"):
            d[k] = src.get(k, "") if (src and src["INCIDENT_DEMAND_SCOPE"] == "1") else ""
        for k in ("ACTIVITY_ANCHOR_DT", "ACTIVITY_ANCHOR_FYE", "ACTIVITY_ANCHOR_TYPE"): d[k] = act.get(k, "") if act else ""
        for k in ("FIRST_WAITLIST_APPEARANCE", "FIRST_APPROVAL_DT", "LAST_SEEN_ON_LIST", "ON_LIST_AT_FOLLOWUP", "DOB", "DOB_SOURCE", "DOB_CONFLICT_FLAG", "DOB_DIFFERENCE_DAYS", "SEX", "SEX_SOURCE", "AGE_AT_ANCHOR", "AGE_GROUP_AT_ANCHOR", "AGE_AT_FIRST_WAITLIST",
                  "RESIDENCY_FINAL", "RESIDENCY_SOURCE", "RESIDENCE_CLASS", "RESIDENCE_POSTAL_CODE_INVALID", "RESIDENCE_COMMUNITY", "RESIDENCE_COMMUNITY_SOURCE", "RESIDENCE_LOCAL_NAME", "RESIDENCE_REFERENCE_TYPE", "RESIDENCE_REFERENCE_FYE", "RESIDENCE_REFERENCE_DATE", "COCHRANE_TOWN_FLAG", "COCHRANE_CATCHMENT_FLAG",
                  "ORIGIN_SETTING", "ORIGIN_SETTING_DETAIL", "ORIGIN_SITE", "ORIGIN_CONFLICT_FLAG", "MOST_FREQUENTLY_OBSERVED_RATED_SITE", "RATED_CARE_STREAM_MOST_FREQUENT", "N_SITES_RATED", "RATED_FOR_COCHRANE_SITE_FLAG", "COCHRANE_SITES_RATED", "DEATH_DT"):
            d[k] = attr.get(k, "") if attr else ""
        d["ATTRIBUTES_AVAILABLE"] = "1" if attr else "0"
        U[phn] = d
    return U

# ── QA ────────────────────────────────────────────────────────────────────────
def qa(P, U, expect, have, E, W, A):
    out = []; fail = 0
    def chk(label, n):
        nonlocal fail
        ok = n == 0; fail += (not ok); out.append((label, n, "ok" if ok else "FAIL")); return ok
    coh = [p for p in P.values() if p["COHORT"]]; inc = [p for p in P.values() if p["INCIDENT_DEMAND_SCOPE"] == "1"]; D = [u for u in U.values() if u["IN_CONSULTANT_DELIVERABLE"] == "1"]
    chk("duplicate STUDY_ID across the consultant person file", len(D) - len({u["STUDY_ID"] for u in D})); chk("duplicate PHN across the consultant person file", len(D) - len({u["PHN"] for u in D}))
    chk("empty / placeholder PHN in the consultant person file", sum(1 for u in D if len(u["PHN"]) != 9 or set(u["PHN"]) == {"0"}))
    chk("cohort member not in incident scope", sum(1 for p in coh if p["INCIDENT_DEMAND_SCOPE"] != "1")); chk("incident-scope person not in the consultant file", sum(1 for p in inc if U[p["PHN"]]["IN_CONSULTANT_DELIVERABLE"] != "1"))
    chk("death before demand inside A-D", sum(1 for p in coh if p["DEATH_DT"] and day(p["DEATH_DT"]) < p["_dem"])); chk("placement before demand", sum(1 for p in coh if p["_pl"] and p["_pl"] < p["_dem"]))
    chk("placement after 2026-03-31 used for A/C", sum(1 for p in coh if p["COHORT"] in ("A", "C") and p["_pl"] and p["_pl"] > FOLLOW_UP)); chk("D with a placement observed by follow-up", sum(1 for p in coh if p["COHORT"] == "D" and p["_pl"]))
    chk("A placement not in Cochrane", sum(1 for p in coh if p["COHORT"] == "A" and p["FIRST_PLACEMENT_IN_COCHRANE"] != "1")); chk("C placement in Cochrane", sum(1 for p in coh if p["COHORT"] == "C" and p["FIRST_PLACEMENT_IN_COCHRANE"] == "1"))
    chk("B not (non-Town and placed in Cochrane)", sum(1 for p in coh if p["COHORT"] == "B" and not (p["RESIDENCY_FINAL"] in (NOT, AREA) and p["FIRST_PLACEMENT_IN_COCHRANE"] == "1"))); chk("A/C/D not Town resident", sum(1 for p in coh if p["COHORT"] in ("A", "C", "D") and p["RESIDENCY_FINAL"] != TOWN))
    c = Counter(p["COHORT"] for p in coh); dc = Counter(p["D_CLASS"][:2] for p in coh if p["COHORT"] == "D"); chk("D1+D2+D3 != D", 0 if dc["D1"] + dc["D2"] + dc["D3"] == c["D"] else 1)
    chk("DAYS_TO_PLACEMENT populated for an unplaced person", sum(1 for p in inc if p["DAYS_TO_PLACEMENT"] != "" and not p["_pl"])); chk("negative DAYS_TO_PLACEMENT", sum(1 for p in inc if p["DAYS_TO_PLACEMENT"] != "" and p["DAYS_TO_PLACEMENT"] < 0))
    chk("implausible age (<18 or >110) at anchor, consultant file", sum(1 for u in D if u["AGE_AT_ANCHOR"] not in ("", None) and not (18 <= u["AGE_AT_ANCHOR"] <= 110)))
    chk("negative age at any event", sum(1 for p in inc for k in ("AGE_AT_DEMAND", "AGE_AT_FIRST_WAITLIST", "AGE_AT_PLACEMENT") if p[k] is not None and p[k] < 0)); chk("age at placement < age at demand", sum(1 for p in inc if p["AGE_AT_PLACEMENT"] is not None and p["AGE_AT_DEMAND"] is not None and p["AGE_AT_PLACEMENT"] < p["AGE_AT_DEMAND"]))
    chk("DOB consensus contradicts two agreeing sources", sum(1 for p in inc if p["DOB_SOURCE"].startswith("CONSENSUS") and p["DOB"] not in (p["DOB_STRATA"], p["DOB_REGISTRY"], p["DOB_EPIC"])))
    chk("Registry sex and Epic sex disagree", sum(1 for u in D if U[u["PHN"]].get("SEX_REGISTRY_EPIC_DISAGREE") == "1" or (P.get(u["PHN"]) or {}).get("SEX_REGISTRY_EPIC_DISAGREE") == "1"))
    chk("Strata placeholder address used to resolve residency", sum(1 for p in inc if p["RESIDENCY_SOURCE"] == "STRATA_ADDRESS_H" and p["STRATA_ADDRESS_IS_PLACEHOLDER"] == "1")); chk("community set while residency unresolved", sum(1 for u in D if u["RESIDENCY_FINAL"] == UNRES and u["RESIDENCE_COMMUNITY"]))
    chk("residency established by an invalid postal code (rev 2.10)", sum(1 for u in D if u["RESIDENCY_SOURCE"] == "STRATA_ADDRESS_H" and u["RESIDENCY_FINAL"] != UNRES and u["RESIDENCE_POSTAL_CODE_INVALID"] == "1"))
    chk("origin conflict resolved by arbitrary choice (raw set while tied)", sum(1 for p in list(P.values()) + list((A or {}).values()) if p["ORIGIN_CONFLICT_FLAG"] == "1" and p["ORIGIN_SETTING_RAW"]))
    if "PATIENT_ID" in have: chk("cohort member without a Strata PATIENT_ID", sum(1 for p in coh if not p["PATIENT_ID"]))
    if E is not None:
        first_ev = {(e["PHN"], e["_ad"]) for e in E}; placed = [p for p in coh if p["_pl"]]
        chk("placed A-D person whose first placement is absent from the event table", sum(1 for p in placed if (p["PHN"], p["_pl"]) not in first_ev))
        chk("event outside 2021-04-01..2026-03-31", sum(1 for e in E if e["_ad"] and not (WIN_START <= e["_ad"] <= FOLLOW_UP))); chk("event with no PHN", sum(1 for e in E if not e["PHN"]))
        chk("Cochrane-site event whose person is missing from the consultant file", sum(1 for e in E if e["PLACEMENT_IN_COCHRANE"] == "1" and (e["PHN"] not in U or U[e["PHN"]]["IN_CONSULTANT_DELIVERABLE"] != "1")))
    if W is not None:
        byp = defaultdict(list)
        for w in W: byp[w["PHN"]].append(w)
        listed = [p for p in coh if p["_fw"]]
        chk("A-D person with a waitlist record but no spell in the waitlist table", sum(1 for p in listed if p["PHN"] not in byp)); chk("A-D person whose first spell entry != FIRST_WAITLIST_APPEARANCE", sum(1 for p in listed if p["PHN"] in byp and min(w["_entry"] for w in byp[p["PHN"]]) != p["_fw"]))
        chk("waitlist spell outside the window", sum(1 for w in W if not (WIN_START <= w["_entry"] < WIN_END)))
        chk("Cochrane-rated waitlist person missing from the consultant file", sum(1 for phn in {w["PHN"] for w in W if w["RATED_COCHRANE_IN_SPELL"] == "1"} if phn not in U or U[phn]["IN_CONSULTANT_DELIVERABLE"] != "1"))
    if A is not None: chk("activity-scope person without attributes (sql/18 gap)", sum(1 for u in D if u["ATTRIBUTES_AVAILABLE"] != "1"))
    got = (c["A"], c["B"], c["C"], c["D"]); chk(f"A/B/C/D differs from accepted {expect} (got {got})", 0 if got == tuple(expect) else 1)
    return out, fail == 0

# ── summaries ─────────────────────────────────────────────────────────────────
def md(headers, rows):
    s = "| " + " | ".join(headers) + " |\n|" + "|".join("---" for _ in headers) + "|\n"
    for r in rows: s += "| " + " | ".join(str(x) for x in r) + " |\n"
    return s
def wt(rows_, k="DAYS_TO_PLACEMENT"):
    xs = [r[k] for r in rows_ if r[k] != "" and r[k] is not None]
    return ["—"] * 5 if not xs else [len(xs), round(st.median(xs)), round(q(xs, .25)), round(q(xs, .75)), round(st.mean(xs), 1)]
def by_fye(items, key, fn):
    return [[y] + fn([i for i in items if y == "**Total**" or i[key] == y]) for y in FYES + ["**Total**"]]
def dist_tables(people, anchor_key, title):
    S = []
    for lab, key in (("Age band", "AGE_GROUP_AT_ANCHOR"), ("Sex", "SEX"), ("Origin setting at first list entry", "ORIGIN_SETTING"), ("Residence class", "RESIDENCE_CLASS")):
        vals = sorted({p[key] or "(missing)" for p in people}, key=lambda v: (v == "(missing)", v))
        S.append(f"### {title} — {lab} by {anchor_key}\n" + md(["FYE"] + vals, by_fye(people, anchor_key, lambda ys: [sum(1 for p in ys if (p[key] or "(missing)") == v) for v in vals])))
    return S

def summaries(P, U, E, W):
    S = []; coh = [p for p in P.values() if p["COHORT"]]; inc = [p for p in P.values() if p["INCIDENT_DEMAND_SCOPE"] == "1"]
    act = [u for u in U.values() if u["CONSULTANT_ACTIVITY_SCOPE"] == "1"]; D = [u for u in U.values() if u["IN_CONSULTANT_DELIVERABLE"] == "1"]
    S.append("## 0. Populations\n" + md(["population", "people", "definition"], [
        ["INCIDENT_DEMAND_SCOPE", len(inc), "new FY2022-FY2026 Type A/B demand, gated on the demand event; holds A/B/C/D"],
        ["CONSULTANT_ACTIVITY_SCOPE", len(act), "any FY2022-FY2026 activity: spell rated for a Cochrane site, spell as a Town resident, or Cochrane-site admission; no demand gate"],
        ["union = consultant person file", len(D), "each person once, STUDY_ID"], ["in both", sum(1 for u in D if u["INCIDENT_DEMAND_SCOPE"] == "1" and u["CONSULTANT_ACTIVITY_SCOPE"] == "1"), ""],
        ["incident only", sum(1 for u in D if u["INCIDENT_DEMAND_SCOPE"] == "1" and u["CONSULTANT_ACTIVITY_SCOPE"] != "1"), "e.g. Town resident whose demand event was an admission, no window spell"],
        ["activity only", sum(1 for u in D if u["INCIDENT_DEMAND_SCOPE"] != "1"), "demand before FY2022, or already in residential care at the demand event"]]))
    S.append("ACTIVITY_STATUS of the consultant person file: " + "; ".join(f"{k} {v}" for k, v in Counter(u["ACTIVITY_STATUS"].split(":")[0] for u in D).most_common()) + "\n")
    S.append("## 1. Demand-year view — INCIDENT_DEMAND_SCOPE by DEMAND_FYE (person grain). A/B/C/D live here.\n")
    S.append(md(["FYE", "incident-scope people", "A+B+C+D", "A", "C", "D", "A+C+D resident demand", "D1", "D2", "D3", "B"],
        by_fye(inc, "DEMAND_FYE", lambda ys: [len(ys), sum(1 for p in ys if p["COHORT"])] + [Counter(p["COHORT"] for p in ys)[k] for k in "ACD"] + [sum(1 for p in ys if p["COHORT"] in "ACD")] + [Counter(p["D_CLASS"][:2] for p in ys if p["COHORT"] == "D")[k] for k in ("D1", "D2", "D3")] + [Counter(p["COHORT"] for p in ys)["B"]])))
    S.append("D = no Type A/B placement observed in the Calgary/Edmonton Strata placement source by 31 March 2026; D1 rises to the right by censoring.\n")
    S += dist_tables(inc, "DEMAND_FYE", "1. Incident scope")
    S.append("## 2. Waitlist-year view — CONSULTANT_ACTIVITY_SCOPE by LIST_ENTRY_FYE (spell grain, no demand gate)\n")
    if W:
        actset = {u["PHN"] for u in act}; Ws = [w for w in W if w["PHN"] in actset]
        for w in Ws: w["_rc"] = U[w["PHN"]]["ACTIVITY_RESIDENCE_CLASS"]; w["_st"] = U[w["PHN"]]["ACTIVITY_STATUS"].split(":")[0]
        S.append(md(["FYE", "spells", "unique people with a spell starting", "Type A", "Type B", "rated for a Cochrane site", "Town residents", "catchment", "non-Town", "unresolved", "of people: incident demand", "of people: pre-window / carry-in or prior care", "left-truncated"],
            by_fye(Ws, "LIST_ENTRY_FYE", lambda ys: [len(ys), len({w["PHN"] for w in ys}), sum(1 for w in ys if w["CARE_STREAM_AT_ENTRY"] == "Type A"), sum(1 for w in ys if w["CARE_STREAM_AT_ENTRY"] == "Type B"), sum(1 for w in ys if w["RATED_COCHRANE_IN_SPELL"] == "1")]
                + [Counter(w["_rc"] for w in ys)[k] for k in ("Town", "Cochrane catchment", "non-Town", "unresolved")] + [len({w["PHN"] for w in ys if w["_st"] == "incident demand FY2022-FY2026"}), len({w["PHN"] for w in ys if w["_st"] != "incident demand FY2022-FY2026"}), sum(1 for w in ys if w["LEFT_TRUNCATED"] == "1")])))
        S.append(f"Unique people across all five years: {len({w['PHN'] for w in Ws}):,} (a person with spells in several years is counted in each). Unique people with at least one Cochrane-rated spell: {len({w['PHN'] for w in Ws if w['RATED_COCHRANE_IN_SPELL']=='1'}):,}. Entry-day location ties: {sum(1 for w in Ws if w['ORIGIN_CONFLICT_FLAG']=='1'):,} of {len(Ws):,} spells. All spells in the source, any person: {len(W):,} for {len({w['PHN'] for w in W}):,} people.\n")
    else: S.append("Waitlist table not supplied.\n")
    S.append("## 3. Placement-year view — by PLACEMENT_FYE (event grain: every qualifying Type A/B admission)\n")
    if E:
        Ec = [e for e in E if e["PLACEMENT_IN_COCHRANE"] == "1"]
        for e in E:
            u = U.get(e["PHN"]); e["_rc"] = u["ACTIVITY_RESIDENCE_CLASS"] if u else "not in person tables"; e["_st"] = u["ACTIVITY_STATUS"].split(":")[0] if u else "not in person tables"
            p = P.get(e["PHN"]); e["_first"] = "1" if (p and p["_pl"] == e["_ad"]) else "0"; e["_coh"] = p["COHORT"] if p else ""
        S.append("### 3a. Cochrane facilities — every admission to Bethany Cochrane LTC, Hawthorne SL4, Hawthorne SL4D, whoever the person is\n")
        S.append(md(["FYE", "placement events", "unique people", "Bethany Cochrane LTC", "Hawthorne SL4", "Hawthorne SL4D", "Type A", "Type B", "Town", "catchment", "non-Town", "unresolved", "no person attributes"],
            by_fye(Ec, "PLACEMENT_FYE", lambda ys: [len(ys), len({e["PHN"] for e in ys})] + [sum(1 for e in ys if e["PLACEMENT_SITE"] == s_) for s_ in SITES] + [sum(1 for e in ys if e["CARE_STREAM"] == s_) for s_ in ("Type A", "Type B")] + [Counter(e["_rc"] for e in ys)[k] for k in ("Town", "Cochrane catchment", "non-Town", "unresolved", "not in person tables")])))
        def cat(e):
            if e["_coh"] in ("A", "B"): return "first placement of A/B" if e["_first"] == "1" else "later move of an A/B person"
            if e["_coh"] == "C": return "later move of a C person into Cochrane"
            if e["_st"] == "incident demand FY2022-FY2026": return "incident-scope person outside A-D (X1-X4)"
            return "person outside incident demand: " + e["_st"]
        cats = sorted({cat(e) for e in Ec}, key=lambda c_: (not c_.startswith("first"), c_))
        S.append("Who the Cochrane-site admissions are (A+B first placements = 237; every other row is activity the person grain does not count):\n" + md(["FYE"] + cats, by_fye(Ec, "PLACEMENT_FYE", lambda ys: [sum(1 for e in ys if cat(e) == c_) for c_ in cats])))
        actset = {u["PHN"] for u in D}; Ep = [e for e in E if e["PHN"] in actset]
        S.append("### 3b. All qualifying Type A/B admissions of people in the consultant person file, any site\n")
        S.append(md(["FYE", "placement events", "unique people placed", "in Cochrane", "outside Cochrane", "Type A", "Type B", "first placements (incident)", "other admissions"],
            by_fye(Ep, "PLACEMENT_FYE", lambda ys: [len(ys), len({e["PHN"] for e in ys}), sum(1 for e in ys if e["PLACEMENT_IN_COCHRANE"] == "1"), sum(1 for e in ys if e["PLACEMENT_IN_COCHRANE"] != "1"), sum(1 for e in ys if e["CARE_STREAM"] == "Type A"), sum(1 for e in ys if e["CARE_STREAM"] == "Type B"), sum(1 for e in ys if e["_first"] == "1"), sum(1 for e in ys if e["_first"] != "1")])))
        S.append("Origin (admission source_location) of those events: " + "; ".join(f"{k} {v}" for k, v in Counter(e["ORIGIN_SETTING"] for e in Ep).most_common()) + ".\n")
    else: S.append("Event table not supplied.\n")
    S.append("### 3c. Person grain for comparison — FIRST placement of A/B/C by PLACEMENT_FYE\n" + md(["FYE", "people first placed", "in Cochrane (A+B)", "Type A", "Type B", "A", "B", "of B: catchment", "C"],
        by_fye([p for p in coh if p["_pl"]], "PLACEMENT_FYE", lambda ys: [len(ys), sum(1 for p in ys if p["FIRST_PLACEMENT_IN_COCHRANE"] == "1"), sum(1 for p in ys if p["FIRST_PLACEMENT_STREAM"] == "Type A"), sum(1 for p in ys if p["FIRST_PLACEMENT_STREAM"] == "Type B"), sum(1 for p in ys if p["COHORT"] == "A"), sum(1 for p in ys if p["COHORT"] == "B"), sum(1 for p in ys if p["B_CATCHMENT"] == "1"), sum(1 for p in ys if p["COHORT"] == "C")])))
    S.append("## 4. Time to placement — DEMAND_DT to first observed placement, A/B/C only (incident scope)\n")
    placed = [p for p in coh if p["_pl"]]; H = ["group", "n", "median days", "P25", "P75", "mean"]
    rows = [["all placed"] + wt(placed)] + [[f"cohort {k}"] + wt([p for p in placed if p["COHORT"] == k]) for k in "ABC"] + [[s_] + wt([p for p in placed if p["FIRST_PLACEMENT_STREAM"] == s_]) for s_ in ("Type A", "Type B")] + [[f"demand FYE {y}"] + wt([p for p in placed if p["DEMAND_FYE"] == y]) for y in FYES]
    S.append(md(H, rows)); S.append("Later demand years are right-censored at 31 March 2026; their medians are biased low.\n")
    alt = [p for p in placed if p["DAYS_TO_PLACEMENT_ALT"] != ""]
    if alt:
        rows = [["all placed (DAYS_TO_PLACEMENT)"] + wt(placed), ["all placed (DAYS_TO_PLACEMENT_ALT)"] + wt(alt, "DAYS_TO_PLACEMENT_ALT")]
        for k in "ABC": rows += [[f"cohort {k} (primary)"] + wt([p for p in placed if p["COHORT"] == k]), [f"cohort {k} (ALT)"] + wt([p for p in alt if p["COHORT"] == k], "DAYS_TO_PLACEMENT_ALT")]
        S.append(f"### 4a. Approval-precedence sensitivity — {sum(1 for p in alt if p['DAYS_TO_PLACEMENT_ALT'] != p['DAYS_TO_PLACEMENT'])} of {len(alt)} placed people change individual wait\n" + md(H, rows))
    S.append("## 5. Completeness and QA — consultant person file (union)\n")
    rows = []; placed_u = [u for u in D if u["FIRST_PLACEMENT_DT"]]
    for lab, pool, f in (("DOB", D, lambda p: p["DOB"]), ("sex", D, lambda p: p["SEX"]), ("age at anchor", D, lambda p: p["AGE_AT_ANCHOR"] not in ("", None)), ("community of residence", D, lambda p: p["RESIDENCE_COMMUNITY"]),
                         ("origin setting classified (not Unknown)", D, lambda p: p["ORIGIN_SETTING"] not in ("", "Unknown")), (f"first placement site (placed incident people, n={len(placed_u)})", placed_u, lambda p: p["FIRST_PLACEMENT_SITE"]),
                         ("at least one rated site", D, lambda p: p["MOST_FREQUENTLY_OBSERVED_RATED_SITE"] and not p["MOST_FREQUENTLY_OBSERVED_RATED_SITE"].startswith("(")), ("attributes available", D, lambda p: p["ATTRIBUTES_AVAILABLE"] == "1")):
        n = sum(1 for p in pool if f(p)); rows.append([lab, n, len(pool) - n, pct(n, len(pool))])
    S.append(md(["field", "present", "missing", "% present"], rows))
    S.append("Sex source: " + "; ".join(f"{k or 'missing'} {v}" for k, v in Counter(u["SEX_SOURCE"] for u in D).most_common()) + ". DOB source: " + "; ".join(f"{k or 'missing'} {v}" for k, v in Counter(u["DOB_SOURCE"] for u in D).most_common()) + "\n")
    S.append("### 5a. Residence — consultant file\n" + md(["RESIDENCY_FINAL", "community", "reference", "people"], [[a, b, c_, n] for (a, b, c_), n in Counter((u["RESIDENCY_FINAL"], u["RESIDENCE_COMMUNITY"] or "(missing)", u["RESIDENCE_REFERENCE_TYPE"][:22]) for u in D).most_common(30)]))
    S.append("### 5b. Origin setting — consultant file\n" + md(["ORIGIN_SETTING", "detail", "people"], [[a, b, n] for (a, b), n in Counter((u["ORIGIN_SETTING"], u["ORIGIN_SETTING_DETAIL"]) for u in D).most_common()]))
    S.append("### 5c. Scope reasons\n" + md(["ACTIVITY_SCOPE_REASON", "ACTIVITY_STATUS", "POPULATION", "people"], [[a, b, c_ or "-", n] for (a, b, c_), n in Counter((u["ACTIVITY_SCOPE_REASON"] or "(incident only)", u["ACTIVITY_STATUS"].split(":")[0], u["POPULATION"][:2]) for u in D).most_common()]))
    return "\n".join(S)

# ── write ─────────────────────────────────────────────────────────────────────
PERSON_CONSULTANT = ["STUDY_ID", "INCIDENT_DEMAND_SCOPE", "CONSULTANT_ACTIVITY_SCOPE", "ACTIVITY_STATUS", "ACTIVITY_SCOPE_REASON", "POPULATION", "COHORT", "D_CLASS", "ATTRIBUTE_ANCHOR",
    "DEMAND_DT", "DEMAND_FYE", "DEMAND_EVENT_TYPE", "ACTIVITY_ANCHOR_DT", "ACTIVITY_ANCHOR_FYE", "ACTIVITY_ANCHOR_TYPE", "FIRST_WAITLIST_APPEARANCE", "FIRST_APPROVAL_DT", "LAST_SEEN_ON_LIST", "ON_LIST_AT_FOLLOWUP",
    "AGE_AT_DEMAND", "AGE_GROUP_AT_DEMAND", "AGE_AT_ANCHOR", "AGE_GROUP_AT_ANCHOR", "AGE_AT_FIRST_WAITLIST", "AGE_AT_PLACEMENT", "SEX", "SEX_SOURCE",
    "RESIDENCY_FINAL", "RESIDENCE_CLASS", "RESIDENCE_COMMUNITY", "RESIDENCE_COMMUNITY_SOURCE", "RESIDENCE_REFERENCE_TYPE", "RESIDENCE_REFERENCE_FYE", "COCHRANE_TOWN_FLAG", "COCHRANE_CATCHMENT_FLAG",
    "ORIGIN_SETTING", "ORIGIN_SETTING_DETAIL", "ORIGIN_SITE", "ORIGIN_CONFLICT_FLAG", "MOST_FREQUENTLY_OBSERVED_RATED_SITE", "RATED_CARE_STREAM_MOST_FREQUENT", "N_SITES_RATED", "RATED_FOR_COCHRANE_SITE_FLAG", "COCHRANE_SITES_RATED",
    "FIRST_PLACEMENT_DT", "PLACEMENT_FYE", "FIRST_PLACEMENT_SITE", "FIRST_PLACEMENT_STREAM", "FIRST_PLACEMENT_IN_COCHRANE", "ACTIVITY_COCHRANE_ADMISSION", "DAYS_TO_PLACEMENT", "DAYS_TO_PLACEMENT_ALT", "DAYS_WAITING_AS_OF_FOLLOWUP"]
EVENT_CONSULTANT = ["STUDY_ID", "ADMISSION_DT", "PLACEMENT_FYE", "PLACEMENT_SITE", "CARE_STREAM", "PLACEMENT_IN_COCHRANE", "ORIGIN_SETTING", "ORIGIN_SETTING_DETAIL", "IS_FIRST_PLACEMENT_INCIDENT", "EVENT_SEQ_FOR_PERSON", "PERSON_RESIDENCE_CLASS", "PERSON_RESIDENCE_COMMUNITY", "PERSON_ACTIVITY_STATUS", "PERSON_COHORT", "PERSON_POPULATION"]
WAIT_CONSULTANT = ["STUDY_ID", "SPELL_SEQ_FOR_PERSON", "LIST_ENTRY_DT", "LIST_ENTRY_FYE", "LIST_LAST_SEEN_DT", "DAYS_OBSERVED", "CARE_STREAM_AT_ENTRY", "ORIGIN_SETTING", "ORIGIN_SETTING_DETAIL", "ORIGIN_CONFLICT_FLAG", "FIRST_APPROVED_DT_IN_SPELL", "RATED_COCHRANE_IN_SPELL", "LEFT_TRUNCATED", "ON_LIST_AT_FOLLOWUP", "PERSON_RESIDENCE_CLASS", "PERSON_ACTIVITY_STATUS", "PERSON_COHORT"]
def write_csv(path, rows, fields):
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(fields)
        for r in rows: w.writerow(["" if r.get(k) is None else r.get(k, "") for k in fields])

def main(a):
    salt = load_salt(a.salt)
    epic = {digits(col(r, "PHN")): r for r in read(a.epic_demo)} if a.epic_demo else None
    P, have = load_incident(a.person, salt, epic); A = load_activity_person(a.activity_person, salt, epic) if a.activity_person else OrderedDict()
    E = load_events(a.events, salt) if a.events else None; W = load_waitlist(a.waitlist, salt) if a.waitlist else None
    global STUDY_ID_FN; STUDY_ID_FN = lambda phn: study_id(salt, phn)
    U = build_scopes(P, A, E or [], W or [])
    checks, ok = qa(P, U, tuple(int(x) for x in a.expect.split(",")), have, E, W, A if a.activity_person else None)
    os.makedirs(a.out, exist_ok=True)
    coh = [p for p in P.values() if p["COHORT"]]; inc = [p for p in P.values() if p["INCIDENT_DEMAND_SCOPE"] == "1"]; act = [u for u in U.values() if u["CONSULTANT_ACTIVITY_SCOPE"] == "1"]; D = [u for u in U.values() if u["IN_CONSULTANT_DELIVERABLE"] == "1"]
    c = Counter(p["COHORT"] for p in coh); dc = Counter(p["D_CLASS"][:2] for p in coh if p["COHORT"] == "D")
    rated_people = {w["PHN"] for w in W if w["RATED_COCHRANE_IN_SPELL"] == "1"} if W else set(); with_spell = {w["PHN"] for w in W} if W else set()
    town_w = [u for u in U.values() if u["ACTIVITY_TOWN_RESIDENT_WITH_SPELL"] == "1"]
    R = ["# Reviewer pre-check — Cochrane planning deliverable (incident demand + activity)\n",
         "Inputs: person `%s`; activity-person %s; events %s; waitlist %s; Epic DOB %s\n" % (os.path.basename(a.person), f"`{os.path.basename(a.activity_person)}`" if a.activity_person else "**not supplied — activity-only people carry no attributes yet**",
            f"`{os.path.basename(a.events)}`" if a.events else "not supplied", f"`{os.path.basename(a.waitlist)}`" if a.waitlist else "not supplied", f"`{os.path.basename(a.epic_demo)}`" if a.epic_demo else "not supplied")]
    R.append("## Populations, reported separately\n" + md(["measure", "count"], [
        ["Incident-demand people (INCIDENT_DEMAND_SCOPE)", len(inc)], ["A / B / C / D", f"{c['A']} / {c['B']} / {c['C']} / {c['D']} — resident demand {c['A']+c['C']+c['D']}"], ["D1 / D2 / D3", f"{dc['D1']} / {dc['D2']} / {dc['D3']}"],
        ["Unique people with a Cochrane-rated Type A/B spell, FY2022-FY2026 (sql/16)", len(rated_people)], ["  of which in incident scope / outside", f"{sum(1 for p in rated_people if p in P and P[p]['INCIDENT_DEMAND_SCOPE']=='1')} / {sum(1 for p in rated_people if not (p in P and P[p]['INCIDENT_DEMAND_SCOPE']=='1'))}"],
        ["Town-resident people with a Type A/B spell, FY2022-FY2026 (residency at activity anchor" + ("" if a.activity_person else "; sql/14 residency only until sql/18") + ")", len(town_w)],
        ["Waitlist spells of activity-scope people / all spells in source", f"{sum(1 for w in W if w['PHN'] in {u['PHN'] for u in act}) if W else '—'} / {len(W) if W else '—'}"],
        ["All Cochrane-facility placement events, FY2022-FY2026 (sql/15)", f"{sum(1 for e in E if e['PLACEMENT_IN_COCHRANE']=='1') if E else '—'} events / {len({e['PHN'] for e in E if e['PLACEMENT_IN_COCHRANE']=='1'}) if E else '—'} people"],
        ["CONSULTANT_ACTIVITY_SCOPE people", len(act)], ["Union of unique people in the consultant deliverables", len(D)],
        ["  in both scopes / incident only / activity only", f"{sum(1 for u in D if u['INCIDENT_DEMAND_SCOPE']=='1' and u['CONSULTANT_ACTIVITY_SCOPE']=='1')} / {sum(1 for u in D if u['INCIDENT_DEMAND_SCOPE']=='1' and u['CONSULTANT_ACTIVITY_SCOPE']!='1')} / {sum(1 for u in D if u['INCIDENT_DEMAND_SCOPE']!='1')}"],
        ["  activity-only people WITHOUT attributes (need sql/18)", sum(1 for u in D if u["ATTRIBUTES_AVAILABLE"] != "1")]]))
    R.append("ACTIVITY_STATUS: " + "; ".join(f"{k} {v}" for k, v in Counter(u["ACTIVITY_STATUS"].split(":")[0] for u in D).most_common()) + "\n")
    R.append("Incident-scope reasons: " + "; ".join(f"{k} {v}" for k, v in Counter(p["INCIDENT_SCOPE_REASON"] for p in inc).most_common()) + f". Excluded by the incident gate but carried as activity: {sum(1 for p in P.values() if p['INCIDENT_EXCLUDED_BY_GATE']=='1')} (" + "; ".join(f"demand {p['DEMAND_DT']}, {p['INCIDENT_SCOPE_REASON']}" for p in P.values() if p["INCIDENT_EXCLUDED_BY_GATE"] == "1") + ")\n")
    Da = [u for u in D if u["ATTRIBUTES_AVAILABLE"] == "1"]
    R.append("## Demographics and attributes (consultant file, people with attributes = %d)\n" % len(Da))
    R.append(f"- Age at anchor complete {sum(1 for u in Da if u['AGE_AT_ANCHOR'] not in ('', None))}/{len(Da)}; bands " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(u['AGE_GROUP_AT_ANCHOR'] or '(missing)' for u in Da).items())) + f"; median {st.median([u['AGE_AT_ANCHOR'] for u in Da if u['AGE_AT_ANCHOR'] not in ('', None)])}. Incident scope: median age at demand {st.median([p['AGE_AT_DEMAND'] for p in inc if p['AGE_AT_DEMAND'] is not None])}, bands " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(p['AGE_GROUP_AT_DEMAND'] for p in inc).items())) + "\n")
    R.append(f"- Sex {sum(1 for u in Da if u['SEX'])}/{len(Da)}: " + ", ".join(f"{k or 'missing'} {v}" for k, v in Counter(u['SEX'] for u in Da).most_common()) + "; source " + ", ".join(f"{k or 'missing'} {v}" for k, v in Counter(u['SEX_SOURCE'] for u in Da).most_common()) + f". Incident scope: {sum(1 for p in inc if p['SEX'])}/{len(inc)}\n")
    R.append(f"- DOB: source " + ", ".join(f"{k} {v}" for k, v in Counter(u['DOB_SOURCE'] for u in Da).most_common()) + f"; Strata-vs-Registry conflicts {sum(1 for u in Da if u['DOB_CONFLICT_FLAG']=='1')}; incident-scope conflicts {sum(1 for p in inc if p['DOB_CONFLICT_FLAG']=='1')} of {sum(1 for p in inc if p['DOB_DIFFERENCE_DAYS']!='')} (Epic sides with: " + ", ".join(f"{k or 'neither'} {v}" for k, v in Counter(p['DOB_EPIC_AGREES_WITH'] for p in inc if p['DOB_CONFLICT_FLAG']=='1' and p['DOB_EPIC']).most_common()) + ")\n")
    R.append(f"- Origin at first list entry: tied {sum(1 for u in Da if u['ORIGIN_CONFLICT_FLAG']=='1')}; " + ", ".join(f"{k} {v}" for k, v in Counter(u['ORIGIN_SETTING'] for u in Da).most_common()) + "\n")
    R.append(f"- Community {sum(1 for u in Da if u['RESIDENCE_COMMUNITY'])}/{len(Da)}; source " + ", ".join(f"{k or 'none (residency unresolved)'} {v}" for k, v in Counter(u['RESIDENCE_COMMUNITY_SOURCE'] for u in Da).most_common()) + "\n")
    R.append("- PHN <-> PATIENT_ID: " + "; ".join(f"{k or 'no Strata patient record'} {v}" for k, v in Counter(u['PHN_PATIENT_ID_MULTIPLICITY'] for u in Da).most_common()) + "\n")
    if W:
        Ws = [w for w in W if w["PHN"] in {u["PHN"] for u in act}]
        R.append("- Annual waitlist (activity scope, LIST_ENTRY_FYE) spells / unique people: " + "; ".join(f"{y}: {sum(1 for w in Ws if w['LIST_ENTRY_FYE']==y)} / {len({w['PHN'] for w in Ws if w['LIST_ENTRY_FYE']==y})}" for y in FYES) + "\n")
    if E:
        Ec = [e for e in E if e["PLACEMENT_IN_COCHRANE"] == "1"]; Ep = [e for e in E if e["PHN"] in {u["PHN"] for u in D}]
        R.append("- Annual placement (PLACEMENT_FYE): Cochrane sites, all people, events / unique — " + "; ".join(f"{y}: {sum(1 for e in Ec if e['PLACEMENT_FYE']==y)} / {len({e['PHN'] for e in Ec if e['PLACEMENT_FYE']==y})}" for y in FYES) + ". Consultant-file people, any site — " + "; ".join(f"{y}: {sum(1 for e in Ep if e['PLACEMENT_FYE']==y)} / {len({e['PHN'] for e in Ep if e['PLACEMENT_FYE']==y})}" for y in FYES) + "\n")
    placed = [p for p in coh if p["_pl"]]; alt = [p for p in placed if p["DAYS_TO_PLACEMENT_ALT"] != ""]
    R.append(f"- Wait time (A/B/C, n={len(placed)}): median {wt(placed)[1]} (P25 {wt(placed)[2]}, P75 {wt(placed)[3]}); DAYS_TO_PLACEMENT_ALT median {wt(alt,'DAYS_TO_PLACEMENT_ALT')[1] if alt else '—'}; {sum(1 for p in alt if p['DAYS_TO_PLACEMENT_ALT']!=p['DAYS_TO_PLACEMENT'])} change\n")
    R.append("## Reconciliation tests\n" + md(["check", "n", "result"], [[l, n, s_] for l, n, s_ in checks]))
    R.append("**Headline change caused by enrichment:** " + ("none — A/B/C/D reproduced exactly" if ok else "**STOP — see failed checks**") + "\n")
    open(os.path.join(a.out, "REVIEWER_PRECHECK.md"), "w").write("\n".join(R))
    if not ok: print("\n".join(R)); sys.exit("QA FAILED — no deliverable files written.")
    write_csv(os.path.join(a.out, "COCHRANE_DEMAND_INTERNAL_QA.csv"), list(P.values()), [k for k in next(iter(P.values())).keys() if not k.startswith("_")])
    write_csv(os.path.join(a.out, "COCHRANE_PERSON_INTERNAL_QA.csv"), list(U.values()), [k for k in next(iter(U.values())).keys() if not k.startswith("_")])
    write_csv(os.path.join(a.out, "COCHRANE_DEMAND_CONSULTANT.csv"), D, PERSON_CONSULTANT)
    if E:
        Dset = {u["PHN"] for u in D}; Ev = [e for e in E if e["PLACEMENT_IN_COCHRANE"] == "1" or e["PHN"] in Dset]
        for e in Ev:
            u = U.get(e["PHN"]); p = P.get(e["PHN"])
            e["IS_FIRST_PLACEMENT_INCIDENT"] = "1" if (p and p["_pl"] == e["_ad"]) else "0"; e["PERSON_RESIDENCE_CLASS"] = u["ACTIVITY_RESIDENCE_CLASS"] if u else "not in person tables"
            e["PERSON_RESIDENCE_COMMUNITY"] = u["RESIDENCE_COMMUNITY"] if u else ""; e["PERSON_ACTIVITY_STATUS"] = u["ACTIVITY_STATUS"].split(":")[0] if u else "not in person tables"; e["PERSON_COHORT"] = p["COHORT"] if p else ""; e["PERSON_POPULATION"] = u["POPULATION"] if u else ""
        write_csv(os.path.join(a.out, "COCHRANE_PLACEMENT_ACTIVITY_INTERNAL.csv"), Ev, [k for k in Ev[0].keys() if not k.startswith("_")]); write_csv(os.path.join(a.out, "COCHRANE_PLACEMENT_ACTIVITY_CONSULTANT.csv"), Ev, EVENT_CONSULTANT)
    if W:
        actset = {u["PHN"] for u in act}; Wv = [w for w in W if w["PHN"] in actset]
        for w in Wv:
            u = U[w["PHN"]]; w["PERSON_RESIDENCE_CLASS"] = u["ACTIVITY_RESIDENCE_CLASS"]; w["PERSON_ACTIVITY_STATUS"] = u["ACTIVITY_STATUS"].split(":")[0]; w["PERSON_COHORT"] = u["COHORT"]
        write_csv(os.path.join(a.out, "COCHRANE_WAITLIST_ACTIVITY_INTERNAL.csv"), Wv, [k for k in Wv[0].keys() if not k.startswith("_")]); write_csv(os.path.join(a.out, "COCHRANE_WAITLIST_ACTIVITY_CONSULTANT.csv"), Wv, WAIT_CONSULTANT)
    head = "# Cochrane continuing-care demand — summary tables\n\nTwo populations (incident demand; consultant activity) and three time bases, never mixed in one metric: **DEMAND_FYE** (person grain, incident scope), **LIST_ENTRY_FYE** (spell grain, activity scope), **PLACEMENT_FYE** (event grain).\n\n"
    open(os.path.join(a.out, "COCHRANE_SUMMARY.md"), "w").write(head + summaries(P, U, E, W))
    print("\n".join(R)); print(f"\nwritten to {a.out}/: " + ", ".join(sorted(os.listdir(a.out))))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--person", required=True); ap.add_argument("--activity-person"); ap.add_argument("--events"); ap.add_argument("--waitlist"); ap.add_argument("--epic-demo")
    ap.add_argument("--salt", default="secrets/study_id_salt.txt"); ap.add_argument("--expect", default="89,148,192,69"); ap.add_argument("--out", default="deliverables")
    main(ap.parse_args())
