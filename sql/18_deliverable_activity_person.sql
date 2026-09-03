-- ============================================================================
-- ACTIVITY-PERSON EXTRACT — attributes for the CONSULTANT ACTIVITY population
-- Generated from sql/14 (itself sql/09 rev 2.10 + enrichment) with ONE change:
-- the anchor is the person's first activity inside FY2022-FY2026 (first Type
-- A/B waitlist appearance, or first Cochrane-site admission), with no new-
-- demand gate and no prior-residential-care exclusion. Residency, community,
-- demographics, origin at first entry and rated sites are computed exactly as
-- in sql/14 but at that anchor. No A/B/C/D here: cohorts live in sql/14.
-- Feed the CSV to analysis/08 --activity-person.
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
        ('EDM - DSL4 / DSL4D',                             'Type B')
        -- Retired-DAL/DEL end in 2012 (check 2); they are history, never an
        -- outcome in this window, so they stay in hist_care_type only.
),
w as (
    select 3                  as occupancy_audit_threshold,   -- REV 2.9: reporting threshold only; never excludes
           -- REV 2.9 named Cochrane-area continuing-care sites (candidate reference; flag only)
           'BETHANY|BIG HILL LODGE|POINTS WEST|HAWTHORNE|EVERGREEN MANOR|ALORA|(^|[^0-9])(32 QUIGLEY|98 CAROLINA|60 FIRESIDE|300 ROSS|207 SUNSET)'
                              as named_facility_pat,
           '2021-04-01'::date as win_start,
           '2026-04-01'::date as win_end,           -- half-open
           '2026-03-31'::date as follow_up_end
),

-- ── STEP 1 — PHN ───────────────────────────────────────────────────────────
-- G5: count digits BEFORE padding. lpad(x,9) truncates anything longer.
pat_key as (
    select patient_id,
           iff(length(digits) = 9 and digits <> '000000000', digits, null) as phn,
           length(digits)                                                   as phn_raw_digits
    from (select p.id as patient_id, regexp_replace(p.identifier1::string,'[^0-9]','') as digits
          from db_source_strata_health_pathways.raw.patient p)
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
           iff(a.source_location is null, 1, 0) as null_source,
           trim(a.source_location)            as source_location      -- SQL14: origin for admission-only demand events
    from db_source_strata_health_pathways.raw.admissions a
    join pat_key k        on k.patient_id = a.patient_id
    left join coch_site s on s.site_name  = trim(a.admission_location)
    where trim(a.source_location) is distinct from trim(a.admission_location)
      and k.phn is not null
      and split_part(trim(a.admission_location), ' - ', 1) <> 'TEST'   -- one test row (check 1)
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
    select phn, census_date, approved_dt, assess_dt, calc_dt, current_location, rated_cochrane
    from (
    select regexp_replace(t.phn::string,'[^0-9]','')            as phn,      -- G5: no lpad
           t.census_date::date                                   as census_date,
           coalesce(t.assess_approved_date,
                    t.calculated_assess_approved_date)::date     as approved_dt,   -- row-level (current)
           t.assess_approved_date::date                          as assess_dt,     -- G1
           t.calculated_assess_approved_date::date               as calc_dt,       -- G1
           t.current_location,
           iff(t.service_provider_rated_site ilike '%cochrane%'
               or t.service_provider_rated_site ilike '%hawthorne%', 1, 0) as rated_cochrane
    from db_team_continuing_seniors_care.calgary_bi.ts_waitlist_trend_with_ratings_1671 t
    join rep_care_type r on r.care_type = trim(t.care_type)
    cross join w
    where t.census_date >= w.win_start and t.census_date < w.win_end
      and t.phn is not null
    )
    where length(phn) = 9 and phn <> '000000000'          -- G5: exactly nine digits, no padding
),
census_bounds as (select min(census_date) as first_dt, max(census_date) as last_dt from wl),
first_list as (
    select l.phn,
           min(l.census_date)                          as first_list_appearance,
           min(l.approved_dt)                          as first_approval_dt,        -- current: min of row-level coalesce
           coalesce(min(l.assess_dt), min(l.calc_dt))  as first_approval_dt_alt,    -- G1: person-level coalesce
           min_by(l.current_location, l.census_date)   as setting_at_list_entry,
           max(l.census_date)                          as last_seen_on_list,
           iff(max(l.census_date) = cb.last_dt, 1, 0)  as on_list_at_followup,   -- D1
           iff(min(l.census_date) = cb.first_dt, 1, 0) as left_truncated,
           max(l.rated_cochrane)                       as rated_cochrane
    from wl l cross join census_bounds cb
    group by l.phn, cb.last_dt, cb.first_dt
),

-- ── STEP 4 — THE DEMAND EVENT = APPROVAL, OR ADMISSION IF NEVER APPROVED ───
-- A person on the list but never approved was never ready for a bed. They
-- are carried (was_approved = 0) and excluded from A/B/C/D.
-- "Already in care" uses the HISTORICAL scope.
-- SQL18 anchor = FIRST ACTIVITY IN THE WINDOW, not the incident demand event:
-- the earlier of the first Type A/B waitlist appearance in FY2022-FY2026 and
-- the first admission to a Cochrane site in FY2022-FY2026. No new-demand gate,
-- no prior-residential-care exclusion: this is the ACTIVITY population.
coch_adm_first as (
    select phn, min(admission_date) as first_coch_adm
    from adm_rep cross join w
    where in_cochrane = 1 and admission_date >= w.win_start and admission_date <= w.follow_up_end
    group by phn
),
demand as (
    select coalesce(l.phn, c.phn)                                          as phn,
           least(coalesce(l.first_list_appearance, '9999-12-31'::date),
                 coalesce(c.first_coch_adm,        '9999-12-31'::date))     as demand_dt,       -- ACTIVITY ANCHOR
           least(coalesce(l.first_list_appearance, '9999-12-31'::date),
                 coalesce(c.first_coch_adm,        '9999-12-31'::date))     as demand_dt_alt,
           l.first_approval_dt_alt,
           iff(l.first_list_appearance is not null
               and (c.first_coch_adm is null or l.first_list_appearance <= c.first_coch_adm),
               'approval', 'admission')                                    as demand_event_type,   -- here: 'waitlist' vs 'Cochrane admission'
           1                                                               as was_approved,
           l.first_list_appearance, l.first_approval_dt, l.setting_at_list_entry,
           l.last_seen_on_list, coalesce(l.on_list_at_followup,0) as on_list_at_followup,
           coalesce(l.left_truncated, 0)                                    as left_truncated,
           coalesce(l.rated_cochrane, 0)                                    as rated_cochrane,
           h.first_residential_ever, h.first_residential_stream
    from first_list l
    full outer join coch_adm_first c on c.phn = l.phn
    left join first_ever_residential h on h.phn = coalesce(l.phn, c.phn)
),
demand_in_window as (
    select d.*,
           iff(month(d.demand_dt) >= 4, year(d.demand_dt) + 1, year(d.demand_dt))         as demand_fye,
           iff(month(d.demand_dt_alt) >= 4, year(d.demand_dt_alt) + 1, year(d.demand_dt_alt)) as demand_fye_alt,
           1 as in_window, 1 as in_window_alt
    from demand d
),

