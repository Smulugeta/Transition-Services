-- ============================================================================
-- MASTER DEMAND COHORT — A / B / C / D — STANDALONE, ONE ROW PER PERSON
--
-- Paste-and-run version of query 08. Nothing to materialise first. Returns
-- one row per person in the demand cohort; feed the CSV to
-- analysis/07_master_cohort_check.py for the report tables, the integrity
-- checks, and the reconciliation against the published A/B/C.
--
-- THE LOGIC IN ONE PARAGRAPH
-- Each person's DEMAND EVENT is the earliest of their first Type A/B waitlist
-- entry and their first Type A/B admission. Everyone has one, including the
-- people who were never placed. Residency is read from the provincial registry
-- for the three fiscal years before that event. The outcome is the first
-- Type A/B admission at or after it, anywhere in the province, on any
-- transfer. A/B/C/D fall out of residency x outcome x location. D means "no
-- Type A/B placement observed by end of follow-up", not "never got a bed".
--
-- WHY min(census_date) AND NOT THE SPELL TABLE
-- Query 05's spells matter for per-spell waits and exit diagnostics. For the
-- demand event only the FIRST day on the list matters, and that is the same
-- whether or not the person later left and returned. Using the minimum
-- directly removes a dependency and a place for the two to drift apart.
--
-- CORRECTIONS CARRIED FROM REVIEW
--   · one anchor for everyone, so A/C and D are the same population
--   · residency UNRESOLVED stays unresolved; it is never read as non-resident
--   · outcome is person-level across every admission, never a single spell
--   · left-truncation at the census start is flagged on every row
-- ============================================================================
with

-- ── STEP 0 — VOCABULARY, IDENTICAL TO QUERY 01 ─────────────────────────────
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
        -- Level 3, hospice and palliative are out of the master cohort.
),
w as (
    select '2021-04-01'::date as win_start,
           '2026-04-01'::date as win_end,          -- half-open
           '2026-03-31'::date as follow_up_end
),

-- ── STEP 1 — PHN FOR EVERY PATIENT ─────────────────────────────────────────
-- identifier1 holds the PHN dash-formatted. Strip, left-pad to 9.
pat_key as (
    select p.id as patient_id,
           case when regexp_replace(p.identifier1::string,'[^0-9]','') = '' then null
                else lpad(regexp_replace(p.identifier1::string,'[^0-9]',''),9,'0') end as phn
    from db_source_strata_health_pathways.raw.patient p
),

-- ── STEP 2 — EVERY TYPE A/B ADMISSION, ANY DATE ────────────────────────────
-- Unbounded on purpose: the first-ever admission decides "already in care
-- before the window"; the first admission after the demand event decides the
-- outcome. Both need the whole history.
adm as (
    select k.phn,
           a.admission_date::date             as admission_date,
           trim(a.admission_location)         as site,
           ct.care_stream,
           iff(s.site_name is not null, 1, 0) as in_cochrane
    from db_source_strata_health_pathways.raw.admissions a
    join pat_key k          on k.patient_id = a.patient_id
    join scope_care_type ct on ct.care_type = trim(a.care_type)
    left join coch_site s   on s.site_name  = trim(a.admission_location)
    where trim(a.source_location) <> trim(a.admission_location)  -- same-site moves are not admissions
      and k.phn is not null
),
first_ever_adm as (
    select phn, min(admission_date) as first_ab_adm_ever from adm group by phn
),

-- ── STEP 3 — FIRST TYPE A/B WAITLIST ENTRY ─────────────────────────────────
-- The first census day on which the person appears against a Type A/B care
-- type. Rated sites are irrelevant here and are collapsed away.
wl as (
    select lpad(regexp_replace(t.phn::string,'[^0-9]',''),9,'0') as phn,
           t.census_date::date                                   as census_date,
           t.current_location
    from db_team_continuing_seniors_care.calgary_bi.ts_waitlist_trend_with_ratings_1671 t
    join scope_care_type ct on ct.care_type = trim(t.care_type)
    cross join w
    where t.census_date >= w.win_start and t.census_date < w.win_end
      and t.phn is not null
),
census_start as (select min(census_date) as dt from wl),
first_list as (
    select l.phn,
           min(l.census_date)                        as first_list_entry,
           min_by(l.current_location, l.census_date) as setting_at_list_entry,
           iff(min(l.census_date) = cs.dt, 1, 0)     as left_truncated
    from wl l cross join census_start cs
    group by l.phn, cs.dt
),

-- ── STEP 4 — THE DEMAND EVENT ──────────────────────────────────────────────
-- Earliest of first list entry and first admission. Exclude anyone whose
-- first-ever admission predates the window (already in care; a later
-- admission is a transfer, not new demand — same rule as query 01).
demand as (
    select coalesce(l.phn, a.phn)                                          as phn,
           least(coalesce(l.first_list_entry,  '9999-12-31'::date),
                 coalesce(a.first_ab_adm_ever, '9999-12-31'::date))         as demand_dt,
           iff(l.first_list_entry is not null
               and (a.first_ab_adm_ever is null or l.first_list_entry <= a.first_ab_adm_ever),
               'waitlist entry', 'admission')                              as demand_event_type,
           coalesce(l.left_truncated, 0)                                    as left_truncated,
           l.setting_at_list_entry,
           a.first_ab_adm_ever
    from first_list l
    full outer join first_ever_adm a on a.phn = l.phn
    cross join w
    where a.first_ab_adm_ever is null or a.first_ab_adm_ever >= w.win_start
),
demand_in_window as (
    select d.*,
           iff(month(d.demand_dt) >= 4, year(d.demand_dt) + 1, year(d.demand_dt)) as demand_fye
    from demand d cross join w
    where d.demand_dt >= w.win_start and d.demand_dt < w.win_end
),

