# Coverage and data-quality check results

Outputs of `sql/10_coverage_checks.sql`, run 2026-09-02 against the warehouse.
These decide what cohort D can and cannot mean.

## Check 1 — zone coverage of the admissions source

| Site prefix | Sites | Admissions |
|---|---|---|
| CAL | 498 | 179,880 |
| EDM | 438 | 114,779 |
| SOUTH | 2 | 82 |
| CENTRAL | 3 | 68 |
| NORTH | 2 | 54 |
| TEST | 1 | 1 |

**Verdict: the source is the Calgary and Edmonton Strata instances. It is not
province-wide.** Seven sites and 204 admissions in the other three zones,
against 936 sites and 294,659 admissions in the two covered ones — vestigial,
not coverage. A Town of Cochrane resident placed in Central, South or North
zone is not observable here and lands in D3.

"Covered" means "in the Calgary or Edmonton Strata instance", not strict AHS
zone geography: Didsbury General Hospital carries a `CAL` prefix although
Didsbury is in Central zone. The `TEST` site is excluded by query 09.

**Consequence.** D3 ("exited, no placement observed in source") is an upper
bound on unmet demand and must be quoted as such. The realistic leak is a
Calgary-zone resident placed just over the Central boundary — Olds, Sundre,
Innisfail, Red Deer. Sizing it needs a source that covers Central zone.

## Check 2 — legacy care-type codes

| Code | Admissions | First seen | Last seen |
|---|---|---|---|
| CAL - Retired - DAL | 1,759 | 2002-09-17 | 2012-03-19 |
| CAL - Retired - DEL | 47 | 2006-01-09 | 2012-07-31 |

Both end in 2012. They cannot be outcomes inside the FY2022–26 window, so they
belong in the **historical** "already in residential care" scope only. Query 09
rev 2 had `Retired - DAL` in reporting scope as well — harmless (no rows in
window) but wrong in principle; removed in rev 2.1.

Whether they are the pre-rename Type B and Level 3 codes is still an ALA
question, but it only affects the already-in-care exclusion for people whose
history predates 2012.

## Check 3 — NULL `source_location`

| Type A/B admissions | NULL source | Same-site moves |
|---|---|---|
| 150,486 | 452 (0.30%) | 453 |

The `<>` filter dropped the 452 silently. `is distinct from` keeps them.

## Check 4 — same-day multiple placements

33 person-days in the whole source with more than one distinct site on the
same day. The deterministic tiebreak (Cochrane first, then site name) and the
`n_sameday_first` column handle them visibly.

## Check 5 — approval fields

| People on a Type A/B list in window | With `assess_approved_date` | With `calculated_assess_approved_date` | Never approved |
|---|---|---|---|
| 68,730 | 66,749 (97.1%) | 67,923 (98.8%) | 1,854 (2.7%) |

`coalesce(assess_approved_date, calculated_assess_approved_date)` is safe as
the demand event. Which field is operational is still an ALA question; on the
Cochrane extract they agree 96% of the time where both exist.

The 1,854 never approved are carried with `was_approved = 0` and excluded
from A–D: they were on a list but never ready for a bed.

## Check 6 — registry postal-code mapping

| Registry rows FY2018–26 | Null postal code | Unmapped postal code |
|---|---|---|
| 40,371,597 | 1,044 | 3,346 |

Negligible (0.011% combined). The LEFT join and `residency_missing_reason`
still report them separately so the negligibility is visible rather than
assumed.

## What this settles

- **"Province-wide" is withdrawn permanently for this source.** Every D figure
  carries "in the Calgary and Edmonton Strata instances".
- The approval-date demand event is well supported.
- NULL sources, ties and postal mapping are all small and now handled
  explicitly rather than silently.

## Still open for ALA

1. Is there a source covering Central zone placements of Calgary-zone
   residents? Without it D3 cannot be separated from out-of-zone placement.
2. Are `Retired - DAL` / `Retired - DEL` the pre-rename Type B / Level 3 codes?
3. Which approval field is operational?