res_rows as (
    select d.phn, d.demand_fye, d.demand_fye_alt, g.fye, g.postal_cd, g.mapped, g.in_town, g.in_area, g.phn_was_padded,
           iff(g.fye between d.demand_fye-3 and d.demand_fye-1, 1, 0)         as in_window,
           iff(g.fye <= d.demand_fye-1, 1, 0)                                  as pre_demand,
           iff(g.fye between d.demand_fye_alt-3 and d.demand_fye_alt-1, 1, 0) as in_window_alt   -- G1
    from demand_in_window d
    left join geo g on g.phn = d.phn
),
residency as (
    select phn,
           count(fye)                                                   as n_registry_fye,
           max(phn_was_padded)                                          as registry_phn_was_padded,
           count_if(in_window=1)                                        as n_window_fye,
           count_if(in_window=1 and postal_cd is not null)              as n_window_with_postal,
           count_if(in_window=1 and mapped=1)                           as n_window_mapped,
           -- METHOD A (published): any Town address in the window
           max(iff(in_window=1 and in_town=1, 1, 0))                    as town_any3,
           max(iff(in_window=1 and in_area=1, 1, 0))                    as area_any3,
           -- METHOD B: the most recent mapped address in the window
           max_by(in_town, iff(in_window=1 and mapped=1, fye, null))    as town_latest,
           max_by(in_area, iff(in_window=1 and mapped=1, fye, null))    as area_latest,
           max(iff(in_window=1 and mapped=1, fye, null))                as latest_window_fye,
           max_by(postal_cd, iff(in_window=1 and mapped=1, fye, null))  as registry_postal_latest,   -- SQL14: the deciding address
           -- for residency_evidence: was there a mapped address in the year
           -- immediately before demand, and is the lookback internally stable
           max(iff(in_window=1 and mapped=1 and fye = demand_fye-1, 1, 0)) as mapped_year_before,
           count(distinct iff(in_window=1 and mapped=1 and in_town=1, fye, null)) as n_town_years_in_window,
           -- FALLBACK: latest mapped address before the demand event at any
           -- distance. Resolves "registry record, no year in lookback".
           count_if(pre_demand=1 and mapped=1)                          as n_predemand_mapped,
           max_by(in_town, iff(pre_demand=1 and mapped=1, fye, null))   as town_fallback,
           max_by(in_area, iff(pre_demand=1 and mapped=1, fye, null))   as area_fallback,
           max(iff(pre_demand=1 and mapped=1, fye, null))               as fallback_fye,
           -- G1: the same latest-address rule at the alternative anchor
           count_if(in_window_alt=1 and mapped=1)                       as n_window_mapped_alt,
           max_by(in_town, iff(in_window_alt=1 and mapped=1, fye, null)) as town_latest_alt,
           max_by(in_area, iff(in_window_alt=1 and mapped=1, fye, null)) as area_latest_alt
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
    select phn, min(death_dt) as death_dt from (
        select regexp_replace(stkh_num_1::string,'[^0-9]','') as phn, dethdate::date as death_dt   -- G5: no lpad
        from db_source_ah_vital_stats.curated.tb_vital_stats_deaths_adhoc
    ) where length(phn) = 9 and phn <> '000000000'
    group by 1
),

