-- ============================================================================
-- DELIVERABLE PLACEMENT-EVENT EXTRACT — ONE ROW PER QUALIFYING TYPE A/B ADMISSION
-- Grain: placement activity, NOT people. A person can appear many times.
-- Scope: every reporting-scope Type A/B admission dated 2021-04-01 to
-- 2026-03-31 (inclusive of the follow-up end), Calgary + Edmonton Strata
-- instances, same qualifying rule as sql/09 adm_all/adm_rep:
--   · source_location differs from admission_location (a move, not a same-
--     site re-registration); · the one TEST site excluded; · valid 9-digit PHN.
-- No cohort logic here. analysis/08 joins each event to the person table by
-- PHN for residency, cohort and IS_FIRST_PLACEMENT, restricts the reported
-- views to (Cochrane-site events) and (events of A-D people), and reconciles
-- first placements back to the person grain.
-- Feed the CSV to analysis/08 --events.
-- ============================================================================
with coch_site (site_name) as (
    select * from values
        ('CAL - Bethany Cochrane LTC_'), ('CAL - Hawthorne SL4_'), ('CAL - Hawthorne SL4D')
),
rep_care_type (care_type, care_stream) as (
    select * from values
        ('CAL - Long Term Care',                           'Type A'),
        ('EDM - LTC',                                      'Type A'),
        ('CAL - Supportive Living Level 4 (DAL)',          'Type B'),
        ('CAL - Supportive Living Level 4 Dementia (DAL)', 'Type B'),
        ('EDM - DSL4 / DSL4D',                             'Type B')
),
w as (select '2021-04-01'::date as win_start, '2026-03-31'::date as follow_up_end),
pat_key as (
    select patient_id, iff(length(digits) = 9 and digits <> '000000000', digits, null) as phn
    from (select p.id as patient_id, regexp_replace(p.identifier1::string,'[^0-9]','') as digits
          from db_source_strata_health_pathways.raw.patient p)
)
select k.phn,
       a.patient_id,
       a.admission_notice_id,
       a.admission_date::date                         as admission_dt,
       iff(month(a.admission_date) >= 4, year(a.admission_date) + 1, year(a.admission_date)) as admission_fye,
       trim(a.admission_location)                     as placement_site,
       r.care_stream,
       iff(s.site_name is not null, 1, 0)             as placement_in_cochrane,
       trim(a.source_location)                        as source_location,
       a.discharge_date::date                         as discharge_dt,
       trim(a.discharge_destination)                  as discharge_destination,
       row_number() over (partition by k.phn order by a.admission_date, a.admission_notice_id) as event_seq_for_person
from db_source_strata_health_pathways.raw.admissions a
join pat_key k        on k.patient_id = a.patient_id
join rep_care_type r  on r.care_type  = trim(a.care_type)
left join coch_site s on s.site_name  = trim(a.admission_location)
cross join w
where k.phn is not null
  and trim(a.source_location) is distinct from trim(a.admission_location)
  and split_part(trim(a.admission_location), ' - ', 1) <> 'TEST'
  and a.admission_date::date >= w.win_start
  and a.admission_date::date <= w.follow_up_end
order by k.phn, a.admission_date;
