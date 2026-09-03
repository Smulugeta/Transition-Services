-- ============================================================================
-- DELIVERABLE WAITLIST-ACTIVITY EXTRACT — ONE ROW PER WAITLIST SPELL
-- Grain: waitlist activity, NOT people. A person can have several spells.
-- Built directly from the daily census (Type A/B reporting scope, Calgary +
-- Edmonton instances) with the spell logic of sql/05: one row per person x
-- transfer record x contiguous run of census days (a gap > 1 day opens a new
-- spell). Rated-site rows are collapsed first so a person rating three sites
-- is one spell, not three. Ties in current_location on the entry day are
-- audited, not broken. analysis/08 joins STUDY_ID, residency and cohort from
-- the person table and reports unique people entering the list per fiscal
-- year. Feed the CSV to analysis/08 --waitlist.
-- ============================================================================
with rep_care_type (care_type, care_stream) as (
    select * from values
        ('CAL - Long Term Care',                           'Type A'),
        ('EDM - LTC',                                      'Type A'),
        ('CAL - Supportive Living Level 4 (DAL)',          'Type B'),
        ('CAL - Supportive Living Level 4 Dementia (DAL)', 'Type B'),
        ('EDM - DSL4 / DSL4D',                             'Type B')
),
w as (select '2021-04-01'::date as win_start, '2026-04-01'::date as win_end),
wl as (
    select t.patient_id, t.patient_transfer_id,
           regexp_replace(t.phn::string,'[^0-9]','') as phn,
           trim(t.care_type) as care_type, r.care_stream,
           t.current_location,
           coalesce(t.assess_approved_date, t.calculated_assess_approved_date)::date as approved_dt,
           t.census_date::date as census_date,
           iff(t.service_provider_rated_site ilike '%cochrane%' or t.service_provider_rated_site ilike '%hawthorne%', 1, 0) as rated_cochrane
    from db_team_continuing_seniors_care.calgary_bi.ts_waitlist_trend_with_ratings_1671 t
    join rep_care_type r on r.care_type = trim(t.care_type)
    cross join w
    where t.census_date >= w.win_start and t.census_date < w.win_end and t.phn is not null
),
daily as (   -- one row per person-transfer-day-location (rated sites collapsed)
    select patient_id, patient_transfer_id, phn, care_type, care_stream, current_location, census_date,
           min(approved_dt) as approved_dt, max(rated_cochrane) as rated_cochrane
    from wl where length(phn) = 9 and phn <> '000000000'
    group by 1,2,3,4,5,6,7
),
day1 as (    -- one row per person-transfer-day (locations audited below)
    select patient_id, patient_transfer_id, phn, min(care_type) as care_type, min(care_stream) as care_stream, census_date,
           min(approved_dt) as approved_dt, max(rated_cochrane) as rated_cochrane,
           count(distinct current_location) as n_locations,
           listagg(distinct current_location, ' | ') within group (order by current_location) as location_list,
           iff(count(distinct current_location) = 1, min(current_location), null) as location
    from daily group by 1,2,3,6
),
flagged as (
    select d.*,
           iff(datediff('day', lag(census_date) over (partition by patient_id, patient_transfer_id order by census_date), census_date) > 1, 1, 0) as spell_start
    from day1 d
),
numbered as (
    select f.*, sum(spell_start) over (partition by patient_id, patient_transfer_id order by census_date rows between unbounded preceding and current row) as spell_no
    from flagged f
),
census_bounds as (select min(census_date) as first_dt, max(census_date) as last_dt from wl)
select n.phn, n.patient_id, n.patient_transfer_id, n.spell_no,
       min(n.census_date)                                        as list_entry_dt,
       iff(month(min(n.census_date)) >= 4, year(min(n.census_date)) + 1, year(min(n.census_date))) as list_entry_fye,
       max(n.census_date)                                        as list_last_seen_dt,
       count(distinct n.census_date)                             as days_observed,
       min(n.care_type)                                          as care_type_at_entry,
       min(n.care_stream)                                        as care_stream_at_entry,
       min_by(n.location, n.census_date)                         as location_at_entry,        -- null when the entry day is tied
       min_by(n.n_locations, n.census_date)                      as n_locations_at_entry,
       min_by(n.location_list, n.census_date)                    as location_list_at_entry,
       max_by(n.location, n.census_date)                         as location_at_last_seen,
       min(n.approved_dt)                                        as first_approved_dt_in_spell,
       max(n.rated_cochrane)                                     as rated_cochrane_in_spell,
       iff(min(n.census_date) = cb.first_dt, 1, 0)               as left_truncated,
       iff(max(n.census_date) = cb.last_dt, 1, 0)                as on_list_at_followup,
       row_number() over (partition by n.phn order by min(n.census_date), n.patient_transfer_id, n.spell_no) as spell_seq_for_person
from numbered n cross join census_bounds cb
group by n.phn, n.patient_id, n.patient_transfer_id, n.spell_no, cb.first_dt, cb.last_dt
order by n.phn, list_entry_dt;
