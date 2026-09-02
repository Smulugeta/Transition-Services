-- ============================================================================
-- MASTER DEMAND COHORT — A / B / C / D — STANDALONE, ONE ROW PER PERSON
-- Revision 2, after second review. Paste-and-run. Feed the CSV to
-- analysis/07_master_cohort_check.py.
--
-- WHAT CHANGED AND WHY (each item is a review finding)
--   1. Outcome capped at follow_up_end. A placement after 2026-03-31 cannot
--      make someone A or C; it is carried as first_placement_after_followup
--      for sensitivity only.
--   2. Demand event is the APPROVAL date, not first census appearance. 8.2%
--      of people who appear on the list are never approved; they were never
--      waiting for a bed and are not unmet demand. first_list_appearance is
--      kept for sensitivity. coalesce(assess_approved_date,
--      calculated_assess_approved_date): the second is populated for 98% vs
--      93%, and where both exist they agree 96% of the time. ASK ALA which is
--      operational.
--   3. D is split. D1 = on the census on the last day (actively waiting).
--      D2 = died before any placement. D3 = exited, no placement observed,
--      outcome unknown. These are different findings.
--   4. Two vocabularies. HISTORICAL residential scope (Type A, B, Level 3,
--      and the legacy "Retired - DAL/DEL" codes) decides "already in care
--      before the window", exactly as query 01 did. REPORTING scope (Type A,
--      B) decides the outcome. Using the reporting filter for history let a
--      Level 3 -> Type A transfer look like new demand.
--   5. "Province-wide" is WITHDRAWN. The admissions source's entire care_type
--      vocabulary is CAL- and EDM-prefixed; there are no Central, North or
--      South labels. A Town of Cochrane resident placed in Red Deer may be
--      invisible here and would wrongly land in D3. Run 10_coverage_checks
--      and confirm the source's zone coverage with ALA before any D figure is
--      quoted. Until then the outcome is "no placement observed IN THIS
--      SOURCE".
--   6. Two residency methods carried side by side. residency_any3 is the
--      published rule (any Town address in the three prior fiscal years).
--      residency_latest reads the MOST RECENT pre-demand address in that
--      window. The checker reports every person who moves between them. The
--      published rule is not changed here; the effect is measured.
--   7. Registry missingness split four ways: no registry record; record but
--      null postal code; postal code that fails the lookup; mapped but no
--      year inside the lookback. The postal-code join is now LEFT so an
--      unmapped code no longer deletes the person.
--  10. NULL source_location kept (is distinct from). Same-day ties broken
--      deterministically and counted.
-- ============================================================================
with

-- ── STEP 0 — TWO VOCABULARIES ──────────────────────────────────────────────
coch_site (site_name) as (
    select * from values
        ('CAL - Bethany Cochrane LTC_'), ('CAL - Hawthorne SL4_'), ('CAL - Hawthorne SL4D')
),
-- HISTORICAL residential scope: anything that means the person was already
-- living in a residential continuing-care setting. Decides "already in care".
hist_care_type (care_type, care_stream) as (
    select * from values
        ('CAL - Long Term Care',                           'Type A'),
        ('EDM - LTC',                                      'Type A'),
        ('CAL - Supportive Living Level 4 (DAL)',          'Type B'),
        ('CAL - Supportive Living Level 4 Dementia (DAL)', 'Type B'),
        ('EDM - DSL4 / DSL4D',                             'Type B'),
        ('CAL - Retired - DAL',                            'Type B (legacy code)'),   -- CONFIRM with ALA
        ('CAL - Supportive Living Level 3 (PCH)',          'Type B - Level 3'),
        ('CAL - Supportive Living Level 3 (DEL)',          'Type B - Level 3'),
        ('CAL - Retired - DEL',                            'Type B - Level 3 (legacy)'), -- CONFIRM with ALA
        ('EDM - DSL3',                                     'Type B - Level 3')
),
-- REPORTING scope: what counts as a Type A/B placement outcome.
rep_care_type (care_type, care_stream) as (
    select * from values
        ('CAL - Long Term Care',                           'Type A'),
        ('EDM - LTC',                                      'Type A'),
        ('CAL - Supportive Living Level 4 (DAL)',          'Type B'),
        ('CAL - Supportive Living Level 4 Dementia (DAL)', 'Type B'),
        ('EDM - DSL4 / DSL4D',                             'Type B'),
        ('CAL - Retired - DAL',                            'Type B (legacy code)')    -- CONFIRM with ALA
),
w as (
    select '2021-04-01'::date as win_start,
           '2026-04-01'::date as win_end,           -- half-open
           '2026-03-31'::date as follow_up_end
),

