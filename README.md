# Cochrane Continuing Care — Demand and Capacity Analysis

Evidence base for the **Bethany Cochrane & Big Hill Lodge campus-of-care needs
assessment**. Five fiscal years, FY2022–FY2026 (years ending 31 March).

Everything here is reproducible from the SQL extracts and the two analysis
scripts. Every published figure traces to a numbered block in
`sql/01_demand_capacity_report.sql`.

> **Status (2026-09-03).** Production headline **accepted mechanically by
> the reviewer** on rev 2.7 and **reproduced exactly by rev 2.9**
> (89 / 148 / 192 / 69, resident demand 350; 0 cohort moves person-by-person).
> Sign-off record in `reference/signoff_2026-09-02.md`. Rev 2.8.3 was
> rejected: its occupancy-based building guard excluded a residential
> condominium and mis-parsed numbered streets. Rev 2.9 removes every
> occupancy-based exclusion from the residency hierarchy; occupancy and
> building normalisation are audit / QA flags only. Unresolved approved
> unplaced 9 (was 11); D maximum 78.
>
> **Deliverable phase** (2026-09-03): person (`sql/14`), placement-event
> (`sql/15`) and waitlist-spell (`sql/16`) extracts run; `analysis/08` builds
> the internal and consultant files with 30 QA gates, reproduces 89/148/192/69,
> and reconciles events and spells back to the person grain. Consultant scope
> 987. Findings, decisions and the reviewer's ten corrections are in
> `reference/deliverable_design.md`. Nothing is external until the reviewer
> clears `REVIEWER_PRECHECK.md`.
>
> Earlier status, rev 2.7 run — all seven gates closed: Definitions:
> *new Type A/B demand arising FY2022–FY2026*; residency = registry latest
> pre-demand address, else the Strata address effective at demand; B = any
> non-Town resident placed in Cochrane. **Headline: A 89 · B 148 · C 192 · D 69
> (13 still waiting / 25 died / 31 exited); resident demand 350.** It is
> robust to every sensitivity the reviewer asked for: registry-only 346;
> approval-date precedence **no change** (259 dates move, all later, none in a
> cohort); the published any-three-year rule 372; Epic address history 352
> (sensitivity only). All twenty-one integrity checks pass on the
> 33,046-person universe. Strata resolves 444 of 525 registry-unresolved
> people; 11 approved-unplaced people remain unresolved under every source,
> so the mathematical maximum on D is 80. **Epic is validated and not
> promoted**: 19% of its addresses at the demand event are facilities, and on
> the Town-relevant cells it disagrees with the registry for a third of the
> people where either says Town. Outside the data: the consultant's
> confirmation of B = non-Town, and ALA's facility reference table (3 of the
> 11 are blocked only by the guard). Everything is in
> `reference/master_cohort_run_2026-09-02.md`. Every figure and correction is in
> `reference/master_cohort_run_2026-09-02.md`.
> The word "province-wide" is **withdrawn permanently for this source**:
> `sql/10_coverage_checks.sql` has been run and the admissions source is the
> Calgary and Edmonton Strata instances only. Every D figure carries that
> qualifier and D3 is an upper bound. Results in
> `reference/coverage_check_results.md`.

---

## The two questions

They look alike and they are not the same question.

| | Question | Grain | Answer |
|---|---|---|---|
| **Demand** | How much continuing care need does the Town of Cochrane generate, and how much is met locally? | one row per **person**, first-ever placement | 317 residents; **69.4% placed outside the town** |
| **Capacity** | Who occupies the beds that already exist in Cochrane? | one row per **admission** | 344 admissions; **57.3% to non-residents** |

Both are true at once, and each strengthens the other. They come from
independent measures, which is why they can corroborate each other.

A third question — **how much local demand never received a bed at all** — is
cohort D, and it is not in the published figures. The 317 is demand that was
eventually served, not total local need. See *Cohort D* below for where that
work stands.

Person counts must never be summed across years — the same individual recurs.
Capacity is counted per admission because each admission occupies a bed.

---

## The method, and why it is unusual

