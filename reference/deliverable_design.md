# Cochrane planning deliverable — design and status

Status 2026-09-03. Methodology validation is closed (rev 2.9 reproduces the
accepted production headline). This document is the field-by-field plan for
the final deliverable and records every decision that is still open.

## Controlling rules (unchanged)

- Population logic is the master A/B/C/D framework of `sql/09` rev 2.9.
  Residency hierarchy Provincial Registry → Strata `address_h`; Epic is
  sensitivity/QA only. Production headline A 89 · B 148 · C 192 · D 69,
  resident demand 350; D1 13 / D2 25 / D3 31. Enrichment must reproduce it
  exactly or the build stops (`analysis/08`, `--expect`).
- Two grains, never merged: **person** (unique demand) and **placement
  event** (activity). Event totals are not forced to equal A/B counts.
- `DAYS_TO_PLACEMENT` is NULL without an observed placement by 31 March 2026;
  `DAYS_WAITING_AS_OF_FOLLOWUP` is a separate, labelled censoring field
  populated only for D1.
- Ages at event dates only. No age at today's date anywhere.
- Community of residence comes only from the address that decided
  `RESIDENCY_FINAL`. Fallback registry addresses stay QA evidence.
- Occupancy / building counts are QA flags. No address is excluded on
  facility grounds until ALA supplies a validated facility-address reference.
- Requested Cochrane facility never determines cohort D.

## Pipeline

| Step | Artefact | State |
|---|---|---|
| 0 | `sql/13_enrichment_inventory.sql` — schemas, PHN↔PATIENT_ID multiplicity, origin vocabulary, placeholder addresses, rated sites, demographic completeness, community-name column | **written; awaiting results** |
| 1 | `sql/14_deliverable_person.sql` — sql/09 rev 2.9 plus enrichment; classification CTE byte-identical; output = Cochrane-facing or Cochrane-rated people only, 51 named columns | **run 2026-09-03: 1,139 rows; 89/148/192/69 reproduced; 21 QA checks pass** |
| 2 | `sql/15_deliverable_events.sql` — one row per qualifying Type A/B admission in the window, all people; builder scopes the views | **run 2026-09-03: 39,993 admissions, 32,043 people; every placed cohort member's first placement present; 344 Cochrane-site events** |
| 3 | `analysis/08_deliverable_build.py` — STUDY_ID, QA assertions, four deliverable files, reviewer pre-check | **complete on sql/14 + sql/15**; 25 QA checks pass |
| 4 | reviewer pre-check (the 12 items) | **final version produced 2026-09-03; sent for review** |
| 5 | publish `COCHRANE_DEMAND_CONSULTANT`, `COCHRANE_PLACEMENT_ACTIVITY`, `COCHRANE_SUMMARY` | not before the reviewer clears step 4 |

## Findings from the sql/14 run (2026-09-03)

| Field | Result |
|---|---|
| DOB | 498 of 498, all from Strata patient. Registry also has 496; 466 agree exactly, 30 differ (25 by a month or less: the registry often carries the 15th of the month; 1 by a year; 1 by seven years, PHN …1030, D). Age band at demand depends on the source for 2 people. Strata stays primary; both values and the difference are in the internal file. |
| Sex | 496 of 498 from the Registry (287 F, 209 M); the 2 missing have no registry row at all (both FY2026 entrants). No conflicts across registry years. |
| Community | 498 of 498. All 350 Town residents map to COCHRANE (T) / local name COCHRANE \| SPRINGBANK; the 6 catchment residents to Rocky View County (MD); 3 non-Town people with out-of-province Strata postal codes are labelled "Outside Alberta (postal …)" because the verdict rested on the postal prefix, not a lookup. |
| Origin | 498 of 498; 494 from the waitlist row nearest the demand date (477 on the demand date itself, 21 within 120 days after), 4 from the admission source for admission-only events. Only 13 differ from the first-appearance value used provisionally. |
| Requested site | 401 of 498 rated at least one site (median 2 sites; up to 30). 97 have no rated site on any census row: reported as "(no site rated)", not imputed. Modal sites: Bethany Cochrane LTC 47, Hawthorne SL4 45, Hawthorne SL4D 24. |
| PHN ↔ PATIENT_ID | 1:1 for all 1,137 people with a Strata patient record; 2 unresolved-residency D3 people have no patient record at all (waitlist PHN only). No split records, so no canonical-ID choice was needed. 59 cohort PHNs carry `IDENTIFIER1_IS_AUTOGEN = 1`, yet all 59 have registry rows and DOBs, so the flag does not mean a fabricated PHN here. |
| Placeholder addresses | 17 flagged in the extract (including the new dummy patterns); none resolves residency. |

