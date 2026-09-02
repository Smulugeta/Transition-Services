# Master cohort — runs of 2026-09-02

Output of `sql/09_master_cohort_standalone.sql` **rev 2.5** (full audit
universe, 33,002 people, Strata `address_h` as secondary residency source),
validated by `analysis/07_master_cohort_check.py` **rev 5**. **All eighteen
integrity checks pass**, including the five that enforce the Strata rules.
That is a data-integrity result, not a methodological sign-off.

Runs so far: rev 2.1 (1,139 rows), 2.2 (653), 2.3 (33,003), 2.5 (33,002 — the
all-zero PHN is now rejected). The checker recomputes every cohort from
residency × placement × location and compares it with the SQL's own column;
the two agree for all 33,002 people.

## Reviewer decisions adopted (third review)

1. **Temporal alignment approved.** The cohort is **new Type A/B demand arising
   FY2022–FY2026**: people whose approval (or first admission, if never
   approved) fell inside the window. A pre-window approval excludes a person
   from A/C and from D alike. This is *not* "placement activity FY2022–26";
   that is the capacity analysis in query 01 and stays separate.
2. **Residency primary = latest mapped pre-demand address in the lookback.**
   The published any-address-in-three-years rule is the sensitivity.
3. **D3 is quotable descriptively only:** *"exited the observed waitlist with no
   Type A/B placement found in the Calgary/Edmonton Strata placement source by
   31 March 2026."* Not "unmet demand". The source-coverage caveat applies to
   **all of D**, not only D3.
4. Already-in-care is tested against the demand event, not the window start
   (rev 2.3). Zero rows affected on this data.
5. The request-based gate on the uncertainty pool is **removed** (rev 2.3).
   The full audit universe is returned; `cochrane_facing` is a presentation
   flag, never a filter.

## Fourth-review items (rev 2.4 / checker rev 4)

6. **Cohort B = any non-Town resident placed in Cochrane.** Cochrane-catchment
   residents are B (6 people, sub-counted as `b_catchment`), so A + B is every
   Cochrane placement with known residency. Unresolved-residency Cochrane
   placements (9) are their own category, never A or B. This is the reviewer's
   recommendation; it is one line to reverse if the consultant wants the
   narrower "outside the catchment" meaning.
7. **PHN validity.** All-zero or malformed identifiers are rejected in every
   path. The rev 2.3 universe carried one: PHN `000000000`, demand 2024-11-10,
   death 1999-01-09.
8. **Death before demand** is an impossible linkage: 2 people in the universe.
   They stay in the universe with `record_valid = 0` and a reason and can never
   take a cohort. Hard check inside A–D: zero. Neither of the two was in A–D
   before the fix, so 87/143/191/68 are unaffected.
9. **`confidence` renamed `registry_history_depth`** — it measured years of
   registry history, not confidence in residency at demand (71 UNRESOLVED
   people were labelled HIGH). `residency_evidence` replaces it for the verdict
   actually used: STRONG (mapped address in the year before demand), MODERATE
   (in the lookback but not that year), NONE.
10. **The fallback is historical evidence only.** Its addresses are 4–31 years
    old (median 16; median 18 among the unplaced). It no longer reduces the
    residency uncertainty around D.

## The four cohorts

| Cohort | | **Primary** (registry latest address, else Strata at demand) | | Sensitivity (any-3-year, registry only) | |
|---|---|---|---|---|---|
| A | resident, placed in Cochrane | **89** | 25.4% | 90 | 24.2% |
| C | resident, placed outside | **192** | 54.9% | 208 | 55.9% |
| D | resident, no placement in source by 2026-03-31 | **69** | 19.7% | 74 | 19.9% |
| | **resident demand A + C + D** | **350** | | 372 | |
| B | **non-Town** resident, placed in Cochrane | **148** | | 140 | |
| | of which Cochrane catchment | 6 | | | |
| — | Cochrane placement, residency unresolved (own category) | 9 | | | |
| | **A + B — every Cochrane placement with known residency** | **237** | | | |

