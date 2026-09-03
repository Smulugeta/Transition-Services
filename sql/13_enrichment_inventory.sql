-- ============================================================================
-- ENRICHMENT INVENTORY — run BEFORE sql/14 (deliverable extract) is written
-- Purpose: the final Cochrane planning deliverable needs demographics (DOB,
-- sex/gender), community of residence, origin setting and the Strata
-- PATIENT_ID linkage. None of those columns has been seen in this project
-- yet. This script inventories what exists and how complete it is, so that
-- ONE documented primary source is chosen per field before anything is
-- joined. Nothing here changes the cohort.
--
-- Run each block as a separate statement. Blocks 0 and 1 use only columns
-- already proven in sql/09. Block 5 uses the column names the describes are
-- expected to show; if a describe shows a different name, edit and re-run
-- that block only. Send every result grid.
-- ============================================================================

-- ── BLOCK 0 — SCHEMAS. Run all six; paste the column lists. ────────────────
describe table db_source_strata_health_pathways.raw.patient;
describe table db_source_strata_health_pathways.raw.admissions;
describe table db_team_continuing_seniors_care.calgary_bi.ts_waitlist_trend_with_ratings_1671;
describe table db_source_ah_provincial_registry.curated.provincial_registry;
describe table db_source_ah_vital_stats.curated.tb_vital_stats_deaths_adhoc;
describe table db_source_ah_postal_code.curated.tb_postal_code;

-- 0b — Epic demographics (sensitivity/QA only). May not exist in this build;
--      if either describe fails, say so and skip block 5c.
describe table db_source_epic_clarity.raw.patient;
describe table db_source_epic_clarity.raw.zc_sex;

-- ── BLOCK 1 — PHN <-> STRATA PATIENT_ID MULTIPLICITY ───────────────────────
-- Canonical ID is chosen only after these are explained. No MIN(patient_id).
with p as (
    select id as patient_id,
           regexp_replace(identifier1::string,'[^0-9]','') as digits
    from db_source_strata_health_pathways.raw.patient
),
v as (   -- valid PHN = exactly nine digits, not all zeros (same rule as sql/09)
    select patient_id, digits as phn from p
    where length(digits) = 9 and digits <> '000000000'
),
by_phn as (select phn, count(distinct patient_id) as n_ids from v group by phn),
by_id  as (select patient_id, count(distinct phn) as n_phns from v group by patient_id)
select '1a patient rows'                                   as metric, count(*) as n from p
union all select '1b patient rows with a valid PHN',            count(*) from v
union all select '1c patient rows with NO valid PHN',           count(*) from p where patient_id not in (select patient_id from v)
union all select '1d distinct valid PHNs',                      count(*) from by_phn
union all select '1e PHNs with >1 PATIENT_ID',                  count(*) from by_phn where n_ids > 1
union all select '1f PHNs with >2 PATIENT_ID',                  count(*) from by_phn where n_ids > 2
union all select '1g PATIENT_IDs with >1 valid PHN',            count(*) from by_id  where n_phns > 1
union all select '1h max PATIENT_IDs on one PHN',               max(n_ids) from by_phn
union all select '1i max PHNs on one PATIENT_ID',               max(n_phns) from by_id;

-- 1j — WHY a PHN has several PATIENT_IDs: does each ID carry its own
--      admissions / waitlist activity, or is one a dead duplicate?
with p as (
    select id as patient_id, regexp_replace(identifier1::string,'[^0-9]','') as phn
    from db_source_strata_health_pathways.raw.patient
),
v as (select * from p where length(phn) = 9 and phn <> '000000000'),
multi as (select phn from v group by phn having count(distinct patient_id) > 1),
act as (
    select v.phn, v.patient_id,
           (select count(*) from db_source_strata_health_pathways.raw.admissions a where a.patient_id = v.patient_id)  as n_admissions,
           (select count(*) from db_source_strata_health_pathways.raw.patient_h h where h.id = v.patient_id)          as n_patient_h_rows,
           (select min(a.admission_date) from db_source_strata_health_pathways.raw.admissions a where a.patient_id = v.patient_id) as first_adm,
           (select max(a.admission_date) from db_source_strata_health_pathways.raw.admissions a where a.patient_id = v.patient_id) as last_adm
    from v join multi m on m.phn = v.phn
)
select case when n_with_adm = 0 then 'no ID has admissions'
            when n_with_adm = 1 then 'exactly one ID has admissions (others are shells)'
            else 'MORE THAN ONE ID has admissions (true split record)' end as pattern,
       count(*) as n_phns