Most analyses of this kind read residence off the placement record. That
cannot work here, and the reason is worth stating before any figure is used.

**The placement system records where people were *admitted*, not where they
*lived*.** Three fields look as though they answer "was this person from
Cochrane", and none of them do:

- `source_location` is the facility a person arrived *from*. Someone who went
  home → hospital → a Calgary nursing home → Bethany Cochrane appears as
  arriving from Calgary.
- Address history **updates to the facility on admission**. Within this cohort,
  50 address records point at the Bethany Cochrane campus itself. Counting
  those as Cochrane residents lets the destination facility manufacture its own
  demand. The same address appears in 24 different spellings.
- Postal code is recorded inconsistently and is frequently stale.

**The provincial registry solves it.** It holds one row per person per fiscal
year — the postal code they lived at that year — going back to the 1990s. That
allows a question no placement system can answer: *where did this person live
in the years before they entered care?*

Pre-care years cannot contain a facility address, because the person was not
yet in a facility. The contamination problem does not get cleaned up — it gets
designed out, by choosing a window in which it cannot occur.

### The four steps

1. **Anchor on entry to residential care.** For each person, their first-ever
   Type A or Type B admission. Day programs and hospital transition units are
   excluded from this test — they are not residential care, and anchoring on
   them sits a median of 1.6 years (max 6.6) too early. Applying that
   restriction changed the anchor for 21% of the cohort.
2. **Look back three fiscal years**, ending the year *before* care began. The
   entry year itself is excluded so a mid-year move into a facility cannot leak
   in. Three years matches the health authority's own lookback cap; in practice
   the window length is immaterial — two-year and five-year windows return an
   identical set of people.
3. **Resolve the postal code to a legal boundary.** Town of Cochrane is the
   Statistics Canada census subdivision (`CSDNAME_2021 = COCHRANE`,
   `CSDTYPE_2021 = T`), 568 postal codes. Two tempting shortcuts were tested
   and rejected: the reference table's `municipality` field labels 22 Rocky
   View County codes as Cochrane, and the T4C prefix splits 562 Town against 41
   county addresses.
4. **Fix residence once, per person.** Origin does not change because someone
   later moved beds, so a transfer between two Cochrane facilities cannot
   convert an outside resident into a local one.

### Two things that are easy to get wrong

**Two wait clocks, never blended.** New placements run from
`assessed_approved_date`; transfers run from `enabled_for_transfer_date`. The
pathway test is *"`enabled_for_transfer_date` is populated"* — **not**
*"`assessed_approved_date` is null"*. Legacy records have the approval date
backfilled to equal the admission date, producing a fake 0-day wait on
year-long transfer waits. Medians for the two clocks differ by an order of
magnitude; blending them yields a figure that describes neither.

**Town versus catchment.** Town of Cochrane (568 postal codes) is the
municipality. The Cochrane catchment (1,177 codes) adds Springbank and rural
Rocky View — areas the facilities serve but the town does not govern. The
headline uses the Town. The catchment adds a further 86 residents, of whom 81
were also placed outside Cochrane.

---

## Scope

**In:** Type A (long-term care) and Type B (supportive living level 4,
including dementia), province-wide — a Cochrane resident can be placed
anywhere. Both the pre- and post-2024 naming of Type B ("DAL" / "DSL4") appear,
because the five-year window straddles the renaming. Cochrane sites are
`CAL - Bethany Cochrane LTC_`, `CAL - Hawthorne SL4_`, `CAL - Hawthorne SL4D`.

**Out:**

- **Level 3 supportive living (PCH / DEL / DSL3).** Cochrane has no level-3
  capacity at all, so "could they get a local bed" has no local bed to compare
  against. 3 Town residents across five years. It is still *tagged* in the
  query rather than dropped at source, because the anchor at step 1 must see
  it: if someone's first-ever residential admission was level 3, that is
  genuinely when they entered residential care, and dropping it would misdate
  their residency window. The exclusion is applied at the `placement` CTE.
- **50 people already in residential care before 2021-04-01.** Their in-window
  admission is a later placement, not a first one, so they are out of the
  demand figures. They remain in the capacity figures, because they still
  occupy a bed.

