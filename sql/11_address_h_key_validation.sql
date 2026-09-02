-- ============================================================================
-- STRATA address_h — KEY VALIDATION. RUN BEFORE TRUSTING IT AS A RESIDENCY SOURCE
--
-- WHAT IS ALREADY KNOWN (from a 9-row sample and the query that produced it)
--   · The working join is  patient_h ph JOIN address_h ah ON ph.address_id = ah.id
--     address_h.id is the ADDRESS RECORD; its rows are date-ranged VERSIONS of
--     that record (effective_from_date / effective_to_date). One record held
--     "509 32 Quigley Dr" 2023-05-19 -> 2025-12-08 and "1000-32 Quigley Dr"
--     2025-12-08 -> open. So it is a history, reachable from the pointer.
--   · patient_h is itself versioned (one row per service_provider_id): the
--     sample carried every address version FOUR times. patient_h must be
--     reduced to DISTINCT (id, address_id) before the join.
--   · 32 Quigley Dr is the Bethany Cochrane campus. Facility addresses live
--     in this table as residences. That is the contamination the registry
--     method exists to avoid, and rule 3 (effective at demand) only partly
--     protects against it.
--   · The first version's effective_from_date equalled patient_h.creation_date
--     (creation_date is a patient_h column, not address_h), i.e. the date the
--     patient record was created, not necessarily a move-in date.
--
-- WHAT THESE QUERIES DECIDE
--   A. Does a person ever have MORE THAN ONE address_id in patient_h? If yes,
--      a move creates a new record and the current pointer (patient.address_id)
--      would miss history; every (id, address_id) pair must be used. If no,
--      moves are new versions of one record and either join is complete.
--   B. Are there address_h records no patient_h row points to (orphans)?
--   C. Fan-out and dedup checks.
--   D. The reviewer's example, PHN 49833-8261.
--   E. How many address versions are shared by many patients (facilities).
--   F. How often effective_from_date is just the creation date.
-- ============================================================================

-- ── 0. SCHEMA ──────────────────────────────────────────────────────────────
describe table db_source_strata_health_pathways.raw.address_h;
describe table db_source_strata_health_pathways.raw.patient_h;
describe table db_source_strata_health_pathways.raw.patient;

-- ── A. ADDRESS RECORDS PER PATIENT, AND ADDRESSES ACTIVE ON THE DEMAND DATE ─
-- A1. records per patient (does a move create a new record?)
with pa as (
    select distinct id as patient_id, address_id
    from db_source_strata_health_pathways.raw.patient_h
    where address_id is not null
)
select address_records, count(*) as patients
from (select patient_id, count(distinct address_id) as address_records from pa group by patient_id)
group by 1 order by 1;
-- If anyone has more than 1, the current pointer is NOT sufficient and the
-- patient_h join (every pair) is required.

