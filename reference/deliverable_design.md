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
| 1 | `sql/14_deliverable_person.sql` — sql/09 rev 2.9 plus enrichment columns (below) | to write after step 0 |
| 2 | `sql/15_deliverable_events.sql` — one row per qualifying Type A/B admission for the universe | to write after step 0 |
| 3 | `analysis/08_deliverable_build.py` — STUDY_ID, QA assertions, four deliverable files, reviewer pre-check | **written; runs today on the rev 2.9 export** with every enrichment field reported as missing |
| 4 | reviewer pre-check (the 12 items) | provisional version produced; final after steps 1–2 |
| 5 | publish `COCHRANE_DEMAND_CONSULTANT`, `COCHRANE_PLACEMENT_ACTIVITY`, `COCHRANE_SUMMARY` | not before the reviewer clears step 4 |

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