-- ── STEP 1 — PHN ───────────────────────────────────────────────────────────
pat_key as (
    select p.id as patient_id,
           case when regexp_replace(p.identifier1::string,'[^0-9]','') = '' then null
                else lpad(regexp_replace(p.identifier1::string,'[^0-9]',''),9,'0') end as phn
    from db_source_strata_health_pathways.raw.patient p
),

-- ── STEP 2 — ADMISSIONS, ANY DATE ──────────────────────────────────────────
-- is distinct from: a NULL source_location is a real admission with a missing
-- field, not a same-site move. <> would drop it silently.
adm_all as (
    select k.phn,
           a.admission_date::date             as admission_date,
           trim(a.admission_location)         as site,
           trim(a.care_type)                  as care_type,
           iff(s.site_name is not null, 1, 0) as in_cochrane,
           iff(a.source_location is null, 1, 0) as null_source
    from db_source_strata_health_pathways.raw.admissions a
    join pat_key k        on k.patient_id = a.patient_id
    left join coch_site s on s.site_name  = trim(a.admission_location)
    where trim(a.source_location) is distinct from trim(a.admission_location)
      and k.phn is not null
),
first_ever_residential as (           -- HISTORICAL scope
    select a.phn, min(a.admission_date) as first_residential_ever,
           min_by(h.care_stream, a.admission_date) as first_residential_stream
    from adm_all a join hist_care_type h on h.care_type = a.care_type
    group by a.phn
),
adm_rep as (                          -- REPORTING scope
    select a.*, r.care_stream
    from adm_all a join rep_care_type r on r.care_type = a.care_type
),

-- ── STEP 3 — WAITLIST: APPROVAL DATE, FIRST APPEARANCE, LAST DAY ON LIST ───
wl as (
    select lpad(regexp_replace(t.phn::string,'[^0-9]',''),9,'0') as phn,
           t.census_date::date                                   as census_date,
           coalesce(t.assess_approved_date,
                    t.calculated_assess_approved_date)::date     as approved_dt,
           t.current_location
    from db_team_continuing_seniors_care.calgary_bi.ts_waitlist_trend_with_ratings_1671 t
    join rep_care_type r on r.care_type = trim(t.care_type)
    cross join w
    where t.census_date >= w.win_start and t.census_date < w.win_end
      and t.phn is not null
),
census_bounds as (select min(census_date) as first_dt, max(census_date) as last_dt from wl),
first_list as (
    select l.phn,
           min(l.census_date)                          as first_list_appearance,
           min(l.approved_dt)                          as first_approval_dt,
           min_by(l.current_location, l.census_date)   as setting_at_list_entry,
           max(l.census_date)                          as last_seen_on_list,
           iff(max(l.census_date) = cb.last_dt, 1, 0)  as on_list_at_followup,   -- D1
           iff(min(l.census_date) = cb.first_dt, 1, 0) as left_truncated
    from wl l cross join census_bounds cb
    group by l.phn, cb.last_dt, cb.first_dt
),

-- ── STEP 4 — THE DEMAND EVENT = APPROVAL, OR ADMISSION IF NEVER APPROVED ───
-- A person on the list but never approved was never ready for a bed. They
-- are carried (was_approved = 0) and excluded from A/B/C/D.
-- "Already in care" uses the HISTORICAL scope.
demand as (
    select coalesce(l.phn, a.phn)                                          as phn,
           least(coalesce(l.first_approval_dt, '9999-12-31'::date),
                 coalesce(a.first_rep_adm,     '9999-12-31'::date))         as demand_dt,
           iff(l.first_approval_dt is not null
               and (a.first_rep_adm is null or l.first_approval_dt <= a.first_rep_adm),
               'approval', 'admission')                                    as demand_event_type,
           iff(l.first_approval_dt is not null or a.first_rep_adm is not null, 1, 0) as was_approved,
           l.first_list_appearance, l.first_approval_dt, l.setting_at_list_entry,
           l.last_seen_on_list, coalesce(l.on_list_at_followup,0) as on_list_at_followup,
           coalesce(l.left_truncated, 0)                                    as left_truncated,
           h.first_residential_ever, h.first_residential_stream
    from first_list l
    full outer join (select phn, min(admission_date) as first_rep_adm from adm_rep group by phn) a
           on a.phn = l.phn
    left join first_ever_residential h on h.phn = coalesce(l.phn, a.phn)
    cross join w
    where h.first_residential_ever is null or h.first_residential_ever >= w.win_start
),
demand_in_window as (
    select d.*,
           iff(month(d.demand_dt) >= 4, year(d.demand_dt) + 1, year(d.demand_dt)) as demand_fye
    from demand d cross join w
    where d.demand_dt >= w.win_start and d.demand_dt < w.win_end
),