## Eighth review (2026-09-03) — two populations, not one

The 987-person population is the INCIDENT-DEMAND scope (new FY2022–FY2026
Type A/B demand; holds A/B/C/D). It is not the consultant activity population:
814 people had a Cochrane-rated spell in the window and 117 of them fall
outside the incident gate (demand before FY2022, or already in residential
care at the demand event). They contributed 183 Cochrane-rated spells and 283
spells in all. The fix is conceptual and touches no cohort.

| # | Reviewer requirement | Status |
|---|---|---|
| 1 | Rename the 987 → `INCIDENT_DEMAND_SCOPE` | done |
| 2 | `CONSULTANT_ACTIVITY_SCOPE` from activity records: any FY2022–26 spell rated for a Cochrane site, any spell as a Town resident, no demand gate | done in the builder; residency at the activity anchor needs **sql/18** (activity-person extract: sql/14 with the anchor moved to first window activity, no gate, no prior-care exclusion, no cohort columns) |
| 3 | Placement activity: all Cochrane-site admissions plus placements of Town residents and Cochrane-rated seekers; STUDY_ID preserved | done: event file = Cochrane-site events (all) ∪ events of everyone in the person file |
| 4 | April-2020 people: out of A/B/C/D, in as activity, labelled carry-in | done: `ACTIVITY_STATUS = pre-window demand (carry-in)` |
| 5 | X1–X4 kept; "rated for a Cochrane site" wording | done |
| 6 | Sex: Epic as labelled fallback | done: incident scope 985/987 (Registry 976, Epic 9); Registry-vs-Epic disagreements 0 |
| 7 | DOB: exact two-of-three consensus, QA flag/source kept | done: consensus Strata+Registry+Epic 928, Strata+Epic 44, Registry+Epic 14, Strata single 2, no consensus 1 (Strata kept); median age 83 and bands unchanged |
| 8 | Origin at entry kept; sub-acute folded into Acute Care | done (detail retained) |
| 9 | Placement-site completeness on the placed denominator | done |
| 10 | 39 vs 40 outside-universe Cochrane events | resolved with distinct labels. The earlier "40" folded in the X4 person (in incident scope, unlabelled at the time). Final: 344 Cochrane-site admissions = 237 first placements of A/B + 29 incident-scope X1–X4 + 24 later moves of C people + 15 later moves of A/B people + 39 people outside incident demand (21 in prior residential care before FY2022, 18 with earlier or non-new demand). Neither April-2020 carry-in person has a Cochrane-site admission |
| 11 | `Z1Z1Z1` must not establish residency | **done, sql/09 rev 2.10 + sql/14 + sql/18**: the non-Alberta branch requires a syntactically valid, non-dummy Canadian postal code. sql/14 re-run 2026-09-03 17:04: the Z1Z1Z1 person is now UNRESOLVED (X2 → X3); A/B/C/D 89/148/192/69 unchanged; the QA population gains one row (a second invalid-code person whose residency became unresolved and is therefore Cochrane-facing). All 35 gates pass |

### Populations after the sql/18 run (2026-09-03 17:29, final pre-check)

| measure | count |
|---|---|
| incident-demand people | 987 (A/B/C/D 89/148/192/69; D1–D3 13/25/31) |
| unique people with a Cochrane-rated spell | 814 (697 incident, 117 outside) |
| Town-resident people with a spell, residency at the activity anchor | 405 |
| waitlist spells, activity scope / all | 2,443 / 66,432 |
| Cochrane-facility placement events | 344 for 329 people |
| consultant activity scope | 1,152 |
| union in the consultant deliverables | 1,152 = 987 incident + 2 pre-window carry-in + 109 prior residential care before FY2022 + 54 other activity-only |
| attributes available | 1,152 of 1,152; all 35 gates pass |

