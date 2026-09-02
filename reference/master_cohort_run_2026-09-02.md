# Master cohort — runs of 2026-09-02

Output of `sql/09_master_cohort_standalone.sql` **rev 2.3** (full audit
universe, 33,003 people), validated by `analysis/07_master_cohort_check.py`
**rev 4**, which applies the fourth-review rules. **All fourteen integrity
checks pass.** That is a data-integrity result, not a methodological sign-off.

Three runs — rev 2.1 (1,139 rows), rev 2.2 (653), rev 2.3 (33,003) — give the
same primary A/B/C/D. The checker recomputes every cohort from residency ×
placement × location and compares it with the SQL's own column; the two agree
for all 33,003 people.

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

| Cohort | | **Primary** (latest address) | | Sensitivity (any-3-year) | |
|---|---|---|---|---|---|
| A | resident, placed in Cochrane | **87** | 25.1% | 90 | 24.2% |
| C | resident, placed outside | **191** | 55.2% | 208 | 55.9% |
| D | resident, no placement in source by 2026-03-31 | **68** | 19.7% | 74 | 19.9% |
| | **resident demand A + C + D** | **346** | | 372 | |
| B | **non-Town** resident, placed in Cochrane | **143** | | 140 | |
| | of which Cochrane catchment | 6 | | | |
| — | Cochrane placement, residency unresolved (own category) | 9 | | | |
| | **A + B — every Cochrane placement with known residency** | **230** | | | |

The two rules differ for 37 of 653 people, all in one direction — 24 Town → not
a resident, 11 catchment → not a resident, 2 Town → catchment. Nobody moves
into Town. The D share is 19.7% against 19.9%; the story does not change.

### D by class — primary

| | People | Share of D |
|---|---|---|
| D1 still on the list at follow-up | 12 | 17.6% |
| D2 died before any placement | 25 | 36.8% |
| D3 exited, no placement observed in source | 31 | 45.6% |

- 7 people in D were placed **after** 2026-03-31 (sensitivity only).
- 1 person in D received a Level 3 bed instead of the Type A/B bed approved.
- D1 sits almost entirely in FY2026 (9 of 12) — censoring, not a trend.

### By fiscal year of demand event — primary

| FYE | A | C | D1 | D2 | D3 |
|---|---|---|---|---|---|
| 2022 | 20 | 27 | 0 | 7 | 5 |
| 2023 | 23 | 45 | 0 | 10 | 5 |
| 2024 | 18 | 47 | 1 | 5 | 6 |
| 2025 | 16 | 44 | 2 | 3 | 9 |
| 2026 | 10 | 28 | 9 | 0 | 6 |

### Days from approval to first placement — primary, placed only

| | n | median | p90 |
|---|---|---|---|
| A | 87 | 39 | 364 |
| B | 137 | 31 | 361 |
| C | 191 | 21 | 304 |

## Residency uncertainty around D — full universe, no request-based gate

Why a request gate is wrong, from this data: only **190 of 346 (54.9%)** of
known Town demand ever recorded a Cochrane request; among those actually
placed, **141 of 278 (50.7%)**. Absence of a request says nothing about
residency and must not narrow the pool. Rev 2.2's gate is withdrawn; rev 2.3
returns everyone.

Unresolved on the primary rule, approved, unplaced, **province-wide: 114**,
of which **113 are valid records** (one is the all-zero PHN). 57 have no
registry record; 56 have a registry record but no year in the lookback.

| | D |
|---|---|
| **Primary** | **68** |
| **Mathematical maximum** — primary + every valid unresolved person counted as Town | **181** |

The maximum is deliberately extreme and is **not an estimate**. Nothing
reduces it: not the fallback, not a proportional allocation.

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
| A | 87 | 5 | 0 | 0 | 3 | 2 | 97 |
| B | 0 | 132 | 0 | 0 | 7 | 5 | 144 |
| C | 0 | 0 | 191 | 0 | 18 | 11 | 220 |
| **TOTAL** | 87 | 137 | 191 | 0 | 28 | 18 | **461** |

**Kept cohort 410 of 461; changed or absent 51.** On the sensitivity rule the
same matrix keeps 428 of 461 with 33 changed — the reviewer's arithmetic; an
earlier message's "428 of 459, 31" was a miscount.

Every off-diagonal cell, with its reason from the extract:

| From → to | n | Reason |
|---|---|---|
| C → none | 15 | latest address not Cochrane (any-3-year said Town) — the residency-rule change |
| C → absent | 11 | not in master: approval before the window, or already in residential care at the demand event |
| B → none | 6 | unresolved at the earlier anchor (registry record, no year in lookback) |
| B → absent | 5 | not in master, as above |
| A → B | 3 | latest address not Cochrane (any-3-year said Town) |
| A → B | 2 | not Cochrane under both rules at the earlier anchor |
| A → absent | 2 | not in master, as above |
| A → none | 2 | unresolved at the earlier anchor |
| C → none | 2 | unresolved at the earlier anchor |
| C → none | 1 | now Cochrane catchment |
| B → none | 1 | unresolved (no registry record) |
| A → none | 1 | now Cochrane catchment |

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
- Primary figures: **A 87 · B 143 · C 191 · D 68 (12 / 25 / 31)**; resident
  demand 346; sensitivity 372. Reviewer status after the fourth pass: A, C and
  resident demand accepted under the latest-residence definition; D
  mechanically validated with the source-coverage wording mandatory; B
  resolved at 143 on the reviewer's recommendation, pending the consultant's
  confirmation that B means non-Town.
- Nothing here goes into the report until the reviewer clears it, and every D
  figure carries "no Type A/B placement observed in the Calgary/Edmonton
  Strata placement source by 31 March 2026".
- Rev 2.3 has been run; rev 2.4 (PHN validity, record_valid, the B rule,
  residency_evidence) and rev 2.5 (Strata `address_h` as a secondary residency
  source, gated on `sql/11`) are written and not yet run. Rev 2.5 will change
  the unresolved pool and possibly A/B/C/D; the checker's rule-10 block reports
  exactly what moved and why. The checker rev 4 already
  applies the rev 2.4 rules to the rev 2.3 extract, which is where the figures
  above come from. 35 people are left-truncated in the full universe, none in
  any cohort.