-- ── STEP 5 — RESIDENCY, TWO METHODS, MISSINGNESS SPLIT ─────────────────────
-- LEFT join to the postal lookup: an unmapped code keeps the person and is
-- reported as such, instead of deleting them into "no registry record".
geo as (
    select lpad(r.phn::string,9,'0')                                   as phn,
           r.fye,
           r.postal_cd,
           iff(pc.postalcode is null, 0, 1)                            as mapped,
           iff(upper(trim(pc.csdname_2021)) = 'COCHRANE'
               and upper(trim(pc.csdtype_2021)) = 'T', 1, 0)           as in_town,
           iff(upper(trim(pc.local_name)) = 'COCHRANE | SPRINGBANK', 1, 0) as in_area
    from db_source_ah_provincial_registry.curated.provincial_registry r
    left join db_source_ah_postal_code.curated.tb_postal_code pc on pc.postalcode = r.postal_cd
),
res_rows as (
    select d.phn, d.demand_fye, g.fye, g.postal_cd, g.mapped, g.in_town, g.in_area,
           iff(g.fye between d.demand_fye-3 and d.demand_fye-1, 1, 0) as in_window
    from demand_in_window d
    left join geo g on g.phn = d.phn
),
residency as (
    select phn,
           count(fye)                                                   as n_registry_fye,
           count_if(in_window=1)                                        as n_window_fye,
           count_if(in_window=1 and postal_cd is not null)              as n_window_with_postal,
           count_if(in_window=1 and mapped=1)                           as n_window_mapped,
           -- METHOD A (published): any Town address in the window
           max(iff(in_window=1 and in_town=1, 1, 0))                    as town_any3,
           max(iff(in_window=1 and in_area=1, 1, 0))                    as area_any3,
           -- METHOD B: the most recent mapped address in the window
           max_by(in_town, iff(in_window=1 and mapped=1, fye, null))    as town_latest,
           max_by(in_area, iff(in_window=1 and mapped=1, fye, null))    as area_latest,
           max(iff(in_window=1 and mapped=1, fye, null))                as latest_window_fye
    from res_rows
    group by phn
),

-- ── STEP 6 — OUTCOME, CAPPED AT FOLLOW-UP ──────────────────────────────────
-- Deterministic tiebreak on same-day placements: Cochrane first, then site
-- name. Ties are counted so the choice is visible.
outcome as (
    select d.phn,
           min(iff(a.admission_date <= w.follow_up_end, a.admission_date, null))   as first_placement_dt,
           min(iff(a.admission_date >  w.follow_up_end, a.admission_date, null))   as first_placement_after_followup,
           count_if(a.admission_date <= w.follow_up_end
                    and a.admission_date = (select min(b.admission_date) from adm_rep b
                                            where b.phn = d.phn and b.admission_date >= d.demand_dt
                                              and b.admission_date <= w.follow_up_end)) as n_sameday_first
    from demand_in_window d
    cross join w
    left join adm_rep a on a.phn = d.phn and a.admission_date >= d.demand_dt
    group by d.phn
),
first_site as (
    select o.phn, a.in_cochrane as first_placement_in_cochrane, a.site as first_placement_site,
           a.care_stream as first_placement_stream
    from outcome o
    join adm_rep a on a.phn = o.phn and a.admission_date = o.first_placement_dt
    qualify row_number() over (partition by o.phn order by a.in_cochrane desc, a.site) = 1
),
-- Level 3 placement after the demand event, for sensitivity: they got a bed,
-- not the Type A/B bed they were approved for.
level3_after as (
    select a.phn, min(a.admission_date) as first_level3_dt
    from adm_all a join hist_care_type h on h.care_type = a.care_type
    join demand_in_window d on d.phn = a.phn
    cross join w
    where h.care_stream like 'Type B - Level 3%' and a.admission_date >= d.demand_dt
      and a.admission_date <= w.follow_up_end
    group by a.phn
),
deaths as (
    select lpad(regexp_replace(stkh_num_1::string,'[^0-9]',''),9,'0') as phn, min(dethdate::date) as death_dt
    from db_source_ah_vital_stats.curated.tb_vital_stats_deaths_adhoc group by 1
),

