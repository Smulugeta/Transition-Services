-- ============================================================================
-- MASTER DEMAND COHORT — A / B / C / D FROM ONE PERSON-LEVEL BASE
--
-- THIS IS THE CONTROLLING LOGIC. Every cohort figure in the Cochrane report
-- should read from here. Queries 01 (placements) and 05/07 (waitlist) are
-- kept as the components and as reconciliation targets, not as the source of
-- published numbers.
--
-- WHY A MASTER COHORT INSTEAD OF BOLTING D ONTO A/B/C
-- The published A/B/C count people whose PLACEMENT fell inside the study
-- window. A cohort D built from the waitlist counts people whose LIST ENTRY
-- fell inside it. Those are different populations. A person who joined the
-- list in 2020 and was placed in 2022 enters A or C; an equivalent person who
-- joined in 2020 and was never placed is excluded from D. Summing the two
-- produces a denominator whose parts were selected on different events, and
-- the bias runs one way: it understates unmet demand.
--
-- THE FIX IS ONE ANCHOR FOR EVERYONE
-- Each person's DEMAND EVENT is the earliest of their first Type A/B waitlist
-- entry and their first Type A/B admission. Everyone has one — including the
-- people who were never placed, which is what made cohort D impossible under
-- the admission anchor. Residency is read at that event, and the outcome is
-- read forward from it across the whole observable pathway.
--
--   Cohort   Cochrane resident at demand event   Placed by end of follow-up   Where
--   A        yes                                 yes                          Cochrane
--   B        no                                  yes                          Cochrane
--   C        yes                                 yes                          outside
--   D        yes                                 NO PLACEMENT OBSERVED        —
--
--   Resident demand            = A + C + D
--   Use of Cochrane capacity   = A + B          (per admission, from query 01)
--
-- D IS "NO TYPE A/B PLACEMENT OBSERVED BY END OF FOLLOW-UP", NOT "NEVER GOT A
-- BED". It contains people still waiting on 2026-03-31, people who died
-- waiting, people who withdrew, and people placed outside the data we can
-- see. Those are different outcomes and the d_outcome column keeps them apart.
-- Do not collapse them into one word in prose.
--
-- LEFT-TRUNCATION IS FLAGGED, NOT HIDDEN. 1,604 people were already on the
-- list when the census opened; their demand event is artificially 2021-04-01.
-- Run every figure with and without left_truncated = 1 and report the spread.
--
-- BLOCK R AT THE BOTTOM RECONCILES AGAINST THE PUBLISHED A/B/C. It will not
-- match exactly — the anchor moved earlier for people with a waitlist record —
-- and the size and direction of the difference is itself something to report.
-- ============================================================================
with

-- ── STEP 0 — VOCABULARY, SHARED WITH QUERIES 01 AND 05 ─────────────────────
coch_site (site_name) as (
    select * from values
        ('CAL - Bethany Cochrane LTC_'), ('CAL - Hawthorne SL4_'), ('CAL - Hawthorne SL4D')
),
scope_care_type (care_type, care_stream) as (
    select * from values
        ('CAL - Long Term Care',                           'Type A'),
        ('EDM - LTC',                                      'Type A'),
        ('CAL - Supportive Living Level 4 (DAL)',          'Type B'),
        ('CAL - Supportive Living Level 4 Dementia (DAL)', 'Type B'),
        ('EDM - DSL4 / DSL4D',                             'Type B')
        -- Level 3, hospice and palliative are OUT of the master cohort. They
        -- are tagged in queries 01 and 05 so the exclusion stays visible.
),
window_bounds as (
    select '2021-04-01'::date as win_start, '2026-04-01'::date as win_end,
           '2026-03-31'::date as follow_up_end
),

-- ── STEP 1 — PHN FOR EVERY PATIENT ─────────────────────────────────────────
pat_key as (
    select p.id as patient_id,
           case when regexp_replace(p.identifier1::string,'[^0-9]','') = '' then null
                else lpad(regexp_replace(p.identifier1::string,'[^0-9]',''),9,'0') end as phn
    from db_source_strata_health_pathways.raw.patient p
),

-- ── STEP 2 — EVERY TYPE A/B ADMISSION, ANY DATE, PROVINCE-WIDE ─────────────
-- Unbounded by date on purpose: the FIRST-EVER admission decides whether a
-- person was already in care before the window, and the first admission AFTER
-- the demand event decides the outcome. Both need the whole history.
adm as (
    select k.phn, a.patient_id,
           a.admission_date::date            as admission_date,
           trim(a.admission_location)        as site,
           ct.care_stream,
           iff(s.site_name is not null, 1, 0) as in_cochrane
    from db_source_strata_health_pathways.raw.admissions a
    join pat_key k         on k.patient_id = a.patient_id
    join scope_care_type ct on ct.care_type = trim(a.care_type)
    left join coch_site s   on s.site_name  = trim(a.admission_location)
    where trim(a.source_location) <> trim(a.admission_location)   -- same-site moves are not admissions
      and k.phn is not null
),
first_ever_adm as (
    select phn, min(admission_date) as first_ab_adm_ever from adm group by phn
),

