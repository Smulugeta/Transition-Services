# Master cohort — runs of 2026-09-02

Output of `sql/09_master_cohort_standalone.sql` **rev 2.7** (full audit
universe, 33,046 people — 44 of them admitted only under the approval-
precedence anchor), validated by `analysis/07_master_cohort_check.py`
**rev 7**. **All twenty-one integrity checks pass**, including the five that
enforce the Strata rules, the two that gate the alternative anchor, and the
two that keep Epic out of production. That is a data-integrity result, not a
methodological sign-off.

Runs so far: rev 2.1 (1,139 rows), 2.2 (653), 2.3 (33,003), 2.5 (33,002),
2.7 (33,046). The checker recomputes every cohort — primary, registry-only,
any-3-year, approval-precedence and Epic-sensitivity — from residency ×
placement × location and compares each with the SQL's own column; all agree
for every person.

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

## Seven sign-off gates (fifth review)

The reviewer accepted the rev 2.5 rule-10 results as mechanically reproduced
and set seven gates. Status, with what each needs:

| Gate | Status | Finding |
|---|---|---|
| **1 Approval precedence** | **closed — zero impact** | Row-level `min(coalesce(assess, calculated))` vs person-level `coalesce(min(assess), min(calculated))`, both carried end to end. Across 33,046 people: **259 demand dates change (0.8%), every one later; 133 cross a fiscal year; 44 enter the window, 3 leave; 2 residency classes change. A / B / C / D and resident demand: 89 / 148 / 192 / 69 = 350 under both anchors — no person moves cohort.** The people the precedence rule touches are all outside the Cochrane-relevant population. |
| **2 Active addresses at demand** | **closed — tiebreak is moot** | Of 444 people Strata resolved, 442 had exactly one address version active on the demand date and 2 had two; the two competing pairs **agree on class**. No cohort assignment depends on the latest-`effective_from` tiebreak. |
| **3 Surrey proof** | **proven** | PHN 49833-8261: demand 2021-06-01; registry UNRESOLVED → Strata `3288 156A ST, Surrey, V3Z 9T1` effective 2021-05-18 → not Cochrane → `residency_source = STRATA_ADDRESS_H`. |
| **4 Facility audit** | **rebuilt and run** | The ever-shared guard blocked 48, mostly apartment units held by successive tenants. On **concurrent occupancy on the demand date** it blocks **28** (3: 14 · 4: 3 · 6–38: 10 · 513: 1), with **15 placeholder addresses** (NO FIXED ADDRESS, EVACUEE) in their own class. It released 14 apartment-unit cases, which Strata then resolved: 430 → **444** resolutions, 15 → **11** remaining unresolved. The 3–5 tier still holds 17 entries and some are multi-person *households*, not facilities — three people at `2122-78C McKenney Avenue` on the same day, four at `331 21 Auburn Bay St SE` — alongside a real one, `McKenzie Towne Retirement Residence` (n=4). **3 of the 11 remaining are unresolved solely because of the guard.** A facility reference table confirmed by ALA would resolve them and is preferable to any threshold; `sql/11` block E lists candidates. |
| **5 Raw PHN before LPAD** | **fixed and run** | Snowflake `LPAD(x, 9)` truncates a string longer than 9. Rev 2.6+ counts digits first and accepts only exactly nine, with no padding, in the patient, waitlist and death paths. Universe: 0 placeholder or malformed PHNs; 1 death-before-demand record, flagged and in no cohort. Epic's own identities are all exactly nine digits (check 1). |
| **6 Fallback = evidence only** | confirmed | Unchanged since rev 2.4; nothing is removed from the uncertainty pool by a fallback address. |
| **7 B = non-Town** | confirmed | B = 148 with `b_catchment` kept (6). |

## Final validation table — rev 2.7, all columns run

| | Registry only | **Registry + Strata (production)** | Approval precedence | Any-3-year sensitivity | Epic sensitivity |
|---|---|---|---|---|---|
| A resident, placed in Cochrane | 87 | **89** | 89 | 90 | 90 |
| B non-Town, placed in Cochrane | 143 | **148** | 148 | 140 | 149 |
| C resident, placed outside | 191 | **192** | 192 | 208 | 193 |
| D resident, no placement in source | 68 | **69** | 69 | 74 | 69 |
| Resident demand A + C + D | 346 | **350** | 350 | 372 | 352 |
| Unresolved, approved, unplaced | 113 | **11** | 11 | — | 8 |
| D mathematical maximum | 181 | **80** | 80 | — | 77 |