Union-file demographics: age at anchor complete, median 83, bands <65 61 /
65–74 170 / 75–84 426 / 85+ 495; sex 1,150 of 1,152 (Registry 1,141, Epic
fallback 9); DOB consensus across all three sources 1,077; community 1,143
(9 residency-unresolved); origin ties 41 of 1,152.

### Populations on the current extracts (before sql/18)

| measure | count |
|---|---|
| incident-demand people | 987 |
| unique people with a Cochrane-rated spell | 814 (697 incident, 117 outside) |
| Town-resident people with a spell (sql/14 residency only) | 351 |
| waitlist spells, activity scope / all | 2,390 / 66,432 |
| Cochrane-facility placement events | 344 for 329 people |
| consultant activity scope | 1,130 |
| union in the consultant deliverables | 1,130 = 987 incident + 2 carry-in + 141 activity-only (attributes pending sql/18) |

sql/18 will add Town residents with a window spell who are outside the incident
universe, so the activity scope will grow beyond 1,130.

## Seventh-review corrections (2026-09-03) — status

| # | Reviewer requirement | Status |
|---|---|---|
| 1 | Ages at event dates (birthday test), age bands, STUDY_ID crosswalk, no PHN/PATIENT_ID external | done in the builder (`age_at`); `AGE_AT_DEMAND / _FIRST_WAITLIST / _PLACEMENT`, `AGE_GROUP_AT_DEMAND`; DOB internal only |
| 2 | Origin = setting at FIRST list entry; audit ties; `N_ORIGIN_LOCATIONS_AT_ENTRY`, `ORIGIN_LOCATION_LIST`, conflict flag; categories Acute Care / Community / Assisted Living or Other CC / Lodge / Out of Province / Other / Unknown | **run**: 37 of 987 tied on the entry day (two locations each); 15 resolve because both values share a category (8 are Home / Rural-Home); 22 disagree (hospital vs home and similar) and are Unknown. Every untied value equals the earlier first-appearance value; the entry census date equals FIRST_LIST_APPEARANCE for all 979 waitlist-driven people |
| 3 | `DOB_CONFLICT_FLAG`, `DOB_DIFFERENCE_DAYS`, Epic review, split `DOB_SOURCE` / `SEX_SOURCE`, "sex" not "gender" | **run**: 51 of 977 in-scope people with both DOBs differ; Epic sides with Strata 36, Registry 14, neither 1. Both material cases (seven years, PHN …1030; one year, …1400, the two whose age band depends on the source) are confirmed by Epic on the Strata date. The 14 Registry-sided cases differ by 20–182 days and change no age band. Strata stays primary; all three dates and the difference are in the internal file. Sex: Registry vs Epic agree for all 976 compared; 9 of the 11 missing Registry values exist in Epic but are NOT filled (Epic is QA only) — reviewer decision |
| 4 | Community for out-of-province Strata addresses from Strata city (labelled); `RESIDENCE_REFERENCE_FYE / DATE` | **run**: 979 of 987 have a community (967 Alberta CSD, 12 labelled Strata city fallback); the 8 without are residency-unresolved and correctly blank. Reference: 947 registry fiscal-year addresses, 32 Strata versions effective on the demand date |
| 5 | `IN_CONSULTANT_SCOPE` from the literal request; reconcile to ~988 | done: **987** on the current extract (see below) |
| 6 | `MOST_FREQUENTLY_OBSERVED_RATED_SITE`; no "preferred" site | renamed in sql/14 and builder; `REQUESTED_COCHRANE_FLAG` and `REQUESTED_COCHRANE_SITES` kept |
| 7 | Waitlist-activity and placement-event tables from the underlying records | **run**: sql/16 gives 66,432 spells for 38,995 people; 2,049 spells for the 987 in-scope people (entry-day ties in 87 spells). Every in-scope A-D person with a waitlist record has a spell and the first spell entry equals FIRST_WAITLIST_APPEARANCE. sql/15: 39,993 admissions |
| 8 | Summary only after those tables pass QA; demand-year / list-entry-year / placement-year kept apart | **done**: 30 reconciliation tests pass; COCHRANE_SUMMARY.md sections 1 (demand-year), 2 (list-entry-year), 3 (placement-year), 4 (wait time), 5 (completeness) |
| 9 | `DAYS_TO_PLACEMENT_ALT` | done: median 28 under both; 5 of 429 placed people change |
| 10 | Return the QA results before the external file | `REVIEWER_PRECHECK.md` items 1-13 |