from (select phn, count_if(n_admissions > 0) as n_with_adm from act group by phn)
group by 1 order by 1;

-- 1k — sample of the split-record PHNs (masked) for the note
with p as (
    select id as patient_id, regexp_replace(identifier1::string,'[^0-9]','') as phn
    from db_source_strata_health_pathways.raw.patient
),
v as (select * from p where length(phn) = 9 and phn <> '000000000'),
multi as (select phn from v group by phn having count(distinct patient_id) > 1)
select '…' || right(v.phn, 4) as phn_masked, v.patient_id,
       (select count(*) from db_source_strata_health_pathways.raw.admissions a where a.patient_id = v.patient_id) as n_admissions,
       (select min(a.admission_date)::date from db_source_strata_health_pathways.raw.admissions a where a.patient_id = v.patient_id) as first_adm,
       (select max(a.admission_date)::date from db_source_strata_health_pathways.raw.admissions a where a.patient_id = v.patient_id) as last_adm
from v join multi m on m.phn = v.phn
order by v.phn, v.patient_id
limit 60;

-- ── BLOCK 2 — ORIGIN-SETTING VOCABULARY ────────────────────────────────────
-- Every distinct waitlist current_location (window, Type A/B) and every
-- admissions source_location, with counts, so the normalisation map is built
-- from the real vocabulary rather than guessed.
select 'waitlist current_location' as field, current_location as value, count(distinct phn) as people
from db_team_continuing_seniors_care.calgary_bi.ts_waitlist_trend_with_ratings_1671
where census_date >= '2021-04-01' and census_date < '2026-04-01'
  and trim(care_type) in ('CAL - Long Term Care','CAL - Supportive Living Level 4 (DAL)',
                          'CAL - Supportive Living Level 4 Dementia (DAL)','EDM - LTC','EDM - DSL4 / DSL4D')
group by 1,2
union all
select 'admissions source_location', source_location, count(distinct patient_id)
from db_source_strata_health_pathways.raw.admissions
where admission_date >= '2021-04-01' and admission_date < '2026-04-01'
  and trim(care_type) in ('CAL - Long Term Care','CAL - Supportive Living Level 4 (DAL)',
                          'CAL - Supportive Living Level 4 Dementia (DAL)','EDM - LTC','EDM - DSL4 / DSL4D')
group by 1,2
order by 1, 3 desc;

-- ── BLOCK 3 — PLACEHOLDER / DUMMY ADDRESSES ────────────────────────────────
-- Reviewer: "123 ANY STREET" and analogous TEST / SAMPLE / DUMMY values must
-- never resolve residency. Inventory them in both address sources.
select 'strata address_h' as source, upper(trim(street_address)) as street, count(*) as rows_, count(distinct id) as records
from db_source_strata_health_pathways.raw.address_h
where regexp_substr(upper(street_address),
        'ANY STREET|ANYSTREET|ANY ST($|[^A-Z])|TEST|SAMPLE|DUMMY|FAKE|UNKNOWN|NO FIXED|NFA|HOMELESS|SHELTER|EVACUEE|TRANSIENT|^N/?A$|^NONE$|^X+$|^123 ') is not null
group by 1,2
union all
select 'epic pat_addr_chng_hx', upper(trim(addr_hx_line1)), count(*), count(distinct pat_id)
from db_source_epic_clarity.raw.pat_addr_chng_hx
where regexp_substr(upper(addr_hx_line1),
        'ANY STREET|ANYSTREET|ANY ST($|[^A-Z])|TEST|SAMPLE|DUMMY|FAKE|UNKNOWN|NO FIXED|NFA|HOMELESS|SHELTER|EVACUEE|TRANSIENT|^N/?A$|^NONE$|^X+$|^123 ') is not null
group by 1,2
order by 1, 3 desc;

-- ── BLOCK 4 — REQUESTED / RATED FACILITY ───────────────────────────────────
-- 4a vocabulary of rated sites (window, Type A/B)
select service_provider_rated_site as rated_site, trim(care_type) as care_type, count(distinct phn) as people
from db_team_continuing_seniors_care.calgary_bi.ts_waitlist_trend_with_ratings_1671
where census_date >= '2021-04-01' and census_date < '2026-04-01'
  and trim(care_type) in ('CAL - Long Term Care','CAL - Supportive Living Level 4 (DAL)',
                          'CAL - Supportive Living Level 4 Dementia (DAL)','EDM - LTC','EDM - DSL4 / DSL4D')
group by 1,2 order by 3 desc;