Registry-only (rev 2.4 rule, before Strata): A 87 · B 143 · C 191 · D 68 ·
resident demand 346. Strata moves A +2, B +5, C +1, D +1.

The two rules differ for 37 of 653 people, all in one direction — 24 Town → not
a resident, 11 catchment → not a resident, 2 Town → catchment. Nobody moves
into Town. The D share is 19.7% against 19.9%; the story does not change.

### D by class — primary

| | People | Share of D |
|---|---|---|
| D1 still on the list at follow-up | 13 | 18.8% |
| D2 died before any placement | 25 | 36.2% |
| D3 exited, no placement observed in source | 31 | 44.9% |

- 8 people in D were placed **after** 2026-03-31 (sensitivity only).
- 1 person in D received a Level 3 bed instead of the Type A/B bed approved.
- D1 sits almost entirely in FY2026 (10 of 13) — censoring, not a trend.
- The one person Strata added to D lives at a private Cochrane address
  (River Heights, T4C 0J3) effective five weeks before their demand event.

### By fiscal year of demand event — primary

| FYE | A | C | D1 | D2 | D3 |
|---|---|---|---|---|---|
| 2022 | 20 | 27 | 0 | 7 | 5 |
| 2023 | 24 | 45 | 0 | 10 | 5 |
| 2024 | 18 | 47 | 1 | 5 | 6 |
| 2025 | 17 | 45 | 2 | 3 | 9 |
| 2026 | 10 | 28 | 10 | 0 | 6 |

### Days from approval to first placement — primary, placed only

| | n | median | p90 |
|---|---|---|---|
| A | 89 | 39 | 364 |
| B | 148 | 34 | 375 |
| C | 192 | 21 | 304 |

## Strata `address_h` as secondary residency source — rule 10

Gated on `sql/11`; the join is through every distinct (patient, address
record) pair in `patient_h`, and the address used is the version effective on
the demand date, mapped through the same postal geography as the registry.

| | |
|---|---|
| Previously unresolved on the registry | 524 |
| **Resolved by Strata** | **430** — 423 not Cochrane · 4 Town · 3 catchment |
| of those, approved and unplaced | 98 — 97 not Cochrane · 1 Town |
| Remaining unresolved | 94 |

Why the 94 stayed unresolved (disjoint): 48 had a **facility** address at
demand (shared by 3+ people — 150 Scotia Landing NW at 64 people, 300 Prince
of Peace Way at 16, an "NWT Evacuee" placeholder) and were not classified; 40
had an address at demand with no postal code; 5 had no Strata address row; 1
had an Alberta code that fails the geography lookup. Nobody fell under rule 9
(older address only).

