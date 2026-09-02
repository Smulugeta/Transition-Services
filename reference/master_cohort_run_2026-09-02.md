# Master cohort — first real run, 2026-09-02

Output of `sql/09_master_cohort_standalone.sql` rev 2.1 (1,139 people),
validated by `analysis/07_master_cohort_check.py`. **All thirteen integrity
checks pass.** That is a data-integrity result. It is not a methodological
sign-off, and nothing here is cleared for the report until the reviewer has
read it.

## The four cohorts

Person-level. A / C / D are Town of Cochrane residents under the published
residency rule (any Town address in the three fiscal years before the demand
event). Demand event = approval date, or admission if never approved.

| Cohort | | People | Share of resident demand |
|---|---|---|---|
| A | resident, placed in Cochrane | 90 | 24.2% |
| C | resident, placed outside | 208 | 55.9% |
| D | resident, no placement in source by 2026-03-31 | 74 | 19.9% |
| | **resident demand A + C + D** | **372** | |
| B | non-resident, placed in Cochrane | 134 | |

Never approved and excluded: 0 in this extract.

### D by class — different findings, never one word

| | People | Share of D |
|---|---|---|
| D1 still on the list at follow-up | 14 | 18.9% |
| D2 died before any placement | 26 | 35.1% |
| D3 exited, no placement observed in source | 34 | 45.9% |

- **D3 is an upper bound.** The source is the Calgary and Edmonton Strata
  instances; a resident placed in Central zone is invisible here and lands in
  D3. D3 last-seen dates cluster in FY2026 (15 of 34), and median time from
  approval to last seen is 138 days.
- 9 people in D were placed **after** 2026-03-31 (8 of them D1). They are D by
  the follow-up rule and are carried as sensitivity only.
- 1 person in D received a Level 3 bed instead of the Type A/B bed approved.
- Upper bound: 8 people are unresolved residency, unplaced, and carry a
  recorded Cochrane request. If every one were a Town resident, D would be 82.

### By fiscal year of demand event

| FYE | A | C | D1 | D2 | D3 |
|---|---|---|---|---|---|
| 2022 | 20 | 31 | 0 | 8 | 5 |
| 2023 | 24 | 48 | 0 | 10 | 6 |
| 2024 | 19 | 50 | 1 | 5 | 7 |
| 2025 | 16 | 48 | 2 | 3 | 10 |
| 2026 | 11 | 31 | 11 | 0 | 6 |

D1 sits almost entirely in FY2026, as censoring predicts. Do not read the D
share as a trend across years.

### Days from approval to first placement (placed only)

| | n | median | p90 |
|---|---|---|---|
| A | 90 | 37 | 364 |
| B | 134 | 31 | 361 |
| C | 208 | 21 | 304 |

Same direction as the published wait (A 32 / C 18 / B 30) on the
approval-to-admission clock; not the same population, so not the same number.

## Residency: published rule vs latest-address rule

37 of 1,139 people (3.2%) change verdict. 24 go Town → not a resident, 11
catchment → not a resident, 2 Town → catchment. Nobody moves *into* Town.

| Cohort | Published rule (any3) | Latest address | Diff |
|---|---|---|---|
| A | 90 | 87 | −3 |
| B | 134 | 137 | +3 |
| C | 208 | 191 | −17 |
| D | 74 | 68 | −6 |
| **A + C + D** | **372** | **346** | **−26** |

The published rule is not changed. This is the measured cost of changing it:
26 people who had a Cochrane address two or three years before their demand
event but were somewhere else in the most recent year. Whether they are
"Cochrane demand" is a definitional call for the reviewer, not the query.

## Reconciliation against the published A / B / C

Published (query 02 demand basis) vs master, person by person:

| | Published | Master | Diff |
|---|---|---|---|
| A | 97 | 90 | −7 |
| B | 144 | 134 | −10 |
| C | 220 | 208 | −12 |
| D | — | 74 | |

428 people keep their cohort (A 90, B 132, C 206). The 31 who do not, with
reasons — every one is an intended effect of a review fix:

- **19 absent from the master extract.** All have zero days in care before
  placement and all are NEW PLACEMENT; 15 were admitted in the first year of
  the window. Their approval predates 2021-04-01, so under the temporal
  alignment their demand arose before the window and they are excluded from
  A/C — exactly as an equivalent never-placed person is excluded from D.
  (Confirm by pulling `first_approval_dt` for these PHNs; a handful may
  instead have pre-window residential history under the widened historical
  vocabulary, which is the same class of exclusion.)
- **12 in the extract with no cohort.** 11 became UNRESOLVED: the earlier
  anchor shifted their three-year lookback onto years for which they have no
  registry address (short registry histories, 1–4 years). 1 became Cochrane
  catchment rather than Town.
- **2 moved A → B.** Under both residency rules they were not Cochrane
  residents three years before their approval; they were three years before
  their admission 12–16 months later.

## Left-truncation

1 person flagged. With approval as the demand event, a pre-window approval is
an exclusion, not a flag — see the 19 absent above.

## Unresolved residency — what the first run got wrong

Rev 2.1 kept every unresolved person in the province in the output (526 of
1,139 rows; 490 with no Cochrane link at all) and the checker then printed
"upper bound on D: 188". That number is meaningless. Rev 2.2 keeps an
unresolved person only with a recorded Cochrane request or a Cochrane
placement, and the checker computes the bound from those alone. On this run
the honest figure is **8**, not 114.

The unresolved rate among people with a Cochrane link is about 5%, consistent
with the published cohort's LOW-confidence share.

## Status

- Cohort D is **measurable and reconciled**, but **not signed off**.
- Do not quote A + C + D, any D figure, or "X% of Cochrane demand was unmet"
  until the reviewer has read this file.
- Every D figure carries "in the Calgary and Edmonton Strata instances".

## For the reviewer

1. Is the temporal alignment as implemented — demand arising in the window,
   pre-window approvals excluded from A/C and D alike — the definition you
   want? It moves the published A/C by −7 / −12.
2. Residency rule: any-address-in-three-years (published) or latest address?
   The difference is 26 people, all one direction.
3. D3 = 34 with the zone caveat. Is that quotable as an upper bound, or does
   it wait for a Central-zone source?