-- ── STEP 5 — RESIDENCY AT THE DEMAND EVENT ─────────────────────────────────
-- Three fiscal years ending the year BEFORE the event. Town = Statistics
-- Canada census subdivision. Years INSIDE the window are counted separately
-- so "could not test" is distinguishable from "tested and not Cochrane".
geo as (
    select lpad(r.phn::string,9,'0') as phn, r.fye,
           iff(upper(trim(pc.csdname_2021)) = 'COCHRANE'
               and upper(trim(pc.csdtype_2021)) = 'T', 1, 0)              as in_town,
           iff(upper(trim(pc.local_name)) = 'COCHRANE | SPRINGBANK', 1, 0) as in_area
    from db_source_ah_provincial_registry.curated.provincial_registry r
    join db_source_ah_postal_code.curated.tb_postal_code pc on pc.postalcode = r.postal_cd
),
residency as (
    select d.phn,
           max(iff(g.in_town=1 and g.fye between d.demand_fye-3 and d.demand_fye-1, 1, 0)) as town_3yr,
           max(iff(g.in_area=1 and g.fye between d.demand_fye-3 and d.demand_fye-1, 1, 0)) as area_3yr,
           count(distinct g.fye)                                                            as n_registry_fye,
           count(distinct iff(g.fye between d.demand_fye-3 and d.demand_fye-1, g.fye, null)) as n_window_fye
    from demand_in_window d
    left join geo g on g.phn = d.phn
    group by d.phn
),

-- ── STEP 6 — OUTCOME, FORWARD FROM THE DEMAND EVENT ────────────────────────
outcome as (
    select d.phn,
           min(a.admission_date)                   as first_placement_dt,
           min_by(a.in_cochrane, a.admission_date) as first_placement_in_cochrane,
           min_by(a.site,        a.admission_date) as first_placement_site,
           min_by(a.care_stream, a.admission_date) as first_placement_stream
    from demand_in_window d
    left join adm a on a.phn = d.phn and a.admission_date >= d.demand_dt
    group by d.phn
),
deaths as (
    select lpad(regexp_replace(stkh_num_1::string,'[^0-9]',''),9,'0') as phn,
           min(dethdate::date) as death_dt
    from db_source_ah_vital_stats.curated.tb_vital_stats_deaths_adhoc
    group by 1
),

-- ── STEP 7 — ONE ROW PER PERSON ────────────────────────────────────────────
master as (
    select d.phn, d.demand_dt, d.demand_fye, d.demand_event_type, d.left_truncated,
           d.setting_at_list_entry, d.first_ab_adm_ever,
           coalesce(r.town_3yr,0) as town_3yr, coalesce(r.area_3yr,0) as area_3yr,
           coalesce(r.n_registry_fye,0) as n_registry_fye, coalesce(r.n_window_fye,0) as n_window_fye,
           case when coalesce(r.town_3yr,0)=1       then 'Town of Cochrane'
                when coalesce(r.area_3yr,0)=1       then 'Cochrane catchment'
                when coalesce(r.n_registry_fye,0)=0 then 'UNRESOLVED - no registry record'
                when coalesce(r.n_window_fye,0)=0   then 'UNRESOLVED - no address in lookback window'
                else 'Not a Cochrane-area resident' end                                    as residency,
           case when coalesce(r.n_registry_fye,0)>=10 then 'HIGH'
                when coalesce(r.n_registry_fye,0)>=5  then 'MEDIUM' else 'LOW' end         as confidence,
           o.first_placement_dt, o.first_placement_in_cochrane, o.first_placement_site,
           o.first_placement_stream,
           x.death_dt,
           iff(o.first_placement_dt is not null, 1, 0)                                     as placed,
           case when o.first_placement_dt is not null then null
                when x.death_dt is not null and x.death_dt <= w.follow_up_end
                     then 'died, no placement observed'
                else 'no placement observed by end of follow-up' end                       as d_outcome,
           iff(o.first_placement_dt is not null,
               datediff('day', d.demand_dt, o.first_placement_dt), null)                   as days_to_placement,
           case when coalesce(r.town_3yr,0)=1 and o.first_placement_in_cochrane=1        then 'A'
                when coalesce(r.town_3yr,0)=0 and coalesce(r.area_3yr,0)=0
                     and coalesce(r.n_window_fye,0)>0 and o.first_placement_in_cochrane=1 then 'B'
                when coalesce(r.town_3yr,0)=1 and o.first_placement_dt is not null
                     and o.first_placement_in_cochrane=0                                  then 'C'
                when coalesce(r.town_3yr,0)=1 and o.first_placement_dt is null            then 'D'
                else null end                                                              as cohort
    from demand_in_window d
    cross join w
    left join residency r on r.phn = d.phn
    left join outcome   o on o.phn = d.phn
    left join deaths    x on x.phn = d.phn
)

-- ── OUTPUT ─────────────────────────────────────────────────────────────────
-- Everyone who bears on the Cochrane question: Cochrane-area residents, people
-- placed in Cochrane, and everyone whose residency could not be resolved (they
-- are the uncertainty around D and must stay visible). The remaining cell —
-- confirmed non-resident, not placed in Cochrane — bears on nothing and is
-- dropped to keep the extract small.
select *
from master
where residency <> 'Not a Cochrane-area resident'
   or first_placement_in_cochrane = 1
order by cohort nulls last, demand_dt
;