---

## What the analysis does *not* measure

State these whenever a figure is quoted.

- **It is conditioned on placement.** Residents still waiting, who withdrew, or
  who died before a bed opened are not counted. The 317 is local demand that
  was eventually *served* — not total local need.
- **Destinations are not named.** The analysis records whether a placement was
  in Cochrane, not which community it was in. Naming destinations needs the
  facility reference table from the health authority.
- **`service_provider_rating` is not a preference rank.** An earlier draft read
  it that way. Tested against the waitlist source: of 344 admissions into
  Cochrane facilities, 285 were to a site the person had **never** listed as a
  preference — and 187 of those carry a rating of 1. The block that used it is
  withdrawn, not corrected (block 5 in `01_demand_capacity_report.sql`). Do not
  reinstate it. Recorded preference lives in the waitlist source.

**Direction of error.** Residents placed elsewhere are found only through a
registry address. Gaps in registry coverage can therefore only *understate*
displacement, never inflate it. **69.4% is a floor.**

---

## Cohort D — the people who never got a bed

The placement analysis is conditioned on placement. Cohort D is everyone else:
still waiting, withdrew, or died before a bed opened. `sql/05_waitlist_spells.sql`
and `analysis/06_exit_classification.py` cover it.

**The census is daily** — 1,826 consecutive dates over five years, one row per
person per rated site per day. It has to be collapsed, but *not* by dropping
`census_date`, which destroys the entry date the whole question rests on.
Collapse into **spells** — a continuous run of days on the list, where a gap of
more than one day means the person came off and returned.

Why spells rather than min/max per person: **29.3% of people leave the list and
come back.** Merging those separate waits inflated the longest wait from a
median of 45 days to 247 — a 5x overstatement.

### Three misreadings this code exists to prevent

**1. A death date is not "died waiting."** 37.9% of spells carry one; only
17.3% of those died without ever being placed. The rest were placed and died in
care afterwards, which is what long-term care is. Reading the first as the
second overstates deaths-on-the-waitlist by **5.8x** — and it is the most
quotable number in the whole analysis, so it is the one that will be repeated.

**2. `current_location` is not a join key.** It is a census snapshot that moves
while people wait (52.5% change setting); `source_location` is fixed at
admission. Joining them drops ~13% of admissions outright and makes placed
people look like they were never placed — silently, because it is a LEFT JOIN.
It is an output column, never a key. Taking `birth_date` from the admissions
side has the same shape of failure: it leaves every never-placed person with no
age, which is exactly the group that needs one.

**3. Vanishing from the census is not an exit.** 39% of apparent
disappearances continue under a new `patient_transfer_id` within 90 days. The
person was re-registered, not lost. Without that test the unexplained residual
reads 18.8%; with it, 11.4%.

### Exit classification, five years province-wide

82,994 spells · 52,873 people · all care types including hospice and palliative.

| Exit | Spells | Share |
|---|---|---|
| Placed | 33,509 | 40.4% |
| Placed, died later in care | 21,030 | 25.3% |
| Left list, outcome unknown | 9,501 | 11.4% |
| **Died waiting** | **5,445** | **6.6%** |
| Left list, died later | 4,983 | 6.0% |
| Re-registered under a new transfer | 4,240 | 5.1% |
| Still waiting (censored) | 2,415 | 2.9% |
| Returned to the list later | 1,869 | 2.3% |

### Two figures that must travel with a qualifier

**The died-waiting window is a judgement call.** 7 days gives 4,555; 30 gives
5,445; 180 gives 7,199 — a 58% spread. State the window in the same sentence
as the number, every time, and do not let it drift between drafts.

**Hospice and palliative inflate every death figure.** 58% of spells entering
from a hospice or palliative setting carry a death date, against 37.9% overall.
Those clients were expected to die. Report Type A/B separately — the SQL tags
`care_stream` for exactly this.

Also worth carrying: of those who left without a placement, 83% had an
`assess_approved_date` and were genuinely ready for a bed. The other 17% were
still in process and were never waiting; they do not belong in cohort D.