### Consultant-scope reconciliation (987)

`IN_CONSULTANT_SCOPE` = valid in-window Type A/B demand AND (Town of Cochrane
residence OR any Cochrane/Hawthorne rated site OR any Type A/B admission to a
Cochrane facility, first or later). On the current extract: 987.

- 986 carry a POPULATION label (A-D 498, X1 2, X2 480, X3 6). The 987th is a
  Cochrane-catchment resident first placed at Bow Crest LTC who later moved
  into a Cochrane facility and never rated one; labelled X4.
- Two people meet a criterion but fail the validity gate: both have demand
  events in April 2020 (approved before the window; left-truncated). One is a
  Town resident who rated a Cochrane site and is Cochrane-facing; including
  them would breach the FY2022-FY2026 new-demand definition. The reviewer's
  "approximately 988" most plausibly includes that person.
- 152 QA-population rows are out of scope: 74 catchment residents who neither
  rated nor used a Cochrane site, 49 unresolved-residency people likewise, 27
  non-Town likewise, and the 2 gate-excluded.

## Findings from the sql/15 run (event grain, 2026-09-03)

- 344 admissions to the three Cochrane Type A/B sites in FY2022–FY2026 for 329
  people: Bethany Cochrane LTC 133, Hawthorne SL4 167, Hawthorne SL4D 44.
  By fiscal year 65 / 79 / 72 / 73 / 55.
- Of the 344: 237 are the first placements of A and B (reconciles to A+B);
  2 are X1 first placements; 15 are later moves of A/B people between Cochrane
  sites; **24 are later moves into Cochrane by C people** (Town residents whose
  first placement was outside Cochrane); 26 are later moves into Cochrane by
  non-Town people first placed elsewhere (X2); 40 belong to people outside the
  demand universe (demand before FY2022 or already in care at the demand event).
- Events of A–D people: 556 admissions for 429 people; 127 are moves after the
  first placement, mostly from supportive living (49), long-term care (39) and
  acute hospital (28).
- The 24 C-to-Cochrane moves are a finding for the consultant: C counts the
  first placement only; a person can still reach Cochrane later.

## Provisional pre-check on the rev 2.9 export (2026-09-03)

Everything the current extract can answer, it answers; nothing missing was
invented.

| Item | Result |
|---|---|
| Person rows | universe 33,046; A+B+C+D 498 |
| A/B/C/D | 89 / 148 / 192 / 69; resident demand 350 (reproduced exactly) |
| D1/D2/D3 | 13 / 25 / 31 |
| Annual demand (DEMAND_FYE 2022→2026), A+B+C+D | 95 / 118 / 112 / 103 / 70 |
| Annual first placements (PLACEMENT_FYE), people | 69 / 84 / 96 / 96 / 84; Cochrane 45 / 52 / 52 / 47 / 41 |
| Event totals | await sql/15 |
| DOB, sex/gender, age | not in extract (0 of 498) — sql/13 block 5 decides the source |
| Community of residence | not in extract — needs postal→community from the deciding address (sql/13 block 6 picks the column) |
| Origin setting | 498 of 498 mapped, **provisional**: waitlist location at first list appearance; sql/14 replaces it with the census row nearest `DEMAND_DT`, and `source_location` for admission-only events |
| PHN ↔ PATIENT_ID | sql/13 block 1 |
| Reconciliation checks | 20 of 20 pass |
| Wait time, placed people | median 28 days (P25 13, P75 127); A 39, B 34, C 21; Type A 20, Type B 36. Under `DEMAND_DT_ALT`: 5 of 429 waits differ, medians unchanged (A 39, B 34, C 20) |

## Decisions the reviewer is asked to make