-- ── STEP 6b — STRATA ADDRESS HISTORY (secondary residency source) ─────────
-- All address records ever linked to a patient, through patient_h reduced to
-- distinct pairs (ADDITION A), then every dated version of those records.
strata_addr as (
    select k.phn,
           ah.id                                                   as address_record_id,
           trim(ah.street_address)                                 as street_address,
           trim(ah.city_name)                                      as city_name,
           upper(regexp_replace(ah.postal_code, '[^A-Za-z0-9]', '')) as postal_norm,
           ah.effective_from_date::date                            as eff_from,
           ah.effective_to_date::date                              as eff_to,
           ph.created                                              as created   -- from patient_h, not address_h
    -- creation_date is a patient_h column. The earliest creation of the
    -- (patient, address record) pairing is what an address version's start
    -- date is compared against in ADDITION C.
    from (select id as patient_id, address_id, min(creation_date)::date as created
          from db_source_strata_health_pathways.raw.patient_h
          where address_id is not null
          group by 1,2) ph
    join pat_key k on k.patient_id = ph.patient_id
    join (select distinct id, street_address, city_name, postal_code, effective_from_date,
                 effective_to_date
          from db_source_strata_health_pathways.raw.address_h) ah on ah.id = ph.address_id
    where k.phn is not null
),
-- REV 2.8: building key. Strip unit designators and abbreviate street types,
-- so every unit of one building shares a key. civic = leading civic number
-- after stripping, for the spelling-variant check.
-- placeholder-address patterns; defined here because strata_addr_b and epic_addr both join to it
strata_placeholder (pat) as (
    select * from values ('%NO FIXED%'),('%NFA%'),('%EVACUEE%'),('%UNKNOWN%'),('%HOMELESS%'),('%SHELTER%'),('%TRANSIENT%'),
        -- SQL14: dummy / test addresses must never resolve residency (reviewer, item 12)
        ('%ANY STREET%'),('%ANYSTREET%'),('%123 ANY %'),('TEST %'),('% TEST %'),('%TEST ADDRESS%'),('%TEST PATIENT%'),
        ('%SAMPLE ADDRESS%'),('%DUMMY%'),('%FAKE ADDRESS%')
),
strata_addr_k as (   -- REV 2.9: QA key only; numbered streets protected
    select a.*,
           trim(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(upper(a.street_address),
             '[#,.]', ' '),
             '([0-9]+)\\s+(STREET|ST|AVENUE|AVE|AV|ROAD|RD|DRIVE|DR|BOULEVARD|BLVD|WAY|CRESCENT|CRES|TRAIL|TR|HIGHWAY|HWY)($|[^A-Z])', '\\1~\\2\\3'),
             '(^|[^A-Z])(UNIT|APT|APARTMENT|SUITE|STE|RM|ROOM)\\s*[A-Z]?[0-9]+[A-Z]?', '\\1 '),
             '(^|[^A-Z])(BSMT|BASEMENT)([^A-Z]|$)', '\\1 \\3'),
             '(^|[^A-Z])(LOWER|UPPER|MAIN)\\s+(FLOOR|FLR|LEVEL)([^A-Z]|$)', '\\1 \\4'),
             '^\\s*[A-Z]?[0-9]+[A-Z]?\\s*-\\s*([0-9])', '\\1'),
             '^\\s*[0-9]+[A-Z]?\\s+([0-9]+\\s+[A-Z])', '\\1'),
             '^\\s*-\\s*', ''),
             '\\s+', ' '),
             '(^|[^A-Z])AVENUE($|[^A-Z])', '\\1AVE\\2'),
             '(^|[^A-Z])STREET($|[^A-Z])', '\\1ST\\2'),
             '(^|[^A-Z])DRIVE($|[^A-Z])', '\\1DR\\2'),
             '(^|[^A-Z])ROAD($|[^A-Z])', '\\1RD\\2'),
             '(^|[^A-Z])CRESCENT($|[^A-Z])', '\\1CRES\\2'),
             '(^|[^A-Z])BOULEVARD($|[^A-Z])', '\\1BLVD\\2'),
             '~', ' ')) as bldg_key
    from strata_addr a
),
strata_addr_b as (
    select k.*,
           regexp_substr(k.bldg_key, '^[0-9]+')                              as civic,
           iff(sp.pat is not null, 1, 0)                                      as is_placeholder,
           iff(regexp_substr(upper(k.street_address), w.named_facility_pat) is not null, 1, 0)
                                                                              as named_facility_candidate   -- REV 2.9 flag only
    from strata_addr_k k
    cross join w
    left join strata_placeholder sp on upper(k.street_address) like sp.pat
    qualify row_number() over (partition by k.phn, k.address_record_id, k.street_address, k.postal_norm,
                                            k.eff_from, k.eff_to order by sp.pat) = 1
),
-- ever-shared count kept for reporting only (was the guard before rev 2.6)
strata_shared as (
    select upper(street_address) as street_u, postal_norm, count(distinct phn) as n_patients
    from strata_addr group by 1,2
),
-- G4: placeholder strings are never an address
-- all versions ACTIVE on the demand date (rules 3, 8), one row per version
-- REV 2.8.1: correlated scalar subqueries are not supported by Snowflake in
-- this shape ("Unsupported subquery type"). Concurrency is computed as
-- pre-aggregated joins keyed on a row hash and joined back.
strata_active_base as (
    select hash(d.phn, a.address_record_id, a.street_address, a.postal_norm, a.eff_from, a.eff_to) as rk,
           d.phn, d.demand_dt, a.street_address, a.city_name, a.postal_norm, a.eff_from, a.eff_to, a.created,
           a.is_placeholder, a.bldg_key, a.civic, a.named_facility_candidate
    from demand_in_window d
    join strata_addr_b a on a.phn = d.phn
                        and a.eff_from <= d.demand_dt
                        and (a.eff_to > d.demand_dt or a.eff_to is null)
),
strata_conc_exact as (       -- G4: distinct people holding THIS address on THIS day
    select s.rk, count(distinct b.phn) as concurrent_n
    from strata_active_base s
    join strata_addr b on upper(b.street_address) = upper(s.street_address) and b.postal_norm = s.postal_norm
                      and b.eff_from <= s.demand_dt and (b.eff_to > s.demand_dt or b.eff_to is null)
    group by s.rk
),
strata_conc_bldg as (        -- REV 2.8: same BUILDING on this day
    select s.rk, count(distinct b.phn) as building_concurrent_n
    from strata_active_base s
    join strata_addr_b b on b.bldg_key = s.bldg_key and b.postal_norm = s.postal_norm
                        and b.eff_from <= s.demand_dt and (b.eff_to > s.demand_dt or b.eff_to is null)
    group by s.rk
),
strata_conc_civic as (       -- REV 2.8: same civic number + postal (spelling variants)
    select s.rk, count(distinct b.phn) as civic_concurrent_n
    from strata_active_base s
    join strata_addr_b b on b.civic = s.civic and s.civic is not null and b.postal_norm = s.postal_norm
                        and b.eff_from <= s.demand_dt and (b.eff_to > s.demand_dt or b.eff_to is null)
    group by s.rk
),
strata_active as (
    select s.rk, s.phn, s.demand_dt, s.street_address, s.city_name, s.postal_norm, s.eff_from, s.eff_to, s.created,
           s.is_placeholder, s.named_facility_candidate,
           coalesce(ce.concurrent_n, 1)          as concurrent_n,
           coalesce(cb.building_concurrent_n, 1) as building_concurrent_n,
           coalesce(cc.civic_concurrent_n, 1)    as civic_concurrent_n,
           s.bldg_key, s.civic,
           pc.postalcode is not null                                  as mapped,
           case when pc.postalcode is not null and upper(trim(pc.csdname_2021)) = 'COCHRANE'
                     and upper(trim(pc.csdtype_2021)) = 'T'          then 'Town of Cochrane'
                when pc.postalcode is not null
                     and upper(trim(pc.local_name)) = 'COCHRANE | SPRINGBANK' then 'Cochrane catchment'
                when pc.postalcode is not null                       then 'Not a Cochrane-area resident'
                when s.postal_norm is not null and left(s.postal_norm,1) <> 'T'
                     and regexp_like(s.postal_norm, '[ABCEGHJ-NPRSTVXY][0-9][ABCEGHJ-NPRSTV-Z][0-9][ABCEGHJ-NPRSTV-Z][0-9]') and s.postal_norm not in ('Z1Z1Z1','A1A1A1','H0H0H0','X0X0X0','T0T0T0','A0A0A0')
                                                                     then 'Not a Cochrane-area resident'   -- REV 2.10: a VALID out-of-Alberta code only
                else 'UNRESOLVED' end                                 as class_raw
    from strata_active_base s
    left join strata_conc_exact ce on ce.rk = s.rk
    left join strata_conc_bldg  cb on cb.rk = s.rk
    left join strata_conc_civic cc on cc.rk = s.rk
    left join db_source_ah_postal_code.curated.tb_postal_code pc
           on upper(regexp_replace(pc.postalcode, '[^A-Za-z0-9]', '')) = s.postal_norm
),
-- G2: how many were active, and do they disagree on class?
strata_active_summary as (
    select phn, count(*) as n_active,
           count(distinct class_raw) as n_classes,
           iff(count(distinct class_raw) > 1, 1, 0) as classes_disagree
    from strata_active group by phn
),
-- the version chosen by the tiebreak (rule 4): latest effective_from, then postal
strata_at_demand as (
    select sa.*, sh.n_patients as shared_by_n,
           iff(sa.eff_from = sa.created, 1, 0) as from_equals_creation,
           ss.n_active, ss.classes_disagree
    from strata_active sa
    join strata_active_summary ss on ss.phn = sa.phn
    left join strata_shared sh on sh.street_u = upper(sa.street_address) and sh.postal_norm = sa.postal_norm
    qualify row_number() over (partition by sa.phn order by sa.eff_from desc, sa.postal_norm) = 1
),
-- G1: the same lookup at the alternative anchor (chosen version only)
strata_active_alt_all as (
    select d.phn, a.postal_norm,
           case when pc.postalcode is not null and upper(trim(pc.csdname_2021)) = 'COCHRANE'
                     and upper(trim(pc.csdtype_2021)) = 'T'          then 'Town of Cochrane'
                when pc.postalcode is not null
                     and upper(trim(pc.local_name)) = 'COCHRANE | SPRINGBANK' then 'Cochrane catchment'
                when pc.postalcode is not null                       then 'Not a Cochrane-area resident'
                when a.postal_norm is not null and left(a.postal_norm,1) <> 'T'
                     and regexp_like(a.postal_norm, '[ABCEGHJ-NPRSTVXY][0-9][ABCEGHJ-NPRSTV-Z][0-9][ABCEGHJ-NPRSTV-Z][0-9]') and a.postal_norm not in ('Z1Z1Z1','A1A1A1','H0H0H0','X0X0X0','T0T0T0','A0A0A0')
                                                                     then 'Not a Cochrane-area resident'   -- REV 2.10: a VALID out-of-Alberta code only
                else 'UNRESOLVED' end                                 as class_raw
    from demand_in_window d
    join strata_addr_b a on a.phn = d.phn and a.eff_from <= d.demand_dt_alt
                        and (a.eff_to > d.demand_dt_alt or a.eff_to is null)
    left join db_source_ah_postal_code.curated.tb_postal_code pc
           on upper(regexp_replace(pc.postalcode, '[^A-Za-z0-9]', '')) = a.postal_norm
),
strata_alt_summary as (
    select phn, iff(count(distinct class_raw) > 1, 1, 0) as classes_disagree_alt from strata_active_alt_all group by phn
),
strata_active_alt_base as (
    select hash(d.phn, a.address_record_id, a.street_address, a.postal_norm, a.eff_from, a.eff_to) as rk,
           d.phn, d.demand_dt_alt, a.postal_norm, a.street_address, a.eff_from, a.is_placeholder, a.bldg_key, a.civic,
           a.named_facility_candidate
    from demand_in_window d
    join strata_addr_b a on a.phn = d.phn
                        and a.eff_from <= d.demand_dt_alt
                        and (a.eff_to > d.demand_dt_alt or a.eff_to is null)
),
strata_conc_exact_alt as (
    select s.rk, count(distinct b.phn) as concurrent_n
    from strata_active_alt_base s
    join strata_addr b on upper(b.street_address) = upper(s.street_address) and b.postal_norm = s.postal_norm
                      and b.eff_from <= s.demand_dt_alt and (b.eff_to > s.demand_dt_alt or b.eff_to is null)
    group by s.rk
),
strata_conc_bldg_alt as (
    select s.rk, count(distinct b.phn) as building_concurrent_n
    from strata_active_alt_base s
    join strata_addr_b b on b.bldg_key = s.bldg_key and b.postal_norm = s.postal_norm
                        and b.eff_from <= s.demand_dt_alt and (b.eff_to > s.demand_dt_alt or b.eff_to is null)
    group by s.rk
),
strata_conc_civic_alt as (
    select s.rk, count(distinct b.phn) as civic_concurrent_n
    from strata_active_alt_base s
    join strata_addr_b b on b.civic = s.civic and s.civic is not null and b.postal_norm = s.postal_norm
                        and b.eff_from <= s.demand_dt_alt and (b.eff_to > s.demand_dt_alt or b.eff_to is null)
    group by s.rk
),
strata_at_demand_alt as (
    select s.phn, s.postal_norm, s.street_address, ss.classes_disagree_alt, s.is_placeholder, s.named_facility_candidate,
           coalesce(ce.concurrent_n, 1)          as concurrent_n,
           coalesce(cb.building_concurrent_n, 1) as building_concurrent_n,
           coalesce(cc.civic_concurrent_n, 1)    as civic_concurrent_n,
           case when pc.postalcode is not null and upper(trim(pc.csdname_2021)) = 'COCHRANE'
                     and upper(trim(pc.csdtype_2021)) = 'T'          then 'Town of Cochrane'
                when pc.postalcode is not null
                     and upper(trim(pc.local_name)) = 'COCHRANE | SPRINGBANK' then 'Cochrane catchment'
                when pc.postalcode is not null                       then 'Not a Cochrane-area resident'
                when s.postal_norm is not null and left(s.postal_norm,1) <> 'T'
                     and regexp_like(s.postal_norm, '[ABCEGHJ-NPRSTVXY][0-9][ABCEGHJ-NPRSTV-Z][0-9][ABCEGHJ-NPRSTV-Z][0-9]') and s.postal_norm not in ('Z1Z1Z1','A1A1A1','H0H0H0','X0X0X0','T0T0T0','A0A0A0')
                                                                     then 'Not a Cochrane-area resident'   -- REV 2.10: a VALID out-of-Alberta code only
                else 'UNRESOLVED' end                                 as class_raw
    from strata_active_alt_base s
    join strata_alt_summary ss on ss.phn = s.phn
    left join strata_conc_exact_alt ce on ce.rk = s.rk
    left join strata_conc_bldg_alt  cb on cb.rk = s.rk
    left join strata_conc_civic_alt cc on cc.rk = s.rk
    left join db_source_ah_postal_code.curated.tb_postal_code pc
           on upper(regexp_replace(pc.postalcode, '[^A-Za-z0-9]', '')) = s.postal_norm
    qualify row_number() over (partition by s.phn order by s.eff_from desc, s.postal_norm) = 1
),
-- rule 9: nothing active at demand, but an older address exists
strata_historical as (
    select d.phn, a.postal_norm, a.eff_from,
           datediff('year', a.eff_from, d.demand_dt)                as years_before_demand
    from demand_in_window d
    join strata_addr a on a.phn = d.phn and a.eff_from <= d.demand_dt
    left join strata_at_demand sad on sad.phn = d.phn
    where sad.phn is null
    qualify row_number() over (partition by d.phn order by a.eff_from desc) = 1
),
-- ── STEP 6c — EPIC ADDRESS HISTORY (sensitivity only) ─────────────────────
epic_phn as (
    select pat_id, digits as phn
    from (select pat_id, regexp_replace(identity_id::string,'[^0-9]','') as digits
          from db_source_epic_clarity.raw.identity_id where identity_type_id = '221')
    where length(digits) = 9 and digits <> '000000000'
),
epic_src_max as (select max(eff_start_date::date) as max_start from db_source_epic_clarity.raw.pat_addr_chng_hx),
epic_addr as (
    select e.phn,
           trim(a.addr_hx_line1)                                   as line1,
           trim(a.city_hx)                                         as city,
           upper(regexp_replace(a.zip_hx,'[^A-Za-z0-9]',''))       as postal_norm,
           a.eff_start_date::date                                  as eff_from,
           a.eff_end_date::date                                    as eff_to,
           iff(upper(a.addr_hx_line1) like 'PO BOX%' or upper(a.addr_hx_line1) like 'P.O. BOX%'
               or upper(a.addr_hx_line1) like 'BOX %', 1, 0)        as is_pobox,
           iff(sp.pat is not null, 1, 0)                            as is_placeholder,
           iff(regexp_substr(upper(a.addr_hx_line1), w.named_facility_pat) is not null, 1, 0)
                                                                    as named_facility_candidate   -- REV 2.9 flag only
    from db_source_epic_clarity.raw.pat_addr_chng_hx a
    join epic_phn e on e.pat_id = a.pat_id
    cross join w
    left join strata_placeholder sp on upper(a.addr_hx_line1) like sp.pat
    where a.addr_hx_line1 is not null or a.zip_hx is not null
    -- one row per distinct (phn, address, dates); exact raw duplicates collapse here,
    -- which matches the hash key used in epic_active_base
    qualify row_number() over (partition by e.phn, trim(a.addr_hx_line1), trim(a.city_hx),
                                            upper(regexp_replace(a.zip_hx,'[^A-Za-z0-9]','')),
                                            a.eff_start_date::date, a.eff_end_date::date
                               order by sp.pat) = 1
),
epic_addr_b as (     -- REV 2.9: QA key only; numbered streets protected
    select a.*,
           trim(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(regexp_replace(upper(a.line1),
             '[#,.]', ' '),
             '([0-9]+)\\s+(STREET|ST|AVENUE|AVE|AV|ROAD|RD|DRIVE|DR|BOULEVARD|BLVD|WAY|CRESCENT|CRES|TRAIL|TR|HIGHWAY|HWY)($|[^A-Z])', '\\1~\\2\\3'),
             '(^|[^A-Z])(UNIT|APT|APARTMENT|SUITE|STE|RM|ROOM)\\s*[A-Z]?[0-9]+[A-Z]?', '\\1 '),
             '(^|[^A-Z])(BSMT|BASEMENT)([^A-Z]|$)', '\\1 \\3'),
             '(^|[^A-Z])(LOWER|UPPER|MAIN)\\s+(FLOOR|FLR|LEVEL)([^A-Z]|$)', '\\1 \\4'),
             '^\\s*[A-Z]?[0-9]+[A-Z]?\\s*-\\s*([0-9])', '\\1'),
             '^\\s*[0-9]+[A-Z]?\\s+([0-9]+\\s+[A-Z])', '\\1'),
             '^\\s*-\\s*', ''),
             '\\s+', ' '),
             '(^|[^A-Z])AVENUE($|[^A-Z])', '\\1AVE\\2'),
             '(^|[^A-Z])STREET($|[^A-Z])', '\\1ST\\2'),
             '(^|[^A-Z])DRIVE($|[^A-Z])', '\\1DR\\2'),
             '(^|[^A-Z])ROAD($|[^A-Z])', '\\1RD\\2'),
             '(^|[^A-Z])CRESCENT($|[^A-Z])', '\\1CRES\\2'),
             '(^|[^A-Z])BOULEVARD($|[^A-Z])', '\\1BLVD\\2'),
             '~', ' ')) as bldg_key
    from epic_addr a
),
epic_addr_c as (select b.*, regexp_substr(b.bldg_key, '^[0-9]+') as civic from epic_addr_b b),
epic_active_base as (
    select hash(d.phn, a.line1, a.postal_norm, a.eff_from, a.eff_to) as rk,
           d.phn, d.demand_dt, a.line1, a.city, a.postal_norm, a.eff_from, a.eff_to, a.is_pobox, a.is_placeholder,
           a.bldg_key, a.civic, a.named_facility_candidate,
           iff(a.eff_from = m.max_start, 1, 0)                     as start_equals_source_max,
           iff(a.eff_from in ('2019-08-16'::date, '2019-08-17'::date), 1, 0) as start_is_migration_date
    from demand_in_window d
    join epic_addr_c a on a.phn = d.phn
                      and a.eff_from <= d.demand_dt
                      and (a.eff_to > d.demand_dt or a.eff_to is null)
    cross join epic_src_max m
),
epic_conc_exact as (
    select s.rk, count(distinct b.phn) as concurrent_n
    from epic_active_base s
    join epic_addr b on upper(b.line1) = upper(s.line1) and b.postal_norm = s.postal_norm
                    and b.eff_from <= s.demand_dt and (b.eff_to > s.demand_dt or b.eff_to is null)
    group by s.rk
),
epic_conc_bldg as (
    select s.rk, count(distinct b.phn) as building_concurrent_n
    from epic_active_base s
    join epic_addr_c b on b.bldg_key = s.bldg_key and b.postal_norm = s.postal_norm
                      and b.eff_from <= s.demand_dt and (b.eff_to > s.demand_dt or b.eff_to is null)
    group by s.rk
),
epic_conc_civic as (
    select s.rk, count(distinct b.phn) as civic_concurrent_n
    from epic_active_base s
    join epic_addr_c b on b.civic = s.civic and s.civic is not null and b.postal_norm = s.postal_norm
                      and b.eff_from <= s.demand_dt and (b.eff_to > s.demand_dt or b.eff_to is null)
    group by s.rk
),
epic_active as (
    select s.*,
           coalesce(ce.concurrent_n, 1)          as concurrent_n,
           coalesce(cb.building_concurrent_n, 1) as building_concurrent_n,
           coalesce(cc.civic_concurrent_n, 1)    as civic_concurrent_n,
           case when pc.postalcode is not null and upper(trim(pc.csdname_2021)) = 'COCHRANE'
                     and upper(trim(pc.csdtype_2021)) = 'T'          then 'Town of Cochrane'
                when pc.postalcode is not null
                     and upper(trim(pc.local_name)) = 'COCHRANE | SPRINGBANK' then 'Cochrane catchment'
                when pc.postalcode is not null                       then 'Not a Cochrane-area resident'
                when s.postal_norm is not null and left(s.postal_norm,1) <> 'T'
                     and regexp_like(s.postal_norm, '[ABCEGHJ-NPRSTVXY][0-9][ABCEGHJ-NPRSTV-Z][0-9][ABCEGHJ-NPRSTV-Z][0-9]') and s.postal_norm not in ('Z1Z1Z1','A1A1A1','H0H0H0','X0X0X0','T0T0T0','A0A0A0')
                                                                     then 'Not a Cochrane-area resident'   -- REV 2.10: a VALID out-of-Alberta code only
                else 'UNRESOLVED' end                                 as class_raw
    from epic_active_base s
    left join epic_conc_exact ce on ce.rk = s.rk
    left join epic_conc_bldg  cb on cb.rk = s.rk
    left join epic_conc_civic cc on cc.rk = s.rk
    left join db_source_ah_postal_code.curated.tb_postal_code pc
           on upper(regexp_replace(pc.postalcode,'[^A-Za-z0-9]','')) = s.postal_norm
),
epic_summary as (
    select phn,
           count(*)                                                as n_active,
           count(distinct class_raw)                               as n_classes,
           iff(count(distinct class_raw) > 1, 1, 0)                as classes_disagree,
           max(is_pobox) as any_pobox, max(is_placeholder) as any_placeholder,
           max(named_facility_candidate)                           as any_named_facility,       -- REV 2.9 flag only
           max(concurrent_n)                                       as max_exact_concurrent_n,   -- REV 2.9 audit
           max(greatest(building_concurrent_n, civic_concurrent_n)) as max_building_concurrent_any,  -- QA only
           max(building_concurrent_n)                              as max_building_concurrent_n,
           max(start_equals_source_max)                            as any_start_equals_source_max,
           max(start_is_migration_date)                            as any_start_is_migration_date,
           min(class_raw)                                          as class_if_unanimous
    from epic_active group by phn
),
epic_at_demand as (
    select ea.*, es.n_active, es.classes_disagree, es.any_pobox, es.any_placeholder, es.any_named_facility,
           iff(es.max_exact_concurrent_n >= w.occupancy_audit_threshold, 1, 0)     as occupancy_flag,             -- REV 2.9 audit only
           iff(es.max_building_concurrent_any >= w.occupancy_audit_threshold, 1, 0) as building_occupancy_flag_qa, -- REV 2.9 QA only
           es.any_start_equals_source_max, es.any_start_is_migration_date, es.max_building_concurrent_n,
           -- reviewer instruction 5: never choose between conflicting classes.
           -- REV 2.9: no occupancy-based exclusion.
           case when es.any_placeholder = 1 then 'NOT USED - placeholder address'
                when es.any_pobox = 1       then 'NOT USED - PO Box'
                when es.classes_disagree = 1 then 'CONFLICT - active addresses disagree'
                else es.class_if_unanimous end                       as epic_residency
    from epic_active ea join epic_summary es on es.phn = ea.phn
    cross join w
    qualify row_number() over (partition by ea.phn order by ea.eff_from desc, ea.postal_norm) = 1
),