### Four problems found in review, and what was done

Each was confirmed in the data before it was fixed.

| | Problem | Measured | Fix |
|---|---|---|---|
| 1 | Query 05 bounded the admission only from below, so a placement during a later spell was credited to every earlier spell of the same transfer | **2,890 spell rows wrongly marked placed**; 99.7% of those admissions belong to the later spell | Admission now bounded above by the next spell's entry (`spell_b` CTE) |
| 2 | Query 07 classified a person with no registry match as *not a resident* — the unresolved branch could never fire because the GROUP BY always produced a row | Every unmatched person fell through to non-resident; D systematically understated | Two explicit UNRESOLVED classes: no registry record, and no address inside the lookback window. "Not a resident" now requires an address in the window that is somewhere else |
| 3 | Cohort D was read from the first spell's exit reason, not the person's whole pathway | **4,598 people (8.7%)** show no placement on their first spell and were placed later | `ever_placed` / `first_placement_date` computed across all spells per person; 06 gained a person-level block |
| 4 | A/C selected on placement-in-window, D on list-entry-in-window — different populations, and the bias understates unmet demand. The census also left-truncates: **1,604 people** were already on the list on day one | Anchor-agreement test (block V) was necessary but not sufficient | `sql/08_master_cohort.sql`: one demand event per person, residency read there, outcome read forward. `left_truncated` flag on every row so figures run with and without |

### Second review — ten more findings, all confirmed

| | Finding | Measured | Fix in `sql/09` rev 2 |
|---|---|---|---|
| 1 | Placement after 2026-03-31 could still make someone A or C | — | Outcome capped at `follow_up_end`; later placements carried as `first_placement_after_followup` for sensitivity only. Checker now tests for it |
| 2 | Demand event was first census appearance, not approval | 8.2% of list-appearers are never approved; approval precedes first appearance for 710 of 735 | Demand event = `coalesce(assess_approved_date, calculated_assess_approved_date)`; never-approved carried with `was_approved = 0` and excluded from A–D |
| 3 | "Still waiting" was not identified; the checker relabelled "no placement observed" as still waiting | 2,414 people on the census on the last day | D split: **D1** on list at follow-up · **D2** died before placement · **D3** exited, no placement observed in source |
| 4 | Level 3 dropped from the first-ever-admission test, so a Level 3 → Type A transfer looked like new demand | — | Two vocabularies: historical residential scope (A, B, Level 3, legacy codes) for "already in care"; reporting scope (A, B) for outcomes |
| 5 | **"Province-wide" is not demonstrated** | **Confirmed by check 1:** 936 sites / 294,659 admissions in CAL+EDM against 7 sites / 204 admissions in the other three zones | Claim withdrawn permanently. D3 is an upper bound; every D figure carries "in the Calgary and Edmonton Strata instances" |
| 6 | Residency = *any* Town address in 3 prior FY, not residence *at* the demand event | — | Both methods carried: `residency_any3` (published) and `residency_latest`. Checker prints the person-level transition matrix and the cohort impact. Published rule unchanged; effect measured |
| 7 | Inner join to the postal lookup deleted registry rows with unmapped codes into "no registry record" | — | LEFT join; `residency_missing_reason` in four classes |
| 8 | Checker printed every table before exiting on integrity failure | — | Stops immediately; nothing below the checks is printed |
| 9 | No placement-after-follow-up integrity test | — | Added, plus five others |
| 10 | NULL `source_location` dropped by `<>`; same-day ties resolved arbitrarily | 11 NULL sources in 55,642; 0 same-day ties in the Cochrane cohort | `is distinct from`; deterministic tiebreak (Cochrane first, then site) with `n_sameday_first` reported |

Also found: `CAL - Retired - DAL` (1,759 admissions) and `CAL - Retired - DEL`
(47) are not in the published vocabulary. Check 2 shows both end in 2012, so
they are historical only — in the already-in-care scope, never an outcome.
Whether they are the pre-rename Type B and Level 3 codes is still an ALA
question but only affects pre-2012 history.

