# Final query set for the Cochrane continuing-care deliverable

Five Snowflake extracts feed one build script. Run in the order below; each
is paste-and-run and returns one result grid, exported to CSV.

| Order | Query | What it returns | Rows returned (2026-09-03 run) | Feeds |
|---|---|---|---|---|
| 1 | `14_deliverable_person.sql` | One row per person with new Type A/B demand in FY2022-FY2026 who is Cochrane-facing or rated for a Cochrane site, with the validated A/B/C/D cohort (sql/09 rev 2.10 logic, byte-identical classification) plus demographics, residence, origin at first list entry, rated sites, placement and QA columns. Full column list at the end of the file. | 1,140 | `analysis/08 --person` |
| 2 | `15_deliverable_events.sql` | One row per qualifying Type A/B admission in FY2022-FY2026, all people (Calgary + Edmonton Strata instances; source differs from destination; TEST site excluded). | 39,993 | `analysis/08 --events` |
| 3 | `16_deliverable_waitlist.sql` | One row per waitlist spell in FY2022-FY2026 (contiguous census days per person and transfer record; a gap of more than one day opens a new spell), with the entry-day location tie audited rather than broken. | 66,432 | `analysis/08 --waitlist` |
| 4 | `17_epic_dob_review.sql` | Connect Care date of birth and sex per PHN on the Type A/B waitlist in the window, for the two-of-three DOB consensus and the sex fallback. QA input only. | 38,972 | `analysis/08 --epic-demo` |
| 5 | `18_deliverable_activity_person.sql` | One row per person with any Cochrane-related activity in FY2022-FY2026 (rated for a Cochrane site, waitlist spell as a Town resident, or Cochrane-site admission), with residence, demographics, origin and rated sites measured at the first activity in the window. No cohort columns. Generated from sql/14 with the anchor changed; no new-demand gate, no prior-care exclusion. | 1,241 | `analysis/08 --activity-person` |

`09_master_cohort_standalone.sql` (rev 2.10) is the production cohort query on
which sql/14 is built and against which the reviewer reproduced
A = 89, B = 148, C = 192, D = 69. It is kept for the record; the deliverable
itself is produced from sql/14, which contains it.

## Build

```
python3 analysis/08_deliverable_build.py \
  --person   <sql14 export>.csv \
  --events   <sql15 export>.csv \
  --waitlist <sql16 export>.csv \
  --epic-demo <sql17 export>.csv \
  --activity-person <sql18 export>.csv
python3 analysis/09_deliverable_docs.py --gates 43
python3 analysis/10_deliverable_workbook.py
```

`analysis/08` refuses to write any file unless all 43 reconciliation gates pass,
including A/B/C/D = 89/148/192/69 and resident demand = A + C + D = 350 in
every fiscal year. Outputs go to `deliverables/` (git-ignored). The STUDY_ID
salt lives in `secrets/` (git-ignored); STUDY_IDs are stable only while it is
unchanged.

## Fixed parameters (identical in every query)

- Window: census and admissions from 2021-04-01, before 2026-04-01; follow-up end 2026-03-31.
- Reporting-scope care types: CAL Long Term Care, EDM LTC (Type A); CAL Supportive Living Level 4, Level 4 Dementia, EDM DSL4 / DSL4D (Type B).
- Cochrane sites: `CAL - Bethany Cochrane LTC_`, `CAL - Hawthorne SL4_`, `CAL - Hawthorne SL4D`.
- PHN: exactly nine digits, not all zeros; registry PHNs of one to eight digits are left-padded (numeric storage), zero or more than nine digits rejected.
- Residency: Provincial Registry latest mapped address in the three fiscal years before the anchor, else the Strata address effective on the anchor date, mapped through the Statistics Canada postal geography; placeholder addresses and invalid or dummy postal codes never classify.
