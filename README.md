# Cochrane Continuing Care — Demand and Capacity Analysis

Evidence base for the **Bethany Cochrane & Big Hill Lodge campus-of-care needs
assessment**. Five fiscal years, FY2022–FY2026 (years ending 31 March).

Everything here is reproducible from two SQL extracts and one cross-reference
script. Every published figure traces to a numbered block in
`sql/01_demand_capacity_report.sql`.

---

## The two questions

They look alike and they are not the same question.

| | Question | Grain | Answer |
|---|---|---|---|
| **Demand** | How much continuing care need does the Town of Cochrane generate, and how much is met locally? | one row per **person**, first-ever placement | 317 residents; **69.4% placed outside the town** |
| **Capacity** | Who occupies the beds that already exist in Cochrane? | one row per **admission** | 344 admissions; **57.3% to non-residents** |

Both are true at once, and each strengthens the other. They come from
independent measures, which is why they can corroborate each other.

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

## Repository layout

```
sql/
  01_demand_capacity_report.sql   the report tables — every published figure
  02_client_level_detail.sql      one row per episode, for validation
  03_waitlist_rated_sites.sql     the waitlist census, for recorded preference
analysis/
  04_displacement_check.py        joins 02 and 03 — the 138-of-220 finding
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
```

### Running things

```bash
# report tables (Snowflake) — 01 also emits its own integrity checks
snowsql -f sql/01_demand_capacity_report.sql

# displacement cross-reference, from the two CSV exports
python3 analysis/04_displacement_check.py placement.csv waitlist.csv

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
2. **Waitlist history before 2021-04-01**, plus exit and closure reasons. Would
   add the fourth cohort (residents who never received a placement) and turn
   the 138 floor into a count.
3. **Confirm with ALA:** the meaning of `rating = 0` in the waitlist source,
   and the DAL → Type B crosswalk in writing.
4. **An allocation question, deliberately unpublished.** 62% of Town residents
   placed *outside* Cochrane had asked for a Cochrane site, against 22% of
   those who *got* one. That is a question for the health authority about how
   allocation works, not a finding — it is not in either report.