-- A2. THE QUESTION THAT MATTERS: how many people have MORE THAN ONE address
--     version ACTIVE ON their demand date, and do the competing versions
--     disagree on Town / catchment / non-Town? Query 09 rev 2.6 answers this
--     exactly for the cohort (strata_n_active_at_demand,
--     strata_active_classes_disagree). This standalone version approximates
--     the demand date as the person's first approval date on a Type A/B list.
with k as (
    select id as patient_id, regexp_replace(identifier1::string,'[^0-9]','') as phn
    from db_source_strata_health_pathways.raw.patient
    qualify length(phn) = 9 and phn <> '000000000'
),
dem as (
    select regexp_replace(phn::string,'[^0-9]','') as phn,
           min(coalesce(assess_approved_date, calculated_assess_approved_date))::date as demand_dt
    from db_team_continuing_seniors_care.calgary_bi.ts_waitlist_trend_with_ratings_1671
    where census_date >= '2021-04-01' and census_date < '2026-04-01'
      and trim(care_type) in ('CAL - Long Term Care','EDM - LTC','CAL - Supportive Living Level 4 (DAL)',
                              'CAL - Supportive Living Level 4 Dementia (DAL)','EDM - DSL4 / DSL4D')
    group by 1 having demand_dt is not null
),
act as (
    select d.phn, ah.id as address_record, ah.postal_code, ah.street_address,
           case when pc.postalcode is not null and upper(trim(pc.csdname_2021))='COCHRANE'
                     and upper(trim(pc.csdtype_2021))='T' then 'Town'
                when pc.postalcode is not null and upper(trim(pc.local_name))='COCHRANE | SPRINGBANK' then 'catchment'
                when pc.postalcode is not null then 'not Cochrane'
                when left(upper(regexp_replace(ah.postal_code,'[^A-Za-z0-9]','')),1) <> 'T' then 'not Cochrane'
                else 'unresolved' end as cls
    from dem d
    join k on k.phn = d.phn
    join (select distinct id, address_id from db_source_strata_health_pathways.raw.patient_h) ph on ph.id = k.patient_id
    join (select distinct id, postal_code, street_address, effective_from_date, effective_to_date
          from db_source_strata_health_pathways.raw.address_h) ah on ah.id = ph.address_id
    left join db_source_ah_postal_code.curated.tb_postal_code pc
           on upper(regexp_replace(pc.postalcode,'[^A-Za-z0-9]','')) = upper(regexp_replace(ah.postal_code,'[^A-Za-z0-9]',''))
    where ah.effective_from_date::date <= d.demand_dt
      and (ah.effective_to_date::date > d.demand_dt or ah.effective_to_date is null)
)
select n_active, classes_disagree, count(*) as people
from (select phn, count(*) as n_active, iff(count(distinct cls) > 1, 1, 0) as classes_disagree from act group by phn)
group by 1,2 order by 1,2;
-- rows with n_active > 1 AND classes_disagree = 1 are the only cases where
-- the latest-effective_from tiebreak can change a residency verdict.

-- does patient.address_id (current) differ from any patient_h address_id?
select count(*)                                            as patients_with_history,
       count_if(p.address_id is null)                      as current_pointer_null,
       count_if(p.address_id <> ph.address_id)             as history_record_not_current
from (select distinct id, address_id from db_source_strata_health_pathways.raw.patient_h) ph
left join db_source_strata_health_pathways.raw.patient p on p.id = ph.id;

-- ── B. ORPHANS ─────────────────────────────────────────────────────────────
select count(distinct ah.id) as address_records_with_no_patient
from db_source_strata_health_pathways.raw.address_h ah
left join (select distinct address_id from db_source_strata_health_pathways.raw.patient_h) ph
       on ph.address_id = ah.id
where ph.address_id is null;

-- ── C. VERSIONS AND FAN-OUT ────────────────────────────────────────────────
-- versions per address record
select versions, count(*) as address_records from (
    select id, count(*) as versions
    from (select distinct id, effective_from_date, effective_to_date, postal_code, street_address
          from db_source_strata_health_pathways.raw.address_h)
    group by id
) group by 1 order by 1;

-- overlapping versions of one record (should be 0: at most one version active on any day)
select count(*) as overlapping_version_pairs
from (select distinct id, effective_from_date f1, effective_to_date t1 from db_source_strata_health_pathways.raw.address_h) a
join (select distinct id, effective_from_date f2, effective_to_date t2 from db_source_strata_health_pathways.raw.address_h) b
  on a.id = b.id and a.f1 < b.f2
 and coalesce(a.t1, '9999-12-31'::date) > b.f2;

-- ── D. THE REVIEWER'S EXAMPLE — PHN 49833-8261 ─────────────────────────────
with k as (
    select id as patient_id
    from db_source_strata_health_pathways.raw.patient
    where lpad(regexp_replace(identifier1::string,'[^0-9]',''),9,'0') = '498338261'
)
select ph.id as patient_id, ph.address_id, ah.street_address, ah.city_name, ah.postal_code,
       ah.effective_from_date, ah.effective_to_date, ph.created as patient_record_created
from k
join (select id, address_id, min(creation_date) as created
      from db_source_strata_health_pathways.raw.patient_h group by 1,2) ph on ph.id = k.patient_id
join db_source_strata_health_pathways.raw.address_h ah on ah.id = ph.address_id
order by ah.effective_from_date;
-- expected: a Surrey BC row, V3Z 9T1, effective from 2021-05-18, active on the
-- 2021-06-01 demand date. If it is missing, the join is wrong.