### Strata address history as a secondary residency source (rev 2.5)

For people the registry cannot resolve, `sql/09` rev 2.5 consults Strata's
`address_h`, under the rules as specified: registry stays primary and is
never overwritten; Strata is used only where `residency_latest = 'UNRESOLVED'`;
the address used is the one **effective on the demand date**, latest
`effective_from` winning; residency comes from the **same postal geography as
the registry**, never from `city_name`; nothing effective after the demand
date is used; an older address with nothing active at demand is reported with
its staleness, not classified. Outputs: `strata_address_at_demand`,
`strata_postal_code_at_demand`, `strata_city_at_demand`, `strata_residency`,
`residency_source` ∈ {REGISTRY, STRATA_ADDRESS_H, UNRESOLVED},
`residency_final`. Cohorts are computed on `residency_final`;
`cohort_registry_only` is kept so Strata's effect is visible.

Three things the data forced beyond the rules:

- **Join through `patient_h`, not `patient`.** A 9-row sample and the query
  that produced it show `address_h.id` is the address record and its rows are
  date-ranged versions, reachable from the patient's pointer — but if a move
  creates a new record, the current pointer misses history. Every distinct
  `(patient, address_id)` pair from `patient_h` is used. `patient_h` is itself
  versioned by `service_provider_id` and must be reduced to distinct first, or
  every address version arrives four times. **`sql/11` decides whether anyone
  has more than one address record; run it before trusting rev 2.5.**
- **Facility guard.** 32 Quigley Dr — the Bethany Cochrane campus — appears in
  `address_h` as a residence. An address version shared by 3 or more distinct
  people is treated as a facility and never used to classify residency, or a
  Cochrane facility would manufacture Town residents. Reported, not dropped.
- **Out-of-province postal codes.** A code absent from the Alberta geography
  whose first letter is not T is classified not-Cochrane; an unmapped T-code
  stays unresolved. The reviewer's own example (V3Z 9T1, Surrey BC) can only
  resolve this way and it is still a postal-code rule, not a city-name one.

`effective_from_date` often equals the record's `creation_date`; the checker
reports how many Strata resolutions rest on a creation date.

### Epic / Connect Care address history — validation only, not in the hierarchy

A third residency source exists: `DB_SOURCE_EPIC_CLARITY.RAW.PAT_ADDR_CHNG_HX`
joined to `IDENTITY_ID` on `PAT_ID` with `IDENTITY_TYPE_ID = '221'` for the
PHN. **It is not in the production hierarchy.** `sql/09` rev 2.7 carries it as
`epic_*` columns and a `cohort_epic_sens` column; `residency_final` and
`cohort` are unchanged from rev 2.6.

The first sample raises the question the validation must answer first: every
visible `EFF_START_DATE` is **2026-09-01** — the day before it was pulled —
and several rows are zero-length with every address field null. That is the
signature of a load or migration timestamp, not a residence period. If it
holds across the table, no Epic row can be active on a 2021–2025 demand date
and the source is at best a current-address snapshot. `sql/12` block 2
quantifies it; the checker reports how many "active at demand" rows rest on a
start date equal to the source-wide maximum.

The rest of `sql/12` covers: whether 221 is the PHN and its uniqueness;
digit-length validation before any padding; facility, PO Box and placeholder
detection by concurrent occupancy; postal mapping through the same geography
table (never `CITY_HX`); and the control case, PHN 49833-8261, which Strata
places in Surrey on 2021-06-01. The checker's Epic block reports the
active-at-demand distribution, class conflicts (never resolved by choosing —
`CONFLICT` is a verdict), the agreement matrix against Registry where
Registry is known, what Epic does to the remaining unresolved, and the
sensitivity cohort.

### The controlling logic: one person-level demand cohort

Each person's **demand event** is the earliest of their first Type A/B
**approval** date and their first Type A/B admission. Everyone who was ever
ready for a bed has one — including the people never placed. Residency is read
at that event; the outcome is read forward to 2026-03-31 and no further.

