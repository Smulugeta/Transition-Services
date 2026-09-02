-- ============================================================================
-- COVERAGE AND DATA-QUALITY CHECKS — RUN BEFORE ANY COHORT D FIGURE IS QUOTED
--
-- Each block answers one review question. Paste and run each separately.
-- ============================================================================

-- ── CHECK 1 — DOES THE ADMISSIONS SOURCE COVER THE WHOLE PROVINCE? ─────────
-- The distinct care_type vocabulary seen so far carries only CAL- and EDM-
-- prefixes. If Central, North and South zones are absent, a Town of Cochrane
-- resident placed in Red Deer is invisible and lands in D3 instead of C.
-- Until this is answered, no "province-wide" claim may be made.
select trim(care_type)                                as care_type,
       split_part(trim(care_type), ' - ', 1)          as zone_prefix,
       count(*)                                       as admissions,
       count(distinct patient_id)                     as people,
       min(admission_date)::date                      as first_seen,
       max(admission_date)::date                      as last_seen,
       count(distinct trim(admission_location))       as distinct_sites
from db_source_strata_health_pathways.raw.admissions
group by 1,2
order by 2,3 desc;

-- Sites by prefix. Any site that is obviously outside Calgary/Edmonton zones
-- (Red Deer, Lethbridge, Medicine Hat, Grande Prairie ...) proves coverage;
-- their absence proves the gap.
select split_part(trim(admission_location), ' - ', 1) as site_prefix,
       count(distinct trim(admission_location))       as sites,
       count(*)                                       as admissions
from db_source_strata_health_pathways.raw.admissions
group by 1 order by 3 desc;

-- ── CHECK 2 — THE LEGACY CODES ─────────────────────────────────────────────
-- "CAL - Retired - DAL" (1,759 admissions) and "CAL - Retired - DEL" (47) are
-- not in the published vocabulary. If they are the pre-rename Type B and
-- Level 3 codes they belong in scope. CONFIRM WITH ALA; meanwhile query 09
-- includes Retired-DAL in reporting scope and both in historical scope.
select trim(care_type) as care_type, count(*) as admissions,
       min(admission_date)::date as first_seen, max(admission_date)::date as last_seen
from db_source_strata_health_pathways.raw.admissions
where care_type ilike '%retired%'
group by 1;

-- ── CHECK 3 — NULL source_location ─────────────────────────────────────────
-- The same-site filter  trim(source_location) <> trim(admission_location)
-- silently drops NULL sources. Query 09 uses IS DISTINCT FROM; this shows
-- how many rows that decision affects.
select count(*)                                            as type_ab_admissions,
       count_if(source_location is null)                   as null_source,
       count_if(trim(source_location) = trim(admission_location)) as same_site_moves
from db_source_strata_health_pathways.raw.admissions
where trim(care_type) in ('CAL - Long Term Care','EDM - LTC',
      'CAL - Supportive Living Level 4 (DAL)','CAL - Supportive Living Level 4 Dementia (DAL)',
      'EDM - DSL4 / DSL4D','CAL - Retired - DAL');

-- ── CHECK 4 — SAME-DAY MULTIPLE PLACEMENTS ─────────────────────────────────
-- min_by() picks arbitrarily among ties. Query 09 breaks ties Cochrane-first
-- then by site name and reports n_sameday_first; this is the raw count.
select count(*) as person_days_with_multiple_sites
from (
    select patient_id, admission_date::date as d, count(distinct trim(admission_location)) as sites
    from db_source_strata_health_pathways.raw.admissions
    where trim(care_type) in ('CAL - Long Term Care','EDM - LTC',
          'CAL - Supportive Living Level 4 (DAL)','CAL - Supportive Living Level 4 Dementia (DAL)',
          'EDM - DSL4 / DSL4D','CAL - Retired - DAL')
    group by 1,2 having count(distinct trim(admission_location)) > 1
);

-- ── CHECK 5 — APPROVAL FIELDS ──────────────────────────────────────────────
-- assess_approved_date vs calculated_assess_approved_date: which is
-- operational? Query 09 coalesces them. On the Cochrane extract the second
-- is populated for 98% vs 93% and they agree 96% of the time where both
-- exist. ASK ALA what "calculated" means before the demand event rests on it.
select count(distinct patient_id)                                             as people,
       count(distinct iff(assess_approved_date is not null, patient_id, null)) as with_assess_approved,
       count(distinct iff(calculated_assess_approved_date is not null, patient_id, null)) as with_calculated,
       count(distinct iff(assess_approved_date is null and calculated_assess_approved_date is null,
                          patient_id, null))                                  as never_approved
from db_team_continuing_seniors_care.calgary_bi.ts_waitlist_trend_with_ratings_1671
where census_date >= '2021-04-01' and census_date < '2026-04-01';

-- ── CHECK 6 — POSTAL CODE MAPPING FAILURES ─────────────────────────────────
-- Registry rows whose postal code has no row in the lookup. These people used
-- to vanish into "no registry record". Query 09 now reports them separately.
select count(*)                                   as registry_rows,
       count_if(r.postal_cd is null)              as null_postal,
       count_if(r.postal_cd is not null and pc.postalcode is null) as unmapped_postal
from db_source_ah_provincial_registry.curated.provincial_registry r
left join db_source_ah_postal_code.curated.tb_postal_code pc on pc.postalcode = r.postal_cd
where r.fye between 2018 and 2026;