Of the 430 resolutions, **107 rest on an out-of-province postal code** (the
reviewer's Surrey example is one) and **229 have an effective-from equal to
the patient record's creation date** — the address was current *at least*
from then. All 7 resolutions to Cochrane or its catchment are private homes,
each shared by exactly one person; no facility slipped under the threshold.

## Residency uncertainty around D — after registry and Strata

Why a request gate is wrong, from this data: only **193 of 350 (55.1%)** of
known Town demand ever recorded a Cochrane request; among those actually
placed, **143 of 281 (50.9%)**.

Unresolved after both sources, approved, unplaced: **15** (8 registry record
with no year in the lookback, 7 no registry record; 3 have a 8–20-year-old
non-Cochrane fallback address, reported as evidence only).

| | D |
|---|---|
| **Primary** | **69** |
| **Mathematical maximum** — primary + every valid unresolved person counted as Town | **84** |

Registry-only the same maximum was 181. The maximum is still deliberately
extreme and **not an estimate**; nothing reduces it.

`residency_fallback` — the latest mapped address before the demand event at
any distance — is reported as **historical evidence only**. Among the 113, it
finds a prior address for 22, all non-Cochrane, **4 to 28 years old, median
18**. A 2008 address does not prove where someone lived in 2024. The other 91
have no pre-demand address at all: 57 no registry record, 34 registry rows
only after the demand event. 7 of the 113 carry a recorded Cochrane request,
reported and not used.

On the sensitivity rule the equivalent maximum is 74 + 113 = 187.

**Corrections on the record:** an earlier message gave the unresolved-with-
request count as 8 (it was 9) and treated the fallback as resolving residency
(it does not). Both rules are withdrawn.

## Reconciliation — full transition matrix, primary rule

Published A/B/C (query 02 demand basis: first-ever placement in window, Level 3
excluded) → master primary cohort. Row and column totals are the arithmetic;
nothing is summarised by hand.

| published \ master | A | B | C | D | none | absent | TOTAL |
|---|---|---|---|---|---|---|---|
| A | 89 | 6 | 0 | 0 | 0 | 2 | 97 |
| B | 0 | 137 | 0 | 0 | 2 | 5 | 144 |
| C | 0 | 0 | 192 | 0 | 17 | 11 | 220 |
| **TOTAL** | 89 | 143 | 192 | 0 | 19 | 18 | **461** |

**Kept cohort 418 of 461; changed or absent 43** (registry-only rev 2.4 rule:
410 and 51 — Strata resolved 8 of the "none" cells). On the sensitivity rule the
same matrix keeps 428 of 461 with 33 changed — the reviewer's arithmetic; an
earlier message's "428 of 459, 31" was a miscount.

Every off-diagonal cell, with its reason from the extract:

| From → to | n | Reason |
|---|---|---|
| C → none | 15 | latest address not Cochrane (any-3-year said Town) — the residency-rule change |
| C → absent | 11 | not in master: approval before the window, or already in residential care at the demand event |
| B → absent | 5 | not in master, as above |
| A → B | 3 | latest address not Cochrane (any-3-year said Town) |
| A → absent | 2 | not in master, as above |
| B → none | 2 | still unresolved after registry and Strata |
| A → B | 2 | not Cochrane under both rules at the earlier anchor |
| C → none | 1 | now Cochrane catchment |
| C → none | 1 | still unresolved after registry and Strata |
| A → B | 1 | now Cochrane catchment (B under the non-Town rule) |

**Correction from the rev 2.3 run.** The rev 2.2 extract showed 19 absent and
I attributed all 19 to pre-window approvals. One of them was a filter
artefact: a published C person who is not a Cochrane resident under any rule
and was dropped by rev 2.2's output filter. On the full universe the absent
count is **18**, all with zero days in care before placement and most admitted
in the first year of the window. Confirm by pulling `first_approval_dt` and
`first_residential_ever` for those 18 PHNs. This is exactly why the audit
universe must not be filtered.

## Status

- Cohort D is **measurable, reconciled, reproducible on two runs, and not
  signed off.**
- Primary figures with Strata: **A 89 · B 148 · C 192 · D 69 (13 / 25 / 31)**;
  resident demand 350; sensitivity 372. Registry-only: 87 / 143 / 191 / 68 =
  346. Reviewer status after the fourth pass (registry-only figures): A, C and
  resident demand accepted; D validated with the source-coverage wording
  mandatory; B at 143 on the reviewer's recommendation pending the
  consultant's confirmation. The Strata increments (+2 / +5 / +1 / +1) are new
  and need the reviewer's pass.
- Nothing here goes into the report until the reviewer clears it, and every D
  figure carries "no Type A/B placement observed in the Calgary/Edmonton
  Strata placement source by 31 March 2026".
- Rev 2.5 has been run (it includes the rev 2.4 rules). One death-before-
  demand record remains in the universe, flagged `record_valid = 0`, in no
  cohort. **`sql/11` blocks A and D have not been reported back**; until block
  A shows whether anyone holds more than one address record, and block D shows
  the Surrey row for PHN 49833-8261, the Strata increments rest on the sample
  evidence only. The checker rev 4 already
  applies the rev 2.4 rules to the rev 2.3 extract, which is where the figures
  above come from. 35 people are left-truncated in the full universe, none in
  any cohort.