-- ── STEP 3 — FIRST TYPE A/B WAITLIST ENTRY, FROM QUERY 05 ──────────────────
first_list as (
    select phn,
           min(list_entry)                       as first_list_entry,
           max(left_truncated)                   as left_truncated,
           min_by(location_at_entry, list_entry) as setting_at_list_entry
    from <schema>.cochrane_waitlist_spells                -- output of 05
    where care_stream in ('Type A','Type B') and phn is not null
    group by phn
),

-- ── STEP 4 — THE DEMAND EVENT ──────────────────────────────────────────────
-- The earliest of first list entry and first admission. Everyone in either
-- source has one. Exclusions:
--   · first-ever admission BEFORE the window: already in care; a later
--     admission is a transfer, not new demand (same rule as query 01).
--   · demand event outside the window.
demand as (
    select coalesce(l.phn, a.phn)                                  as phn,
           least(coalesce(l.first_list_entry, '9999-12-31'::date),
                 coalesce(a.first_ab_adm_ever, '9999-12-31'::date)) as demand_dt,
           iff(l.first_list_entry is not null
               and (a.first_ab_adm_ever is null
                    or l.first_list_entry <= a.first_ab_adm_ever),
               'waitlist entry', 'admission')                      as demand_event_type,
           coalesce(l.left_truncated, 0)                            as left_truncated,
           l.setting_at_list_entry,
           a.first_ab_adm_ever
    from first_list l
    full outer join first_ever_adm a on a.phn = l.phn
    cross join window_bounds w
    where (a.first_ab_adm_ever is null or a.first_ab_adm_ever >= w.win_start)
),
demand_in_window as (
    select d.*,
           iff(month(d.demand_dt) >= 4, year(d.demand_dt) + 1, year(d.demand_dt)) as demand_fye
    from demand d
    cross join window_bounds w
    where d.demand_dt >= w.win_start and d.demand_dt < w.win_end
),

-- ── STEP 5 — RESIDENCY AT THE DEMAND EVENT ─────────────────────────────────
-- Three fiscal years ending the year before the demand event. Statistics
-- Canada census subdivision for the Town. Unresolved stays unresolved.
geo as (
    select lpad(r.phn::string,9,'0') as phn, r.fye,
           iff(upper(trim(pc.csdname_2021)) = 'COCHRANE'
               and upper(trim(pc.csdtype_2021)) = 'T', 1, 0)               as in_town,
           iff(upper(trim(pc.local_name)) = 'COCHRANE | SPRINGBANK', 1, 0)  as in_area
    from db_source_ah_provincial_registry.curated.provincial_registry r
    join db_source_ah_postal_code.curated.tb_postal_code pc on pc.postalcode = r.postal_cd
),
residency as (
    select d.phn,
           max(iff(g.in_town=1 and g.fye between d.demand_fye-3 and d.demand_fye-1,1,0)) as town_3yr,
           max(iff(g.in_area=1 and g.fye between d.demand_fye-3 and d.demand_fye-1,1,0)) as area_3yr,
           count(distinct g.fye)                                                        as n_registry_fye,
           count(distinct iff(g.fye between d.demand_fye-3 and d.demand_fye-1, g.fye, null)) as n_window_fye
    from demand_in_window d
    left join geo g on g.phn = d.phn
    group by d.phn
),

-- ── STEP 6 — OUTCOME, READ FORWARD ACROSS THE WHOLE PATHWAY ────────────────
-- The first Type A/B admission at or after the demand event, anywhere in the
-- province, on any transfer. Person-level by construction.
outcome as (
    select d.phn,
           min(a.admission_date)                    as first_placement_dt,
           min_by(a.in_cochrane, a.admission_date)  as first_placement_in_cochrane,
           min_by(a.site,        a.admission_date)  as first_placement_site,
           min_by(a.care_stream, a.admission_date)  as first_placement_stream
    from demand_in_window d
    left join adm a on a.phn = d.phn and a.admission_date >= d.demand_dt
    group by d.phn
),
deaths as (
    select lpad(stkh_num_1::string,9,'0') as phn, min(dethdate::date) as death_dt
    from db_source_ah_vital_stats.curated.tb_vital_stats_deaths_adhoc
    group by 1
),

