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

-- ── A. ADDRESS RECORDS PER PATIENT (the decisive question) ────────────────
with pa as (
    select distinct id as patient_id, address_id
    from db_source_strata_health_pathways.raw.patient_h
    where address_id is not null
)
select count(distinct address_id) as address_records, count(*) as patients
from pa group by patient_id
qualify true
order by 1;
-- read as: how many patients have 1 record, 2 records, 3 ... If anyone has
-- more than 1, the current pointer is NOT sufficient.

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

-- ── E. FACILITY ADDRESSES — versions shared by many patients ───────────────
select upper(trim(ah.street_address)) as street, upper(replace(ah.postal_code,' ','')) as postal,
       count(distinct ph.id) as patients
from (select distinct id, address_id from db_source_strata_health_pathways.raw.patient_h) ph
join db_source_strata_health_pathways.raw.address_h ah on ah.id = ph.address_id
group by 1,2 having count(distinct ph.id) >= 3
order by 3 desc limit 60;
-- private homes appear once. Anything with 3+ is almost certainly a facility
-- (Bethany Cochrane, Hawthorne, Big Hill Lodge, hospitals ...). Query 09 rev
-- 2.5 refuses to classify residency from such an address.

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