B = any non-Town resident placed in Cochrane, `b_catchment` = 6 kept.
Fallback registry addresses are evidence only.

### The 11 remaining unresolved, approved, unplaced (PHN masked)

| PHN | Demand | Registry | Strata | Epic (sensitivity) | D class |
|---|---|---|---|---|---|
| …8002 | 2021-11-30 | no registry record | no Strata row | — | D3 |
| …5102 | 2022-02-10 | no registry record | no Strata row | — | D3 |
| …2811 | 2022-02-16 | record, no year in lookback | no Strata row | — | D2 |
| …3271 | 2022-09-15 | no registry record | no Strata row | — | D3 |
| …6920 | 2022-09-22 | record, no year in lookback | no Strata row | — | D2 |
| …3831 | 2022-11-04 | record, no year in lookback | facility guard (household, n=3) | — | D2 |
| …3100 | 2022-12-21 | record, no year in lookback | no Strata row | — | D2 |
| …3100 | 2022-12-21 | record, no year in lookback | no Strata row | — | D3 |
| …6131 | 2023-11-20 | record, no year in lookback | address, no postal code | — | D2 |
| …8612 | 2025-08-15 | no registry record | facility guard (household, n=3) | — | D3 |
| …1330 | 2026-02-18 | record, no year in lookback | NO FIXED ADDRESS (placeholder) | — | D1 |

Epic (sensitivity only) classifies 3 of the 11 as not Cochrane and 0 as Town;
8 stay unresolved under every source.

## Epic / Connect Care — validation complete; recommendation: do not promote

| Check | Result |
|---|---|
| 1 PHN identity | 221 is the PHN: 9,384,709 identities, all 9 digits, one per patient, one patient per PHN, zero placeholders |
| 2 Dates | Real event dates: 92.8% of 27.4M rows start before 2026, 43.4% before the window; 3 rows carry the source maximum. Caveat: 4.7M rows (17%) start on the 2019-08-16/17 conversion; only 53 of the cohort's active-at-demand rows rest on one |
| 3–4 Active at demand | 33,001 approved people: **32,934 have exactly one active address, 67 have none, 0 have more than one** |
| 5 Conflicts | none possible — no multiples |
| 6 Geography | mapped through the same postal table; never `CITY_HX` |
| 7 Guards | **6,370 facility addresses (19% of the cohort), 1,043 PO Boxes, 23 placeholders** — not used |
| 8 Agreement with Registry | 25,111 people with both. Overall **99.6%**, but that is the non-Town / non-Town cell (24,784). **On the Town-relevant cells: Registry Town / Epic Town 221 · Registry Town / Epic non-Town 41 · Registry non-Town / Epic Town 65.** Where either source says Town, they disagree for 106 of 327 people (32%). |
| 9–10 The 11 remaining | Epic: 0 Town, 0 catchment, 3 not Cochrane, 8 still unresolved |
| 11 Sensitivity cohort | A +1, B +1, C +1, D +0 — resident demand 352 against 350 |
| Control 49833-8261 | **Not in Epic** — no active address on 2021-06-01, so Epic cannot corroborate or contradict Strata's Surrey verdict |

**Why not promote.** Epic's address at the demand event is the facility or
hospital the person was in for 19% of the cohort — the approval date is
exactly when many people are in an acute bed — so the guard is doing heavy
work and the residual risk is that a sub-threshold facility passes as a home.
On the cells that matter for Cochrane, Epic and Registry disagree for a third
of the people where either says Town; 65 people Registry calls non-Town would
become Town under Epic, which would inflate resident demand with no way to
adjudicate. And it resolves none of the 11 remaining to Town. Epic is a
validated source that adds +1 / +1 / +1 as sensitivity and nothing the
analysis needs. Keep it as sensitivity; report the 352 alongside 350.

## Sign-off state after the rev 2.7 run

- **89 / 148 / 192 / 69 — resident demand 350 — is robust** to: the Strata
  secondary source (+2 / +5 / +1 / +1 over registry-only), approval-date
  precedence (no change), Epic (+1 / +1 / +1 / 0 as sensitivity), and the
  published any-three-year residency rule (372).
