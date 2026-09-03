-- ============================================================================
-- EPIC / CONNECT CARE DOB AND SEX — for reviewing Strata-vs-Registry DOB conflicts only
-- Sensitivity / QA input. Never a production demographic source. If the Epic
-- PATIENT table is not present in this build the statement fails; say so and
-- skip (analysis/08 --epic-demo is optional).
-- Scope: PHNs on the Type A/B waitlist in the window (superset of the cohort).
-- ============================================================================
with scope as (
    select distinct regexp_replace(phn::string,'[^0-9]','') as phn
    from db_team_continuing_seniors_care.calgary_bi.ts_waitlist_trend_with_ratings_1671
    where census_date >= '2021-04-01' and census_date < '2026-04-01'
      and trim(care_type) in ('CAL - Long Term Care','CAL - Supportive Living Level 4 (DAL)',
                              'CAL - Supportive Living Level 4 Dementia (DAL)','EDM - LTC','EDM - DSL4 / DSL4D')
),
epic_phn as (
    select pat_id, digits as phn
    from (select pat_id, regexp_replace(identity_id::string,'[^0-9]','') as digits
          from db_source_epic_clarity.raw.identity_id where identity_type_id = '221')
    where length(digits) = 9 and digits <> '000000000'
)
select s.phn,
       min(p.birth_date::date)            as epic_dob,
       count(distinct p.birth_date::date) as n_epic_dob,
       min(z.name)                        as epic_sex,        -- ZC_SEX label; if zc_sex is absent, replace z.name with p.sex_c
       count(distinct p.pat_id)           as n_epic_patients
from scope s
join epic_phn e on e.phn = s.phn
join db_source_epic_clarity.raw.patient p on p.pat_id = e.pat_id
left join db_source_epic_clarity.raw.zc_sex z on z.sex_c = p.sex_c
where length(s.phn) = 9
group by s.phn;
