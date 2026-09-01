-- ============================================================================
-- COCHRANE CONTINUING CARE — WAITLIST CENSUS FOR COCHRANE-RATED SITES
--
-- WHAT THIS IS
-- The placement records say where people ended up. They do NOT say which sites
-- people asked for. That lives here, in the waitlist census: one row per
-- person per rated site per census date, so a person's presence on the
-- Cochrane list can be dated.
--
-- WHY IT MATTERS
-- This is the source behind the displacement finding — 138 of the 220 Town
-- residents placed outside Cochrane had formally requested a Cochrane site and
-- were on that list at or before the moment they were placed elsewhere. The
-- cross-reference is in analysis/04_displacement_check.py.
--
-- WHAT IT IS NOT
-- Not a substitute for service_provider_rating on the admission record. That
-- field was tested against this source and does not carry preference meaning;
-- see the WITHDRAWN block 5 note in 01_demand_capacity_report.sql.
--
-- LIMITS TO STATE WHENEVER THIS IS QUOTED
--   · The census begins 2021-04-01. Anyone who asked for Cochrane before that
--     and was placed early is invisible, so every count from it is a FLOOR.
--   · rating >= 1 or rating is null keeps genuine ranked preferences and rows
--     where the rank was never captured; it drops rating 0, whose meaning the
--     source system does not define. Confirm with ALA before reading rank.
--   · The site filter is on the RATED site, not the site admitted to.
-- ============================================================================
select *
from db_team_continuing_seniors_care.calgary_bi.ts_waitlist_trend_with_ratings_1671
where care_type in (
        -- Same Type A / Type B vocabulary as the placement query. Level 3 is
        -- listed so the extract can answer questions about it; the reported
        -- figures exclude it.
        'CAL - Long Term Care',
        'EDM - LTC',
        'CAL - Supportive Living Level 4 (DAL)',
        'CAL - Supportive Living Level 4 Dementia (DAL)',
        'EDM - DSL4 / DSL4D',
        'CAL - Supportive Living Level 3 (PCH)'
      )
  -- Half-open on the upper bound: BETWEEN against a timestamp cuts off at
  -- midnight and silently loses the last census day.
  and census_date >= '2021-04-01'
  and census_date <  '2026-04-01'
  and (service_provider_rated_site ilike '%cochrane%'
    or service_provider_rated_site ilike '%hawthorne%')
  and (rating >= 1 or rating is null)
;