-- rule 5 mapping is inside strata_active (same postal geography, never city_name)
strata_geo as (
    select s.*, s.class_raw as strata_residency_raw from strata_at_demand s
),

-- ── STEP 7 — ONE ROW PER PERSON ────────────────────────────────────────────
-- ── SQL14 ENRICHMENT CTEs (LEFT-joined into master by PHN; add columns only) ──
-- SQL14 pat_ids: every Strata PATIENT_ID carrying this PHN, with its activity
pat_ids_all as (
    select k.phn, k.patient_id,
           coalesce(ad.n, 0) as n_admissions, coalesce(wr.n, 0) as n_waitlist_rows,
           p.modification_date, p.identifier1_is_autogen, p.birth_date::date as dob
    from pat_key k
    join db_source_strata_health_pathways.raw.patient p on p.id = k.patient_id
    left join (select patient_id, count(*) as n from db_source_strata_health_pathways.raw.admissions group by 1) ad on ad.patient_id = k.patient_id
    left join (select patient_id, count(*) as n
               from db_team_continuing_seniors_care.calgary_bi.ts_waitlist_trend_with_ratings_1671
               where census_date >= '2021-04-01' and census_date < '2026-04-01' group by 1) wr on wr.patient_id = k.patient_id
    where k.phn is not null
),
pat_ids as (
    select phn,
           count(distinct patient_id)                                             as n_patient_ids,
           -- canonical: the ID with the activity; ties -> most recently modified; never plain MIN
           max_by(patient_id, (n_admissions + n_waitlist_rows) * 1000000000 + coalesce(datediff('second','2000-01-01',modification_date),0)) as patient_id,
           listagg(distinct patient_id::string, '|')                              as patient_id_all,
           count_if(n_admissions + n_waitlist_rows > 0)                           as n_ids_with_activity,
           case when count(distinct patient_id) = 1 then '1:1'
                when count_if(n_admissions + n_waitlist_rows > 0) <= 1 then '1:N ids, one carries activity (shells)'
                else '1:N ids, several carry activity (split record)' end         as phn_patient_id_multiplicity,
           max(iff(identifier1_is_autogen, 1, 0))                                 as phn_is_autogen_any,
           min(dob)                                                               as dob_strata,
           count(distinct dob)                                                    as n_dob_strata
    from pat_ids_all group by phn
),
-- SQL14 reg_demo: Registry DOB and SEX, one value per PHN, conflicts counted
reg_demo as (
    select phn,
           min(dob)                                    as dob_registry,
           count(distinct dob)                         as n_dob_registry,
           max_by(iff(sex in ('F','M'), sex, null), iff(sex in ('F','M'), fye, null)) as sex_registry,   -- most recent fiscal year's F/M value
           count(distinct iff(sex in ('F','M'), sex, null))                             as n_sex_registry
    from (select iff(length(d) between 1 and 9, lpad(d, 9, '0'), null) as phn, birth_dt::date as dob, sex, fye
          from (select regexp_replace(phn::string,'[^0-9]','') as d, birth_dt, sex, fye
                from db_source_ah_provincial_registry.curated.provincial_registry)
          where sex in ('F','M') or birth_dt is not null)
    where phn is not null and phn <> '000000000'
    group by phn
),
-- SQL14 origin_entry: the setting on the FIRST census date the person appears
-- (where they entered the pathway from). Ties on that date are AUDITED, never
-- broken by min_by/max_by: n_origin_locations_at_entry, origin_location_list,
-- origin_conflict_flag. origin_setting_raw is the single value only when there
-- is exactly one; the builder normalises each listed value and reports agreement.
origin_entry as (
    select l.phn,
           min(l.census_date)                                        as entry_census_date,
           count(distinct l.current_location)                        as n_origin_locations_at_entry,
           listagg(distinct l.current_location, ' | ') within group (order by l.current_location) as origin_location_list,
           iff(count(distinct l.current_location) > 1, 1, 0)         as origin_conflict_flag,
           iff(count(distinct l.current_location) = 1, min(l.current_location), null) as origin_location_at_entry
    from wl l
    join (select phn, min(census_date) as first_dt from wl group by phn) f on f.phn = l.phn and f.first_dt = l.census_date
    group by l.phn
),
-- SQL14 origin_at_demand: the waitlist location nearest the demand event (QA only)
origin_at_demand as (
    select d.phn,
           coalesce(max_by(l.current_location, iff(l.census_date <= d.demand_dt, l.census_date, null)),
                    min_by(l.current_location, iff(l.census_date >  d.demand_dt, l.census_date, null)))  as origin_location,
           coalesce(max(iff(l.census_date <= d.demand_dt, l.census_date, null)),
                    min(iff(l.census_date >  d.demand_dt, l.census_date, null)))                          as origin_census_date
    from demand_in_window d
    join wl l on l.phn = d.phn
    group by d.phn, d.demand_dt
),
-- SQL14 requested: what the person rated / requested while on the list
wl_req as (
    select regexp_replace(t.phn::string,'[^0-9]','') as phn, t.census_date::date as census_date,
           t.service_provider_rated_site as rated_site, t.rating, r.care_stream,
           iff(t.service_provider_rated_site ilike '%cochrane%' or t.service_provider_rated_site ilike '%hawthorne%', 1, 0) as rated_cochrane
    from db_team_continuing_seniors_care.calgary_bi.ts_waitlist_trend_with_ratings_1671 t
    join rep_care_type r on r.care_type = trim(t.care_type)
    cross join w
    where t.census_date >= w.win_start and t.census_date < w.win_end and t.phn is not null
),
requested as (
    select phn,
           mode(rated_site)                                  as most_frequently_observed_rated_site,   -- daily snapshots: long-lasting ratings recur; NOT a preference
           count(distinct rated_site)                        as n_sites_requested,
           mode(care_stream)                                 as requested_care_stream,
           max(rated_cochrane)                               as requested_cochrane_flag,
           listagg(distinct iff(rated_cochrane = 1, rated_site, null), '|') as requested_cochrane_sites
    from wl_req where length(phn) = 9 and phn <> '000000000'
    group by phn
),
-- SQL14 community: postal code -> Statistics Canada census subdivision
pc_comm as (
    select postalcode as postal_raw,
           upper(regexp_replace(postalcode, '[^A-Za-z0-9]', '')) as postal_norm,
           trim(csdname_2021) || iff(csdtype_2021 is not null, ' (' || trim(csdtype_2021) || ')', '') as community,
           trim(local_name) as local_name
    from db_source_ah_postal_code.curated.tb_postal_code
    qualify row_number() over (partition by upper(regexp_replace(postalcode, '[^A-Za-z0-9]', '')) order by postalcode) = 1
),