- Residency uncertainty around D: 11 unresolved approved-unplaced people;
  mathematical maximum 80. Three of the 11 are blocked only by the facility
  guard and would resolve against a confirmed facility table.
- Still to decide outside the data: the consultant's confirmation that B
  means non-Town (148), and ALA's facility reference table.

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
- Rev 2.5 has been run and its rule-10 results are accepted as mechanically
  reproduced. **Rev 2.7 is written and not yet run**; it closes gates 1, 2, 4
  and 5 and carries Epic address history as sensitivity only. Sign-off on
  89 / 148 / 192 / 69 waits on the gate-1 sensitivity. `sql/11` blocks A1, A2,
  E, G and `sql/12` blocks 1, 2, 7 and the control are to be reported back.
- **Epic is not in the hierarchy.** An early suspicion that `EFF_START_DATE`
  was a load date — every row in a sample of recent rows started 2026-09-01 —
  was **wrong**; block 2 shows real event dates (below).
- **Epic check 1, run 2026-09-02:** under `identity_type_id = 221`,
  **9,384,709 rows = 9,384,709 distinct patients, all exactly 9 digits, zero
  all-zero placeholders.** One identity per patient, no padding or
  truncation risk, and a population-scale count consistent with the
  provincial PHN/ULI. Still to confirm: no PHN held by more than one patient
  (the uniqueness-both-ways statement), cohort coverage (0c), and the
  start-date question (block 2).
- **Epic check 1 closed:** uniqueness both ways is 0 and 0 — no patient with
  two PHNs, no PHN held by two patients.
- **Epic check 2 answered, run 2026-09-02:** 27,410,304 rows; **92.8% start
  before 2026; 43.4% (11.9M) start before the window**; only 3 rows carry the
  source-wide maximum date. `EFF_START_DATE` is a real event date and Epic
  addresses can be active on 2021–2025 demand dates. Caveat: the two largest
  single start dates are **2019-08-16 and 2019-08-17 — 4.7M rows, 17% of the
  table — the Connect Care initial conversion.** Those addresses were carried
  over from legacy systems; an open-ended one is "active" on every later
  demand date while reflecting wherever the person lived in 2019 or earlier.
  Rev 2.7 flags them (`epic_start_is_migration_date`) and the checker reports
  how many Epic resolutions rest on one. A further cluster of starts across
  Oct 2019–Mar 2020 matches first visits after wave-1 go-live. Zero-length
  and address-less rows are a small minority. The checker rev 4 already
  applies the rev 2.4 rules to the rev 2.3 extract, which is where the figures
  above come from. 35 people are left-truncated in the full universe, none in
  any cohort.

## Rev 2.8.1 – 2.8.3 — Snowflake compatibility fixes (no logic change; not yet run)

Rev 2.8 never executed. Three successive compile errors, each fixed in the query
and verified mechanically before resending:

| Rev | Snowflake error | Cause | Fix |
|---|---|---|---|
| 2.8.1 | Unsupported subquery type cannot be evaluated | correlated scalar COUNT subqueries with a date-range predicate; LATERAL in `geo` | pre-aggregated `*_conc_*` CTEs joined on a `hash()` row key; plain subquery in `geo` |
| 2.8.2 | Object STRATA_PLACEHOLDER does not exist | CTE declared after the CTE that joins to it | moved ahead of `strata_addr_k`; all 58 CTEs scanned, no forward reference |
| 2.8.3 | Invalid regular expression … no argument for repetition operator | `(?=…)` lookahead and `\b` are not POSIX ERE | building-key chain rewritten with explicit `(^\|[^A-Z])` edges and replacement backreferences; every regex literal in the file compiled and checked for Perl-only tokens |

One behavioural correction rode along in 2.8.3: a unit designator is stripped only
when followed by a unit number, so "123 MAIN STREET" keeps its street; rev 2.8's
pattern would have reduced it to the civic number. The checker's `bkey()` mirror was
rewritten to the identical chain; on the rev 2.7 export the within-cohort building
count moves from 99 to 100 of 360 Epic Town verdicts in a 3+ occupant building.

Expected on the 2.8.3 run: production unchanged at 89 / 148 / 192 / 69; Epic
sensitivity close to 89 / 149 / 193 / 69 (lower bound from within-cohort keys).

## Rev 2.8.3 — REJECTED by the reviewer (2026-09-03)