-- ── STEP 7 — ONE ROW PER PERSON ────────────────────────────────────────────
master as (
    select d.phn, d.demand_dt, d.demand_fye, d.demand_event_type, d.was_approved,
           d.first_list_appearance, d.first_approval_dt, d.setting_at_list_entry,
           d.last_seen_on_list, d.on_list_at_followup, d.left_truncated,
           d.first_residential_ever, d.first_residential_stream,
           coalesce(r.n_registry_fye,0) as n_registry_fye, coalesce(r.n_window_fye,0) as n_window_fye,
           coalesce(r.n_window_mapped,0) as n_window_mapped, r.latest_window_fye,
           -- residency missingness, four classes, before any verdict
           case when coalesce(r.n_registry_fye,0) = 0       then 'no registry record'
                when coalesce(r.n_window_fye,0)   = 0       then 'registry record, no year in lookback'
                when coalesce(r.n_window_with_postal,0) = 0 then 'lookback years, postal code null'
                when coalesce(r.n_window_mapped,0) = 0      then 'postal code present, lookup failed'
                else 'resolved' end                                                  as residency_missing_reason,
           -- METHOD A — published rule
           case when coalesce(r.n_window_mapped,0) = 0 then 'UNRESOLVED'
                when r.town_any3 = 1                    then 'Town of Cochrane'
                when r.area_any3 = 1                    then 'Cochrane catchment'
                else 'Not a Cochrane-area resident' end                              as residency_any3,
           -- METHOD B — most recent address in the lookback
           case when coalesce(r.n_window_mapped,0) = 0 then 'UNRESOLVED'
                when r.town_latest = 1                  then 'Town of Cochrane'
                when r.area_latest = 1                  then 'Cochrane catchment'
                else 'Not a Cochrane-area resident' end                              as residency_latest,
           case when coalesce(r.n_registry_fye,0)>=10 then 'HIGH'
                when coalesce(r.n_registry_fye,0)>=5  then 'MEDIUM' else 'LOW' end   as confidence,
           o.first_placement_dt, o.first_placement_after_followup, o.n_sameday_first,
           fs.first_placement_in_cochrane, fs.first_placement_site, fs.first_placement_stream,
           l3.first_level3_dt,
           x.death_dt,
           iff(o.first_placement_dt is not null, 1, 0)                                as placed,
           iff(o.first_placement_dt is not null,
               datediff('day', d.demand_dt, o.first_placement_dt), null)              as days_to_placement,
           -- D CLASSES. Only meaningful when placed = 0 and was_approved = 1.
           case when o.first_placement_dt is not null                 then null
                when d.on_list_at_followup = 1                        then 'D1 still waiting at follow-up'
                when x.death_dt is not null
                     and x.death_dt <= w.follow_up_end                then 'D2 died before placement'
                else 'D3 exited, no placement observed in source' end                 as d_class
    from demand_in_window d
    cross join w
    left join residency  r  on r.phn  = d.phn
    left join outcome    o  on o.phn  = d.phn
    left join first_site fs on fs.phn = d.phn
    left join level3_after l3 on l3.phn = d.phn
    left join deaths     x  on x.phn  = d.phn
),
classified as (
    select m.*,
           -- cohort on the PUBLISHED residency rule; the checker recomputes on
           -- residency_latest and reports the transition matrix.
           case when was_approved = 0 then null
                when residency_any3 = 'Town of Cochrane' and first_placement_in_cochrane = 1 then 'A'
                when residency_any3 = 'Not a Cochrane-area resident'
                     and first_placement_in_cochrane = 1                                  then 'B'
                when residency_any3 = 'Town of Cochrane' and placed = 1                   then 'C'
                when residency_any3 = 'Town of Cochrane' and placed = 0                   then 'D'
                else null end as cohort
    from master m
)

select *
from classified
where residency_any3 <> 'Not a Cochrane-area resident'
   or residency_latest <> 'Not a Cochrane-area resident'
   or first_placement_in_cochrane = 1
order by cohort nulls last, demand_dt
;