-- 4b how many distinct sites a person rates (distribution)
select n_sites, count(*) as people
from (select phn, count(distinct service_provider_rated_site) as n_sites
      from db_team_continuing_seniors_care.calgary_bi.ts_waitlist_trend_with_ratings_1671
      where census_date >= '2021-04-01' and census_date < '2026-04-01'
        and trim(care_type) in ('CAL - Long Term Care','CAL - Supportive Living Level 4 (DAL)',
                                'CAL - Supportive Living Level 4 Dementia (DAL)','EDM - LTC','EDM - DSL4 / DSL4D')
      group by phn)
group by 1 order by 1;

-- ── BLOCK 5 — DEMOGRAPHIC COMPLETENESS (edit column names after block 0) ───
-- Scope proxy: PHNs on the Type A/B waitlist in the window (the demand
-- universe is a subset of these plus admission-only people).
-- 5a Strata patient.  EXPECTED columns: birth_date, gender (sql/05 assumed
--    birth_date; neither has been confirmed).
with scope as (
    select distinct regexp_replace(phn::string,'[^0-9]','') as phn
    from db_team_continuing_seniors_care.calgary_bi.ts_waitlist_trend_with_ratings_1671
    where census_date >= '2021-04-01' and census_date < '2026-04-01'
      and trim(care_type) in ('CAL - Long Term Care','CAL - Supportive Living Level 4 (DAL)',
                              'CAL - Supportive Living Level 4 Dementia (DAL)','EDM - LTC','EDM - DSL4 / DSL4D')
),
p as (
    select regexp_replace(identifier1::string,'[^0-9]','') as phn,
           birth_date::date as dob,                    -- EDIT if describe differs
           gender            as sex                    -- EDIT if describe differs
    from db_source_strata_health_pathways.raw.patient
)
select 'strata patient' as source,
       count(distinct s.phn)                                       as scope_people,
       count(distinct iff(p.phn is not null, s.phn, null))         as matched,
       count(distinct iff(p.dob is not null, s.phn, null))         as with_dob,
       count(distinct iff(p.sex is not null and trim(p.sex) <> '', s.phn, null)) as with_sex,
       count(distinct iff(p.dob > current_date or p.dob < '1900-01-01', s.phn, null)) as implausible_dob,
       min(p.dob) as min_dob, max(p.dob) as max_dob
from scope s left join p on p.phn = s.phn
where length(s.phn) = 9;

-- 5a2 sex/gender vocabulary in Strata patient
select gender as value, count(*) as n                              -- EDIT if describe differs
from db_source_strata_health_pathways.raw.patient group by 1 order by 2 desc;

-- 5a3 does DOB DISAGREE between duplicate patient rows for one PHN?
with p as (
    select regexp_replace(identifier1::string,'[^0-9]','') as phn, birth_date::date as dob, gender as sex   -- EDIT
    from db_source_strata_health_pathways.raw.patient
)
select count_if(n_dob > 1) as phns_with_conflicting_dob, count_if(n_sex > 1) as phns_with_conflicting_sex, count(*) as phns_with_multiple_rows
from (select phn, count(distinct dob) as n_dob, count(distinct sex) as n_sex, count(*) as n
      from p where length(phn) = 9 group by phn having count(*) > 1);

-- 5b Provincial Registry. EXPECTED: a birth-date column and a sex column
--    (names unknown; PERS_ prefix seen for PERS_REAP_END_DATE). Fill in from
--    the describe, then run.
--    select count(distinct phn), count(distinct iff(<dob col> is not null, phn, null)), count(distinct iff(<sex col> is not null, phn, null))
--    from db_source_ah_provincial_registry.curated.provincial_registry;

-- 5c Epic (only if 0b succeeded). Clarity PATIENT normally has BIRTH_DATE and
--    SEX_C (code; ZC_SEX.NAME is the label).
--    select count(*) , count(birth_date), count(sex_c) from db_source_epic_clarity.raw.patient;

-- ── BLOCK 6 — COMMUNITY NAME COLUMNS IN THE POSTAL GEOGRAPHY ───────────────
-- Which column carries the community name to publish? Show what the T4C
-- prefix looks like under each candidate.
select left(regexp_replace(postalcode,'[^A-Za-z0-9]',''),3) as fsa,
       csdname_2021, csdtype_2021, local_name, count(*) as postal_codes
from db_source_ah_postal_code.curated.tb_postal_code
where upper(left(postalcode,3)) in ('T4C','T3Z','T3R','T3L','T0L','T4B','T1W')
group by 1,2,3,4 order by 1,5 desc;