Independent comparison against rev 2.7:

| | Rev 2.7 (accepted) | Rev 2.8.3 |
|---|---|---|
| A / B / C / D | 89 / 148 / 192 / 69 | 89 / 148 / **191** / 69 |
| Resident demand | 350 | 349 |
| Strata residencies resolved → UNRESOLVED | — | 172 |
| Unresolved, approved, unplaced | 11 | 50 (41 blocked as "facility") |
| Crude D range | 69–80 | 69–119 |

The lost C client (PHN …4381): registry unresolved; Strata address at demand
`107 1000 Glenhaven Way, Cochrane T4C 1Y9`; blocked because the normalised
building held 16 concurrent patients. Town of Cochrane property records
identify 1000 Glenhaven Way as residential condominium / single-family units.
False-positive facility guard.

Numbered-street parsing defect in the building key: `403-8402 142 STREET` →
`142 ST`, `1206-15503 87 AVENUE NW` → `87 AVE NW`, and so on — the civic number
was stripped as if it were a unit number, so unrelated homes on numbered
streets merged into one "building".

Reviewer's required change: occupancy alone never determines a facility;
replace the exclusion with a known facility-address reference table; until
one exists, occupancy is an audit flag only; building normalisation QA only.

## Rev 2.9 — occupancy is an audit flag, not an exclusion (written; not yet run)

- No occupancy-based exclusion in `strata_residency`, `strata_residency_alt`
  or `epic_residency`. Remaining blocks: placeholder address, PO Box (Epic),
  CONFLICT between active versions.
- Reported, never applied: `strata_occupancy_flag` (exact address ≥ 3
  concurrent on the demand date), `strata_building_occupancy_flag_qa`,
  `strata_building_key_qa`, `strata_building_concurrent_n_qa`,
  `strata_civic_concurrent_n_qa`, and the Epic equivalents.
- `strata_named_facility_candidate` / `epic_named_facility_candidate`: the
  address matches a named Cochrane-area continuing-care site from
  `reference/cochrane_address_lookup.csv`. Flag for validation only.
- Numbered streets protected in the QA key before any leading number is
  treated as a unit: `403-8402 142 STREET` → `8402 142 ST`;
  `322 50 GRANDE AVE` → `50 GRANDE AVE`.
- Checker rev 9: integrity failure if any residency verdict reads
  `NOT USED - facility address`; G4 rewritten as an occupancy audit that lists
  every flagged production resolution and shows the cohort effect of each
  flag class as a sensitivity; `--baseline <rev 2.7 export>` prints the
  per-person cohort transition matrix with a reason for every move.
- Expected: 89/148/192/69 (350). The rev 2.7 exact-address guard blocked 28
  addresses (27 not approved-and-unplaced; nearly all outside Cochrane); those
  now resolve, so any move will appear in the baseline diff with its address.

### Rev 2.9 run — 2026-09-03 09:43 export, checker rev 9, baseline = rev 2.7 export

All 27 integrity tests pass (new: no verdict reads `NOT USED - facility`).

| | Rev 2.7 (accepted) | Rev 2.9 | Moves |
|---|---|---|---|
| A / B / C / D | 89 / 148 / 192 / 69 | 89 / 148 / 192 / 69 | **0 people change cohort** |
| Resident demand | 350 | 350 | |
| Strata-resolved residencies | 444 | 469 | +25, all outside the Cochrane area |
| Unresolved, approved, unplaced | 11 | 9 | the two guard-blocked cases now resolve non-Town |
| D mathematical maximum | 80 | 78 | |
| PHN …4381 (107 1000 Glenhaven Way) | C | C | exact occupancy 1, building-key occupancy 16, verdict Town of Cochrane |

Occupancy audit (G4): 25 production Strata resolutions carry the exact-address
flag (≥ 3 concurrent); every one is outside the Cochrane area and none is in a
cohort, so the flag cannot move A/B/C/D whichever way ALA rules on them. 0
production resolutions match a named Cochrane-area site. The QA building key,
if it were an exclusion, would still drop 177 resolutions and one C (the
Glenhaven case) — it is not fit to exclude and is not used.

Epic sensitivity, no occupancy exclusion: 90 / 149 / 194 / 69 (353); unresolved
6; D maximum 75. Epic occupancy flag on 6,370 people in the universe, named
facility candidate on 146 — audit only.