-- ── E. FACILITY CANDIDATES — CONCURRENT occupancy, not ever-shared ─────────
-- "Ever shared by 3+" over decades of history flags apartment units with three
-- successive tenants. A facility has many DIFFERENT people holding the same
-- address ON THE SAME DAY. This lists addresses by their peak concurrent
-- occupancy so a facility reference table can be built and confirmed by
-- ALA, which is preferable to any numeric threshold.
with v as (
    select distinct ph.id as patient_id, upper(trim(ah.street_address)) as street,
           upper(regexp_replace(ah.postal_code,'[^A-Za-z0-9]','')) as postal,
           ah.effective_from_date::date as f, coalesce(ah.effective_to_date::date, current_date()) as t
    from (select distinct id, address_id from db_source_strata_health_pathways.raw.patient_h) ph
    join db_source_strata_health_pathways.raw.address_h ah on ah.id = ph.address_id
    where ah.street_address is not null
),
-- sample the calendar quarterly and count distinct occupants per address per sample date
cal as (select dateadd('quarter', seq4(), '2015-01-01'::date) as d from table(generator(rowcount => 48))),
occ as (
    select v.street, v.postal, c.d, count(distinct v.patient_id) as occupants
    from v join cal c on c.d between v.f and v.t
    group by 1,2,3
)
select street, postal, max(occupants) as peak_concurrent_occupants,
       (select count(distinct patient_id) from v v2 where v2.street = occ.street and v2.postal = occ.postal) as ever_shared_by
from occ
group by 1,2 having max(occupants) >= 3
order by 3 desc limit 100;
-- Expect Bethany Cochrane, Hawthorne, Big Hill Lodge, hospitals, lodges and
-- large seniors' residences at the top; apartment units should NOT appear.

-- ── G. RAW PHN DIGIT LENGTHS BEFORE ANY PADDING (gate 5) ───────────────────
-- Snowflake LPAD(x, 9) TRUNCATES a string longer than 9. A 10-digit identifier
-- padded "to 9" silently became its first nine digits. Count first.
select 'patient.identifier1' as source,
       case when d = 0 then '0 digits' when d between 1 and 8 then '1-8 digits'
            when d = 9 then '9 digits' else '>9 digits' end as digit_class,
       count(*) as rows_, count_if(digits = '000000000') as all_zero
from (select regexp_replace(identifier1::string,'[^0-9]','') as digits, length(regexp_replace(identifier1::string,'[^0-9]','')) as d
      from db_source_strata_health_pathways.raw.patient)
group by 1,2
union all
select 'waitlist.phn (distinct people)',
       case when d = 0 then '0 digits' when d between 1 and 8 then '1-8 digits'
            when d = 9 then '9 digits' else '>9 digits' end,
       count(*), count_if(digits = '000000000')
from (select distinct regexp_replace(phn::string,'[^0-9]','') as digits, length(regexp_replace(phn::string,'[^0-9]','')) as d
      from db_team_continuing_seniors_care.calgary_bi.ts_waitlist_trend_with_ratings_1671
      where census_date >= '2021-04-01' and census_date < '2026-04-01')
group by 1,2
union all
select 'vital_stats.stkh_num_1',
       case when d = 0 then '0 digits' when d between 1 and 8 then '1-8 digits'
            when d = 9 then '9 digits' else '>9 digits' end,
       count(*), count_if(digits = '000000000')
from (select regexp_replace(stkh_num_1::string,'[^0-9]','') as digits, length(regexp_replace(stkh_num_1::string,'[^0-9]','')) as d
      from db_source_ah_vital_stats.curated.tb_vital_stats_deaths_adhoc)
group by 1,2
order by 1,2;

-- ── F. IS effective_from_date A MOVE-IN DATE OR A RECORD-CREATION DATE? ────
-- creation_date is on patient_h. Compare each address record's FIRST version
-- start against the earliest creation of the patient/address pairing.
select count(*)                                          as first_versions,
       count_if(first_from = created)                    as from_equals_patient_creation,
       round(100.0*count_if(first_from = created)/count(*),1) as pct
from (
    select ah.id, min(ah.effective_from_date)::date as first_from, min(ph.creation_date)::date as created
    from (select distinct id, effective_from_date from db_source_strata_health_pathways.raw.address_h) ah
    join db_source_strata_health_pathways.raw.patient_h ph on ph.address_id = ah.id
    group by ah.id
);
-- a high share means the first address's start date is when the record was
-- created in Strata, not when the person moved there. Rule 3 still works for
-- "active at demand" but the address may have been current for longer.