master as (
    select d.phn, d.demand_dt, d.demand_fye, d.demand_event_type, d.was_approved,
           d.demand_dt_alt, d.demand_fye_alt, d.first_approval_dt_alt, d.in_window, d.in_window_alt,   -- G1
           d.first_list_appearance, d.first_approval_dt, d.setting_at_list_entry,
           d.last_seen_on_list, d.on_list_at_followup, d.left_truncated, d.rated_cochrane,
           d.first_residential_ever, d.first_residential_stream,
           -- SQL14 identification
           pi.patient_id, pi.patient_id_all, pi.n_patient_ids, pi.n_ids_with_activity,
           pi.phn_patient_id_multiplicity, pi.phn_is_autogen_any,
           -- SQL14 demographics: DOB primary Strata, fallback Registry; SEX Registry only
           coalesce(pi.dob_strata, rg.dob_registry)                            as dob,
           case when pi.dob_strata is not null then 'STRATA_PATIENT'
                when rg.dob_registry is not null then 'REGISTRY' else null end  as demographic_source,
           pi.dob_strata, rg.dob_registry, pi.n_dob_strata, rg.n_dob_registry,
           iff(pi.dob_strata is not null and rg.dob_registry is not null,
               iff(pi.dob_strata = rg.dob_registry, 1, 0), null)               as dob_sources_agree,
           iff(rg.n_sex_registry > 1, null, rg.sex_registry)                    as sex,
           iff(rg.n_sex_registry > 1, 1, 0)                                     as sex_conflict_registry,
           -- SQL14 origin setting at FIRST list entry (admission-only events: the admission's source_location)
           iff(d.demand_event_type = 'approval', oe.origin_location_at_entry, fa_src.source_location) as origin_setting_raw,
           iff(d.demand_event_type = 'approval',
               'waitlist current_location at first list entry ' || oe.entry_census_date::string,
               'admission source_location (admission-only demand event)')       as origin_source,
           oe.entry_census_date                                                 as origin_entry_census_date,
           iff(d.demand_event_type = 'approval', oe.n_origin_locations_at_entry, 1) as n_origin_locations_at_entry,
           iff(d.demand_event_type = 'approval', oe.origin_location_list, fa_src.source_location) as origin_location_list,
           iff(d.demand_event_type = 'approval', coalesce(oe.origin_conflict_flag, 0), 0) as origin_conflict_flag,
           od.origin_location                                                   as location_nearest_demand_raw,   -- QA only
           od.origin_census_date,
           -- SQL14 requested facility (preference; never used for cohort D)
           rq.most_frequently_observed_rated_site, rq.requested_care_stream, rq.n_sites_requested,
           coalesce(rq.requested_cochrane_flag, 0) as requested_cochrane_flag, rq.requested_cochrane_sites,
           -- SQL14 community candidates (chosen in master_final by residency_source)
           r.registry_postal_latest,
           pcr.community as registry_community_latest, pcr.local_name as registry_local_name_latest,
           pcs.community as strata_community_at_demand, pcs.local_name as strata_local_name_at_demand,
           coalesce(r.n_registry_fye,0) as n_registry_fye, coalesce(r.n_window_fye,0) as n_window_fye,
           coalesce(r.registry_phn_was_padded,0) as registry_phn_was_padded,
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
           -- G1: METHOD B at the alternative anchor
           case when coalesce(r.n_window_mapped_alt,0) = 0 then 'UNRESOLVED'
                when r.town_latest_alt = 1                  then 'Town of Cochrane'
                when r.area_latest_alt = 1                  then 'Cochrane catchment'
                else 'Not a Cochrane-area resident' end                              as residency_latest_alt,
           -- FALLBACK — only meaningful when residency_latest is UNRESOLVED
           case when coalesce(r.n_predemand_mapped,0) = 0 then 'UNRESOLVED'
                when r.town_fallback = 1                   then 'Town of Cochrane'
                when r.area_fallback = 1                   then 'Cochrane catchment'
                else 'Not a Cochrane-area resident' end                              as residency_fallback,
           iff(r.fallback_fye is null, null, d.demand_fye - r.fallback_fye)          as fallback_years_before_demand,
           -- depth of registry history. NOT confidence in residency at demand.
           case when coalesce(r.n_registry_fye,0)>=10 then 'HIGH'
                when coalesce(r.n_registry_fye,0)>=5  then 'MEDIUM' else 'LOW' end   as registry_history_depth,
           -- evidence for the residency verdict actually used
           case when coalesce(r.n_window_mapped,0) = 0 then 'NONE - no mapped address in lookback'
                when r.mapped_year_before = 1          then 'STRONG - mapped address in the year before demand'
                else 'MODERATE - mapped address in lookback, not the most recent year' end as residency_evidence,
           iff(coalesce(r.n_window_mapped,0) > 0
               and (coalesce(r.n_town_years_in_window,0) = 0
                    or coalesce(r.n_town_years_in_window,0) = coalesce(r.n_window_mapped,0)), 1, 0)
                                                                                       as residency_stable_in_lookback,
           -- STRATA secondary source (rev 2.5). Only meaningful when
           -- residency_latest = 'UNRESOLVED'; carried for everyone for audit.
           sg.street_address                                   as strata_address_at_demand,
           sg.postal_norm                                      as strata_postal_code_at_demand,
           sg.city_name                                        as strata_city_at_demand,
           sg.eff_from                                         as strata_effective_from,
           sg.shared_by_n                                      as strata_address_shared_by_n,       -- ever-shared, reporting only
           sg.concurrent_n                                     as strata_address_concurrent_n,      -- exact string, that day
           sg.building_concurrent_n                            as strata_building_concurrent_n_qa,  -- REV 2.9: QA only
           sg.civic_concurrent_n                               as strata_civic_concurrent_n_qa,     -- REV 2.9: QA only
           sg.bldg_key                                         as strata_building_key_qa,           -- REV 2.9: QA only
           -- REV 2.9: occupancy is REPORTED, never applied to the verdict
           iff(coalesce(sg.concurrent_n,0) >= w.occupancy_audit_threshold, 1, 0)      as strata_occupancy_flag,
           iff(greatest(coalesce(sg.building_concurrent_n,0), coalesce(sg.civic_concurrent_n,0))
               >= w.occupancy_audit_threshold, 1, 0)                                   as strata_building_occupancy_flag_qa,
           sg.named_facility_candidate                         as strata_named_facility_candidate,  -- REV 2.9: flag only
           sg.is_placeholder                                   as strata_address_is_placeholder,    -- G4
           sg.from_equals_creation                             as strata_from_equals_creation,
           sg.n_active                                         as strata_n_active_at_demand,        -- G2
           sg.classes_disagree                                 as strata_active_classes_disagree,   -- G2
           -- REV 2.9: no occupancy-based exclusion
           case when sg.phn is null                                   then null
                when sg.is_placeholder = 1                            then 'NOT USED - placeholder address'
                when sg.classes_disagree = 1                          then 'CONFLICT - active addresses disagree'   -- REV 2.8: blocks
                else sg.strata_residency_raw end                        as strata_residency,
           -- G1: Strata verdict at the alternative anchor
           case when sga.phn is null                                  then null
                when sga.is_placeholder = 1                           then 'NOT USED - placeholder address'
                when sga.classes_disagree_alt = 1                     then 'CONFLICT - active addresses disagree'   -- REV 2.8
                else sga.class_raw end                                  as strata_residency_alt,
           sh.postal_norm                                      as strata_historical_postal_code,
           sh.years_before_demand                              as strata_historical_years_before_demand,
           -- EPIC (sensitivity only; never in residency_final or cohort)
           ep.line1                                            as epic_address_at_demand,
           ep.city                                             as epic_city_at_demand,
           ep.postal_norm                                      as epic_zip_at_demand,
           ep.eff_from                                         as epic_eff_start,
           ep.n_active                                         as epic_n_active_at_demand,
           ep.classes_disagree                                 as epic_classes_disagree,
           ep.occupancy_flag                                   as epic_occupancy_flag,              -- REV 2.9 audit only
           ep.building_occupancy_flag_qa                       as epic_building_occupancy_flag_qa,  -- REV 2.9 QA only
           ep.any_named_facility                               as epic_named_facility_candidate,    -- REV 2.9 flag only
           ep.max_building_concurrent_n                        as epic_building_concurrent_n_qa,
           ep.bldg_key                                         as epic_building_key_qa,
           ep.any_pobox                                        as epic_is_pobox,
           ep.any_placeholder                                  as epic_is_placeholder,
           ep.any_start_equals_source_max                      as epic_start_equals_source_max,
           ep.any_start_is_migration_date                      as epic_start_is_migration_date,
           ep.epic_residency,
           -- record validity: an impossible linkage can never take a cohort
           iff(x.death_dt is not null and x.death_dt < d.demand_dt, 0, 1)             as record_valid,
           iff(x.death_dt is not null and x.death_dt < d.demand_dt,
               'death date precedes demand event', null)                               as record_invalid_reason,
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
    left join pat_ids   pi  on pi.phn = d.phn                                              -- SQL14
    left join reg_demo  rg  on rg.phn = d.phn                                              -- SQL14
    left join origin_at_demand od on od.phn = d.phn                                        -- SQL14 (QA)
    left join origin_entry     oe on oe.phn = d.phn                                        -- SQL14
    left join (select phn, min_by(source_location, admission_date) as source_location      -- SQL14: first reporting-scope admission
               from adm_rep group by phn) fa_src on fa_src.phn = d.phn
    left join requested rq  on rq.phn = d.phn                                              -- SQL14
    cross join w
    left join residency  r  on r.phn  = d.phn
    left join outcome    o  on o.phn  = d.phn
    left join first_site fs on fs.phn = d.phn
    left join level3_after l3 on l3.phn = d.phn
    left join deaths     x  on x.phn  = d.phn
    left join strata_geo sg on sg.phn = d.phn
    left join pc_comm pcr on pcr.postal_raw  = r.registry_postal_latest                    -- SQL14 community (registry key, raw as in geo)
    left join pc_comm pcs on pcs.postal_norm = sg.postal_norm                              -- SQL14 community (Strata key, normalised)
    left join strata_at_demand_alt sga on sga.phn = d.phn
    left join strata_historical sh on sh.phn = d.phn
    left join epic_at_demand ep on ep.phn = d.phn
),
-- ── G1 — OUTCOME AT THE ALTERNATIVE ANCHOR ─────────────────────────────────
outcome_alt as (
    select d.phn,
           min(iff(a.admission_date <= w.follow_up_end, a.admission_date, null)) as first_placement_dt_alt
    from demand_in_window d cross join w
    left join adm_rep a on a.phn = d.phn and a.admission_date >= d.demand_dt_alt
    group by d.phn
),
first_site_alt as (
    select o.phn, a.in_cochrane as first_placement_in_cochrane_alt
    from outcome_alt o join adm_rep a on a.phn = o.phn and a.admission_date = o.first_placement_dt_alt
    qualify row_number() over (partition by o.phn order by a.in_cochrane desc, a.site) = 1
),

-- ── STEP 7b — FINAL RESIDENCY HIERARCHY (rule 7) ───────────────────────────
master_final as (
    select m.*,
           case when m.residency_latest <> 'UNRESOLVED'                          then 'REGISTRY'
                when m.strata_residency in ('Town of Cochrane','Cochrane catchment',
                                            'Not a Cochrane-area resident')      then 'STRATA_ADDRESS_H'
                else 'UNRESOLVED' end                                           as residency_source,
           case when m.residency_latest <> 'UNRESOLVED'                          then m.residency_latest
                when m.strata_residency in ('Town of Cochrane','Cochrane catchment',
                                            'Not a Cochrane-area resident')      then m.strata_residency
                else 'UNRESOLVED' end                                           as residency_final,
           -- SQL14: community of residence from the SAME address that decided residency_final
           case when m.residency_latest <> 'UNRESOLVED'                          then m.registry_postal_latest
                when m.strata_residency in ('Town of Cochrane','Cochrane catchment',
                                            'Not a Cochrane-area resident')      then m.strata_postal_code_at_demand
                else null end                                                   as residence_postal_code_at_demand,
           case when m.residency_latest <> 'UNRESOLVED'                          then m.registry_community_latest
                when m.strata_residency in ('Town of Cochrane','Cochrane catchment',
                                            'Not a Cochrane-area resident')      then m.strata_community_at_demand
                else null end                                                   as residence_community_at_demand,
           case when m.residency_latest <> 'UNRESOLVED'                          then m.registry_local_name_latest
                when m.strata_residency in ('Town of Cochrane','Cochrane catchment',
                                            'Not a Cochrane-area resident')      then m.strata_local_name_at_demand
                else null end                                                   as residence_local_name_at_demand,
           -- EPIC SENSITIVITY: registry -> Strata -> Epic. Not the production rule.
           case when m.residency_latest <> 'UNRESOLVED'                          then m.residency_latest
                when m.strata_residency in ('Town of Cochrane','Cochrane catchment',
                                            'Not a Cochrane-area resident')      then m.strata_residency
                when m.epic_residency in ('Town of Cochrane','Cochrane catchment',
                                          'Not a Cochrane-area resident')        then m.epic_residency
                else 'UNRESOLVED' end                                           as residency_final_epic_sens,
           -- G1: the same hierarchy at the alternative anchor
           case when m.residency_latest_alt <> 'UNRESOLVED'                      then m.residency_latest_alt
                when m.strata_residency_alt in ('Town of Cochrane','Cochrane catchment',
                                                'Not a Cochrane-area resident')  then m.strata_residency_alt
                else 'UNRESOLVED' end                                           as residency_final_alt
    from master m
),
classified as (
    select m.*,
           oa.first_placement_dt_alt, fa.first_placement_in_cochrane_alt,
           -- G1: cohort at the alternative anchor, same rule, gated on in_window_alt
           case when m.in_window_alt = 0 or m.was_approved = 0 or m.record_valid = 0 then null
                when m.residency_final_alt = 'Town of Cochrane' and fa.first_placement_in_cochrane_alt = 1 then 'A'
                when m.residency_final_alt in ('Not a Cochrane-area resident','Cochrane catchment')
                     and fa.first_placement_in_cochrane_alt = 1                                          then 'B'
                when m.residency_final_alt = 'Town of Cochrane' and oa.first_placement_dt_alt is not null  then 'C'
                when m.residency_final_alt = 'Town of Cochrane' and oa.first_placement_dt_alt is null      then 'D'
                else null end as cohort_alt,
           -- PRIMARY: residency_final = registry latest address, else Strata
           -- address active at demand (rev 2.5). B = any NON-TOWN resident.
           -- Gated on in_window (G1: the universe now also holds alt-only people).
           case when in_window = 0 or was_approved = 0 or record_valid = 0 then null
                when residency_final = 'Town of Cochrane' and first_placement_in_cochrane = 1 then 'A'
                when residency_final in ('Not a Cochrane-area resident','Cochrane catchment')
                     and first_placement_in_cochrane = 1                                   then 'B'
                when residency_final = 'Town of Cochrane' and placed = 1                    then 'C'
                when residency_final = 'Town of Cochrane' and placed = 0                    then 'D'
                else null end as cohort,
           -- EPIC SENSITIVITY cohort. Not the headline.
           case when in_window = 0 or was_approved = 0 or record_valid = 0 then null
                when residency_final_epic_sens = 'Town of Cochrane' and first_placement_in_cochrane = 1 then 'A'
                when residency_final_epic_sens in ('Not a Cochrane-area resident','Cochrane catchment')
                     and first_placement_in_cochrane = 1                                          then 'B'
                when residency_final_epic_sens = 'Town of Cochrane' and placed = 1                 then 'C'
                when residency_final_epic_sens = 'Town of Cochrane' and placed = 0                 then 'D'
                else null end as cohort_epic_sens,
           -- the same rule on registry alone, so Strata's effect is visible
           case when in_window = 0 or was_approved = 0 or record_valid = 0 then null
                when residency_latest = 'Town of Cochrane' and first_placement_in_cochrane = 1 then 'A'
                when residency_latest in ('Not a Cochrane-area resident','Cochrane catchment')
                     and first_placement_in_cochrane = 1                                    then 'B'
                when residency_latest = 'Town of Cochrane' and placed = 1                   then 'C'
                when residency_latest = 'Town of Cochrane' and placed = 0                   then 'D'
                else null end as cohort_registry_only,
           iff(residency_final = 'Cochrane catchment' and first_placement_in_cochrane = 1
               and was_approved = 1 and record_valid = 1, 1, 0)                          as b_catchment,
           iff(residency_final = 'UNRESOLVED' and first_placement_in_cochrane = 1
               and was_approved = 1 and record_valid = 1, 1, 0)                          as cochrane_placement_residency_unresolved,
           -- SENSITIVITY: the published any-address-in-three-years rule
           case when in_window = 0 or was_approved = 0 or record_valid = 0 then null
                when residency_any3 = 'Town of Cochrane' and first_placement_in_cochrane = 1 then 'A'
                when residency_any3 in ('Not a Cochrane-area resident','Cochrane catchment')
                     and first_placement_in_cochrane = 1                                  then 'B'
                when residency_any3 = 'Town of Cochrane' and placed = 1                   then 'C'
                when residency_any3 = 'Town of Cochrane' and placed = 0                   then 'D'
                else null end as cohort_any3,
           -- presentation subset; NOT a filter on the audit universe
           iff(residency_final    in ('Town of Cochrane','Cochrane catchment')
            or residency_latest   in ('Town of Cochrane','Cochrane catchment')
            or residency_any3     in ('Town of Cochrane','Cochrane catchment')
            or residency_fallback in ('Town of Cochrane','Cochrane catchment')
            or first_placement_in_cochrane = 1
            or residency_final = 'UNRESOLVED', 1, 0) as cochrane_facing
    from master_final m
    left join outcome_alt oa on oa.phn = m.phn
    left join first_site_alt fa on fa.phn = m.phn
)

-- OUTPUT — ACTIVITY PEOPLE. One row per person with any Type A/B waitlist
-- spell or Cochrane-site admission in FY2022-FY2026 who is a Town/catchment
-- resident (at the activity anchor), was rated for a Cochrane/Hawthorne site,
-- or was admitted to a Cochrane site. No cohort columns: A/B/C/D belong to
-- the incident-demand extract (sql/14) only.
select
    phn, patient_id, patient_id_all, n_patient_ids, phn_patient_id_multiplicity,
    demand_dt as activity_anchor_dt, demand_fye as activity_anchor_fye,
    iff(demand_event_type = 'approval', 'first waitlist appearance in window', 'first Cochrane-site admission in window') as activity_anchor_type,
    first_list_appearance, first_approval_dt, last_seen_on_list, on_list_at_followup, left_truncated, rated_cochrane,
    first_residential_ever, first_residential_stream,     -- prior residential care, for the carry-in / prior-demand label
    dob, sex, demographic_source, dob_strata, dob_registry, dob_sources_agree, sex_conflict_registry,
    residency_final, residency_source, residency_evidence,
    residence_postal_code_at_demand as residence_postal_code_at_anchor,
    residence_community_at_demand   as residence_community_at_anchor,
    residence_local_name_at_demand  as residence_local_name_at_anchor,
    latest_window_fye as residence_reference_fye, strata_effective_from as strata_address_effective_from, strata_city_at_demand as strata_city_at_anchor,
    strata_address_is_placeholder, strata_residency,
    origin_setting_raw, origin_source, origin_entry_census_date, n_origin_locations_at_entry, origin_location_list, origin_conflict_flag,
    most_frequently_observed_rated_site, requested_care_stream, n_sites_requested, requested_cochrane_flag, requested_cochrane_sites,
    death_dt
from classified
where residency_final in ('Town of Cochrane', 'Cochrane catchment')
   or requested_cochrane_flag = 1
   or phn in (select phn from coch_adm_first)
order by demand_dt
;