1. **Descriptive groups outside A–D.** The request covers "individuals
   seeking or receiving placement in Cochrane facilities regardless of
   residence". The framework holds those *receiving* (A, B). Those *seeking*
   but not placed in Cochrane are not in any cohort. The builder labels them
   without changing any cohort: X2 = non-Town resident, ever rated a Cochrane
   site in the window, not placed in Cochrane (480: 393 placed elsewhere, 87
   unplaced; 20 of the 480 are Cochrane-catchment). X3 = the same with
   residency unresolved (6). X1 = placed in Cochrane, residency unresolved
   after Registry and Strata (2). Include X1–X3 in the consultant file as
   `POPULATION` values with `COHORT` blank, or omit them?
2. **Correction to the sign-off record.** "Cochrane placement, residency
   unresolved: 9" was computed on registry-only residency. After Strata it is
   2 (Strata resolved 7: A +2, B +5). 239 Cochrane placements in all = 237
   (A+B) + 2. Record and checker corrected.
3. **Origin categories.** The reviewer's list plus one addition used here:
   *Acute care (sub-acute / transition)* for RCTP, transition units, Glenrose,
   subacute and restorative beds (21 of 498). Fold into Acute care, or keep?
   Detail categories are retained in `ORIGIN_SETTING_DETAIL` either way.
4. **Community field.** Statistics Canada CSD name (`csdname_2021` +
   `csdtype_2021`) is proposed as `RESIDENCE_COMMUNITY_AT_DEMAND`, with
   `local_name` as a secondary descriptor. Registry residency yields only a
   postal code, so the community is the CSD of that postal code; Strata
   residency uses the same lookup on the Strata postal code (never
   `city_name`, per rule 5).

## sql/14 enrichment columns (to add on top of sql/09 rev 2.9)

| Field | Source and rule |
|---|---|
| `PATIENT_ID`, `PHN_PATIENT_ID_MULTIPLICITY` | Strata `patient` by valid PHN; canonical ID chosen per the block-1 explanation (never `MIN`) |
| `DOB`, `SEX`, `DEMOGRAPHIC_SOURCE` | one primary source from block 5 with documented fallback; conflicts between duplicate patient rows counted |
| `RESIDENCE_POSTAL_CODE_AT_DEMAND` | the registry postal code of the deciding year, else the Strata postal code active at demand |
| `RESIDENCE_COMMUNITY_AT_DEMAND` | CSD name of that postal code (block 6) |
| `ORIGIN_SETTING_RAW`, `ORIGIN_SOURCE` | approval event: waitlist `current_location` on the latest census date ≤ `DEMAND_DT`, else the earliest after; admission-only event: `source_location` of that admission |
| `REQUESTED_SITE`, `REQUESTED_CARE_STREAM`, `N_SITES_REQUESTED`, `REQUESTED_COCHRANE_FLAG` | waitlist ratings in the window: modal rated site, care type, distinct-site count, any Cochrane rating |
| Placeholder rule | add `ANY STREET`, `TEST`, `SAMPLE`, `DUMMY`, `FAKE` (block 3 vocabulary) to `strata_placeholder` |

## sql/15 placement-event columns

`PHN`, `PATIENT_ID`, `ADMISSION_DT`, `PLACEMENT_SITE`, `CARE_STREAM`,
`PLACEMENT_IN_COCHRANE`, `SOURCE_LOCATION`, for every reporting-scope Type
A/B admission in the window (same `adm_rep` rule as sql/09: source ≠
destination, TEST site excluded). Residency and cohort are joined from the
person table by the builder; `IS_FIRST_PLACEMENT` marks the person-level
anchor so events reconcile to the person grain.

## Consultant file contents

`STUDY_ID` (HMAC-SHA256 of PHN with a project salt kept in `secrets/`, outside
the repository), population and cohort fields, demand and waitlist dates,
ages at events, sex/gender, community, origin setting, requested site,
placement fields, Type A/B, `DAYS_TO_PLACEMENT`, `DAYS_WAITING_AS_OF_FOLLOWUP`.
Removed: PHN, DOB, `PATIENT_ID`, street address, postal code, Epic columns,
QA flags. `deliverables/` and `secrets/` are git-ignored.