| Cohort | Cochrane resident at demand event | Placed by end of follow-up | Where |
|---|---|---|---|
| A | yes | yes | Cochrane |
| B | no | yes | Cochrane |
| C | yes | yes | outside |
| D1 | yes | no — **on the list at follow-up** | — |
| D2 | yes | no — **died before placement** | — |
| D3 | yes | no — **exited, no placement observed in source** | — |

**Resident demand = A + C + D.** Use of Cochrane capacity = A + B, per
admission, from query 01. Rated or preferred site is analysed separately
(query 03) and never substituted for actual placement.

**D means "no Type A/B placement observed in this source by 2026-03-31"**, not
"never got a bed". D3 in particular may contain people placed in a zone the
source does not cover. `d_class` keeps D1/D2/D3 apart. Do not collapse them
into one word in prose.

**Cohort D is filtered on residency, not on who rated Cochrane.** Only 159 of
the 317 placed Town residents ever rated a Cochrane site — about half. Building
D from Cochrane-raters would miss half of it and select on willingness to ask
rather than on where people live.

**Query 09 is the paste-and-run form of 08** and needs nothing materialised
first. Its output is one row per person; `analysis/07_master_cohort_check.py`
runs thirteen integrity checks that must all pass (it stops otherwise),
tabulates A–D with D1/D2/D3, reports both residency rules with the transition
matrix, sizes the unresolved-residency upper bound on D from people with a
Cochrane signal only, and reconciles person by person against the published
A/B/C. The first real run is recorded in
`reference/master_cohort_run_2026-09-02.md`; every one of the 31 people who
moved or vanished in reconciliation is an intended effect of a review fix, and
the file says which.

Rev 2.2 gated the unresolved pool on a recorded Cochrane request. **That was
a regression and is withdrawn in rev 2.3**: it is the request-based selection
rule already rejected for D itself, and only 55% of known Town demand ever
recorded a Cochrane request, so the gate biased the uncertainty downward. Rev
2.3 returns the full audit universe with a `cochrane_facing` presentation
flag, and resolves the unresolved further instead of dropping them —
`residency_fallback` is the latest mapped address before the demand event at
any distance, with its staleness reported. The checker reports D in tiers:
primary, + fallback-Town, + truly unresolved (mathematical maximum).

### Not to be used yet

- any cohort D number
- A + C + D as total Cochrane resident demand
- the 11.4% "outcome unknown" as a final business category
- any wait time derived from min-to-max census dates where people can re-enter
- any statement of the form "X% of Cochrane demand was unmet" until censoring
  and follow-up are handled by query 08

### Still open

`PERS_REAP_END_DATE` on the registry is a registration/eligibility end, not a
death date — registration also ends on out-of-province migration and
administrative lapse. Vital statistics
(`DB_SOURCE_AH_VITAL_STATS.CURATED.TB_VITAL_STATS_DEATHS_ADHOC`, joined
`phn = stkh_num_1`) is the source used here, and it validates cleanly: 6
impossible records out of 82,994.

The 9,501 "outcome unknown" spells are the last real gap — candidates are
withdrawal, out-of-province moves, or placement into a facility the admissions
table does not cover.

---

## Repository layout