-- ── STEP 7 — CLASSIFY ──────────────────────────────────────────────────────
master as (
    select d.phn, d.demand_dt, d.demand_fye, d.demand_event_type, d.left_truncated,
           d.setting_at_list_entry,
           case when coalesce(r.town_3yr,0)=1        then 'Town of Cochrane'
                when coalesce(r.area_3yr,0)=1        then 'Cochrane catchment'
                when coalesce(r.n_registry_fye,0)=0  then 'UNRESOLVED - no registry record'
                when coalesce(r.n_window_fye,0)=0    then 'UNRESOLVED - no address in lookback window'
                else                                      'Not a Cochrane-area resident' end as residency,
           case when coalesce(r.n_registry_fye,0)>=10 then 'HIGH'
                when coalesce(r.n_registry_fye,0)>=5  then 'MEDIUM' else 'LOW' end        as confidence,
           o.first_placement_dt, o.first_placement_in_cochrane, o.first_placement_site,
           o.first_placement_stream,
           x.death_dt,
           iff(o.first_placement_dt is not null, 1, 0)                                    as placed,
           -- D outcome. Kept separate because they are different findings.
           case when o.first_placement_dt is not null          then null
                when x.death_dt is not null
                     and x.death_dt <= w.follow_up_end          then 'died, no placement observed'
                else 'no placement observed by end of follow-up' end                      as d_outcome,
           -- days to first placement, from the demand event. Null when unplaced;
           -- NOT zero, and the person stays in the denominator.
           iff(o.first_placement_dt is not null,
               datediff('day', d.demand_dt, o.first_placement_dt), null)                  as days_to_placement,
           case when coalesce(r.town_3yr,0)=1 and o.first_placement_in_cochrane=1 then 'A'
                when coalesce(r.town_3yr,0)=0 and coalesce(r.area_3yr,0)=0
                     and o.first_placement_in_cochrane=1
                     and coalesce(r.n_window_fye,0)>0                          then 'B'
                when coalesce(r.town_3yr,0)=1 and o.first_placement_dt is not null
                     and o.first_placement_in_cochrane=0                       then 'C'
                when coalesce(r.town_3yr,0)=1 and o.first_placement_dt is null then 'D'
                else null end                                                             as cohort
    from demand_in_window d
    cross join window_bounds w
    left join residency r on r.phn = d.phn
    left join outcome   o on o.phn = d.phn
    left join deaths    x on x.phn = d.phn
)

-- ════════════════════════════════════════════════════════════════════════════
-- REPORT BLOCKS
-- ════════════════════════════════════════════════════════════════════════════
select * from (

-- M1. THE FOUR COHORTS. Town of Cochrane residents only for A/C/D.
select 'M1. Cohorts (person-level)'       as section,
       cohort                             as row_label,
       coalesce(d_outcome, 'placed')      as col_label,
       count(*)                           as n_people,
       round(100.0*count(*)/sum(count(*)) over (partition by iff(cohort in ('A','C','D'),'resident','B')),1) as pct
from master where cohort is not null group by 1,2,3

-- M2. RESIDENT DEMAND = A + C + D, with and without the left-truncated.
union all
select 'M2. Resident demand A+C+D', iff(left_truncated=1,'left-truncated (entered before window)','clean'),
       cohort, count(*), round(100.0*count(*)/sum(count(*)) over (partition by left_truncated),1)
from master where cohort in ('A','C','D') group by 1,2,3

-- M3. RESIDENCY OVER EVERYONE IN THE DEMAND COHORT. The unresolved rows are
--     the size of the uncertainty around D; they are not zero.
union all
select 'M3. Residency at demand event', residency, demand_event_type, count(*),
       round(100.0*count(*)/sum(count(*)) over (),1)
from master group by 1,2,3

-- M4. TIME TO PLACEMENT FROM THE DEMAND EVENT. Placed people only; the
--     denominator for "how many waited" is M1, never this.
union all
select 'M4. Days from demand event to first placement', cohort, first_placement_stream,
       count(*), median(days_to_placement)::number(10,1)
from master where placed=1 and cohort is not null group by 1,2,3

-- M5. D BY FISCAL YEAR OF DEMAND EVENT. Later years are more censored — a
--     person whose demand event was in FY2026 has had less time to be placed.
--     Read the trend with that in mind, or restrict to FY2022-24.
union all
select 'M5. Cohort D by demand FYE (censoring rises to the right)', demand_fye::string,
       coalesce(d_outcome,'placed'), count(*),
       round(100.0*count(*)/sum(count(*)) over (partition by demand_fye::string),1)
from master where cohort in ('A','C','D') group by 1,2,3

) order by section, row_label, col_label;


-- ════════════════════════════════════════════════════════════════════════════
-- BLOCK R — RECONCILE AGAINST THE PUBLISHED A / B / C (query 01)
-- Will not match exactly: the demand anchor sits earlier than the admission
-- anchor for anyone with a waitlist record, and residency is read at that
-- earlier date. Report the difference; do not adjust either side to close it.
-- ════════════════════════════════════════════════════════════════════════════
-- select p.cohort as published_cohort, m.cohort as master_cohort,
--        p.residency as published_residency, m.residency as master_residency,
--        count(*) as n_people
-- from <schema>.cochrane_client_level p          -- query 02, admission_seq=1, first-ever, Type A/B
-- full outer join master m on m.phn = p.phn
-- group by 1,2,3,4 order by 1,2,3,4;