```
sql/
  01_demand_capacity_report.sql   the report tables — every published figure
  02_client_level_detail.sql      one row per episode, for validation
  03_waitlist_rated_sites.sql     the waitlist census, for recorded preference
  05_waitlist_spells.sql          cohort D — spells, exits, deaths (corrected)
  07_cohort_d_residency.sql       cohort D — list-entry residency, diagnostic (corrected)
  08_master_cohort.sql            CONTROLLING: one demand event per person, A–D derived
  09_master_cohort_standalone.sql paste-and-run master cohort, rev 2 — one row per person
  10_coverage_checks.sql          zone coverage, legacy codes, NULL sources, ties, approval fields
  11_address_h_key_validation.sql proves the Strata join; A2 active-at-demand, E facility candidates, G raw PHN digits
  12_epic_address_validation.sql  Epic PAT_ADDR_CHNG_HX source validation — run before Epic is ever promoted
analysis/
  04_displacement_check.py        joins 02 and 03 — the 138-of-220 finding
  06_exit_classification.py       validates and classifies 05's output
  07_master_cohort_check.py       validates 09's output, tabulates A–D, reconciles vs 02
reports/
  cochrane-report.html            full evidence paper
  cochrane-onepager.html          one-page summary of findings
  Where-Cochrane-Residents-Are-Placed.docx
  Cochrane-Demand-and-Capacity-Summary.docx
build/
  build-docx.js                   generates the report .docx
  build-onepager-docx.js          generates the one-pager .docx
reference/
  cochrane_address_lookup.csv     129 Cochrane-tagged addresses, pre-classified
  coverage_check_results.md       outputs of sql/10 with interpretation (run 2026-09-02)
  master_cohort_run_2026-09-02.md working run record across revisions 2.1-2.7
  signoff_2026-09-02.md           FINAL: production 89/148/192/69, D split, sensitivities, the 11 unresolved
```

### Running things

```bash
# report tables (Snowflake) — 01 also emits its own integrity checks
snowsql -f sql/01_demand_capacity_report.sql

# displacement cross-reference, from the two CSV exports
python3 analysis/04_displacement_check.py placement.csv waitlist.csv

# cohort D — classify exits, with the sensitivity and integrity checks
python3 analysis/06_exit_classification.py spells.csv --window 30 --rereg 90

# A/B/C/D from one base — run sql/09 in Snowflake, export, then:
python3 analysis/07_master_cohort_check.py master.csv --published client_level.csv

# regenerate the Word documents after editing the builders
cd build && npm install && node build-docx.js && node build-onepager-docx.js
```

The HTML reports are self-contained single files — open them in a browser, or
print to PDF (the one-pager carries a print stylesheet).

---

## Validation

`sql/01_demand_capacity_report.sql` emits section 7 with its own integrity
checks. Two of them are hard gates — if either fails, nothing should be
circulated until the cause is found:

| Check | Required | Result |
|---|---|---|
| Every demand record is that person's first-ever residential admission | 100% | 100% |
| Demand population is one row per person | equal | 546 / 546 |
| Registry linkage rate | high | 100% |
| Duplicate person identifiers | none | 0 |
| Admissions with no computable wait clock | none | 0 |
| Residence verdicts resting on 10+ years of registry history | majority | 86.4% |
| Residence verdicts resting on under 5 years | minority | 5.0% |
| Total in scope | — | 636 people · 776 admissions |

`sql/02_client_level_detail.sql` returns the person-level rows behind every
figure. Filter and pivot it and it must reproduce the report exactly; the two
queries share their logic and should never be edited apart. Level 3 episodes
are deliberately retained in the client extract so a reviewer can apply the
exclusion themselves and see which 3 residents it removes.

---

## Open items

Not blocking anything published, but each would strengthen the case:

1. **A population denominator.** The registry can supply Cochrane residents
   aged 75+ by year. That converts 63 placements a year into a *rate* —
   admissions per 1,000 seniors — benchmarkable against comparable Alberta
   communities and projectable against the town's growth. Single most useful
   number not yet in hand, and it needs no external request.
2. **Run `sql/09` rev 2.8** to confirm the hardening changes nothing (the
   local re-evaluation predicts Epic sensitivity 89 / 149 / 193 / 69). Then
   the consultant confirms B = non-Town. Still for ALA (a facility reference
   table is now the most useful of these — it would resolve 3 of the 11
   remaining): a Central-zone source; the Retired-DAL/DEL codes; which approval
   field is operational. Waitlist history before 2021-04-01 would additionally
   resolve the 1,604 left-truncated people and turn the 138 displacement floor
   into a count.
3. **Confirm with ALA:** the meaning of `rating = 0` in the waitlist source,
   and the DAL → Type B crosswalk in writing.
4. **An allocation question, deliberately unpublished.** 62% of Town residents
   placed *outside* Cochrane had asked for a Cochrane site, against 22% of
   those who *got* one. That is a question for the health authority about how
   allocation works, not a finding — it is not in either report.
