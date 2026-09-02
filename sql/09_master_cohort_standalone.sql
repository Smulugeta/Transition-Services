-- ============================================================================
-- MASTER DEMAND COHORT — A / B / C / D — STANDALONE, ONE ROW PER PERSON
-- Revision 2.7: Epic PAT_ADDR_CHNG_HX carried as SENSITIVITY ONLY. Paste-and-run.
-- Feed the CSV to analysis/07_master_cohort_check.py.
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
--   5. "Province-wide" is WITHDRAWN — CONFIRMED by 10_coverage_checks: the
--      source is the Calgary and Edmonton Strata instances (936 sites,
--      294,659 admissions) with 7 vestigial sites and 204 admissions in the
--      other three zones. A Town of Cochrane resident placed in Central zone
--      is invisible here and lands in D3. Every D figure carries "in the
--      Calgary and Edmonton Strata instances"; D3 is an upper bound. See
--      reference/coverage_check_results.md.
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
--
-- REV 2.3 — THIRD REVIEW
--   · The cohort is named: NEW TYPE A/B DEMAND ARISING FY2022-FY2026. It is
--     not "placement activity FY2022-26"; that is the capacity analysis in
--     query 01 and stays separate.
--   · Residency PRIMARY = latest mapped address in the three-year lookback
--     (residency_latest). The published any-address-in-three-years rule is
--     carried as SENSITIVITY (residency_any3, cohort_any3).
--   · Already-in-care is tested against the DEMAND EVENT, not the window
--     start: first_residential_ever < demand_dt excludes. A person in Level 3
--     since 2022 who is approved for Type A in 2024 is a transfer, not new
--     demand.
--   · NO OUTPUT FILTER. The full audit universe is returned; cochrane_facing
--     marks the presentation subset. Rev 2.2 dropped unresolved-residency
--     people unless they had requested Cochrane. That is the request-based
--     selection rule rejected for D itself, and the data rejects it here too:
--     only 53% of known Town demand ever recorded a Cochrane request.
--   · Unresolved residency is RESOLVED FURTHER, not filtered: residency_fallback
--     is the latest mapped address before the demand event at ANY distance,
--     with fallback_years_before_demand saying how stale it is. People with no
--     registry record at all cannot be resolved and stay UNRESOLVED; the
--     checker reports them as the mathematical maximum on D.
--
-- REV 2.4 — FOURTH REVIEW
--   · PHN validity. An identifier that normalises to all zeros, or to
--     anything other than nine digits, is rejected in BOTH the patient and
--     the waitlist path. The first run carried PHN 000000000 linked to a
--     1999 death and a 2024 demand event.
--   · Death before demand. A death date earlier than the demand event is an
--     impossible linkage (2 people in the first run). The row stays in the
--     audit universe with record_valid = 0 and a reason, and can never take
--     a cohort. The checker requires zero such rows inside A-D.
--   · confidence renamed registry_history_depth: it measures how many years
--     of registry history exist, not confidence in residency at demand. 71
--     UNRESOLVED people were labelled HIGH. A real residency_evidence column
--     is added: STRONG = mapped address in the year before demand;
--     MODERATE = mapped address in the lookback but not that year; NONE.
--   · Cohort B = NON-TOWN resident placed in Cochrane, so A + B is every
--     Cochrane placement with known residency. Cochrane-catchment residents
--     (6 in the first run) are therefore B, flagged b_catchment = 1 so they
--     can be shown separately. Unresolved-residency Cochrane placements (9)
--     are their own category, never A or B. Reviewer recommendation; one
--     line to reverse.
--   · residency_fallback is HISTORICAL EVIDENCE ONLY. Its addresses are 4-31
--     years old (median 16). It does not remove anyone from the residency
--     uncertainty around D; the maximum is primary D plus every valid
--     unresolved approved-unplaced person.
--
-- REV 2.7 — EPIC / CONNECT CARE ADDRESS HISTORY, SENSITIVITY ONLY
--   Epic is NOT in the production hierarchy. residency_final and cohort are
--   unchanged from rev 2.6. Epic feeds only epic_* and cohort_epic_sens, so
--   the checker can run the source validation (sql/12) checks 3-11 and the
--   control case against the cohort's real demand dates.
--   · PHN = identity_id where identity_type_id = '221', digit-validated.
--   · Rows active on the demand date: eff_start_date <= demand_dt and
--     (eff_end_date > demand_dt or null). epic_n_active_at_demand counts them.
--   · If the active rows DISAGREE on Town / catchment / non-Town the verdict
--     is 'CONFLICT' and nothing is chosen (reviewer instruction 5).
--   · ZIP_HX through the same postal geography; never CITY_HX.
--   · Facility = concurrent occupancy >= facility_min_patients; PO Box and
--     placeholder rows are never classified.
--   · epic_start_equals_source_max flags a row whose start date is the
--     source-wide maximum - the load-date signature seen in the sample.
--
-- REV 2.6 — SEVEN SIGN-OFF GATES
--   G1 APPROVAL PRECEDENCE. Two demand anchors are carried side by side:
--      demand_dt      = min over rows of coalesce(assess, calculated)   (current)
--      demand_dt_alt  = coalesce(min(assess), min(calculated)) per person
--      The universe admits anyone in the window under EITHER anchor, with
--      in_window / in_window_alt flags. Residency, Strata and the cohort are
--      computed at BOTH anchors (…_alt columns) so the checker can report the
--      exact impact. On a 792-person extract the alt anchor moved 1% of dates,
--      never earlier.
--   G2 ACTIVE ADDRESSES AT DEMAND. strata_n_active_at_demand counts Strata
--      versions active on the demand date; strata_active_classes_disagree says
--      whether they map to different Town / catchment / non-Town classes, i.e.
--      whether the latest-effective_from tiebreak could matter.
--   G4 FACILITY GUARD IS NOW CONCURRENT OCCUPANCY. "Ever shared by 3+" over
--      decades of address history blocked apartment units with three
--      successive tenants (403-18 Hebert Road, 353-5149 Mullen Road). A
--      facility is now an address with facility_min_patients or more DISTINCT
--      PEOPLE HOLDING IT ON THE SAME DAY (the demand date). Placeholder
--      strings (NO FIXED ADDRESS, NWT EVACUEE, UNKNOWN …) are a separate
--      class and never classified. A facility reference table would be
--      better than any threshold; query 11 block E lists candidates for one.
--   G5 RAW PHN VALIDATION BEFORE LPAD. Snowflake LPAD(x, 9) TRUNCATES a
--      string longer than 9 — a 10-digit identifier silently became its first
--      nine digits. Digits are counted first; only exactly-9-digit
--      identifiers are accepted, in the patient, waitlist and death paths.
--   G6 Registry fallback stays historical evidence only.  G7 B = non-Town.
--
-- REV 2.5 — STRATA address_h AS A SECONDARY RESIDENCY SOURCE
-- Rules as specified, with three additions the data forced:
--   1. Registry is primary and is never overwritten.
--   2. Strata is consulted ONLY where residency_latest = 'UNRESOLVED'.
--   3. The Strata address used is the one EFFECTIVE ON demand_dt
--      (effective_from <= demand_dt and (effective_to > demand_dt or null)).
--   4. Several active -> latest effective_from wins; ties broken by postal code.
--   5. Residency comes from the SAME postal geography as the registry, never
--      from city_name. ADDITION: a postal code that is not in the Alberta
--      geography and does not start with T is out of province and is
--      classified 'Not a Cochrane-area resident'; an unmapped T-code stays
--      UNRESOLVED (lookup failed). The reviewer's own example (V3Z 9T1,
--      Surrey BC) can only resolve this way.
--   6-7. Outputs and hierarchy below; residency_source in
--        ('REGISTRY','STRATA_ADDRESS_H','UNRESOLVED').
--   8. No address effective after demand_dt is ever used.
--   9. If nothing is active at demand but an older Strata address exists, it
--      is reported as strata_historical_* with its staleness, not classified.
--   ADDITION A — JOIN THROUGH patient_h, NOT patient. Every distinct
--      (patient, address_id) pair is used, so a move that created a new
--      address record is not lost behind the current pointer. patient_h is
--      versioned by service_provider_id and must be reduced to DISTINCT first
--      or every address version arrives four times. See query 11.
--   ADDITION B — FACILITY GUARD. 32 Quigley Dr (the Bethany Cochrane campus)
--      appears in address_h as a residence. An address version shared by
--      facility_min_patients or more distinct patients is treated as a
--      facility and is NOT used to classify residency (a Cochrane facility
--      would otherwise manufacture Town residents - the exact contamination
--      the registry method exists to avoid). Reported, not silently dropped.
--   ADDITION C — effective_from_date often equals patient_h.creation_date
--      (the patient record was created that day). Flagged as
--      strata_from_equals_creation so the checker can say how many Strata
--      resolutions rest on a record-creation date rather than a move-in date.
--      creation_date is NOT an address_h column.
--   Cohorts are computed on residency_final; cohort_registry_only is kept so
--   the change attributable to Strata is visible.
--
-- LEFT-TRUNCATION, AFTER THE FIRST RUN: with approval as the demand event, a
-- person approved before 2021-04-01 has a demand event outside the window and
-- is EXCLUDED, not flagged. The flag therefore marks almost nobody (1 person
-- in the first run). The exclusion is the temporal-alignment fix working: A/C
-- and D are both selected on demand arising inside the window. It is also why
-- the master A/C are smaller than the published A/C - see the reconciliation.
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
    select 3                  as facility_min_patients,   -- ADDITION B threshold
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
           iff(a.source_location is null, 1, 0) as null_source
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
demand as (
    select coalesce(l.phn, a.phn)                                          as phn,
           least(coalesce(l.first_approval_dt, '9999-12-31'::date),
                 coalesce(a.first_rep_adm,     '9999-12-31'::date))         as demand_dt,
           least(coalesce(l.first_approval_dt_alt, '9999-12-31'::date),
                 coalesce(a.first_rep_adm,         '9999-12-31'::date))     as demand_dt_alt,     -- G1
           l.first_approval_dt_alt,
           iff(l.first_approval_dt is not null
               and (a.first_rep_adm is null or l.first_approval_dt <= a.first_rep_adm),
               'approval', 'admission')                                    as demand_event_type,
           iff(l.first_approval_dt is not null or a.first_rep_adm is not null, 1, 0) as was_approved,
           l.first_list_appearance, l.first_approval_dt, l.setting_at_list_entry,
           l.last_seen_on_list, coalesce(l.on_list_at_followup,0) as on_list_at_followup,
           coalesce(l.left_truncated, 0)                                    as left_truncated,
           coalesce(l.rated_cochrane, 0)                                    as rated_cochrane,
           h.first_residential_ever, h.first_residential_stream
    from first_list l
    full outer join (select phn, min(admission_date) as first_rep_adm from adm_rep group by phn) a
           on a.phn = l.phn
    left join first_ever_residential h on h.phn = coalesce(l.phn, a.phn)
    cross join w
    where h.first_residential_ever is null or h.first_residential_ever >= w.win_start
    -- (the stricter test against the demand event itself is in demand_in_window)
),
demand_in_window as (
    select d.*,
           iff(month(d.demand_dt) >= 4, year(d.demand_dt) + 1, year(d.demand_dt))         as demand_fye,
           iff(month(d.demand_dt_alt) >= 4, year(d.demand_dt_alt) + 1, year(d.demand_dt_alt)) as demand_fye_alt,
           -- G1: membership under each anchor. The universe admits EITHER.
           iff(d.demand_dt >= w.win_start and d.demand_dt < w.win_end
               and (d.first_residential_ever is null or d.first_residential_ever >= d.demand_dt), 1, 0) as in_window,
           iff(d.demand_dt_alt >= w.win_start and d.demand_dt_alt < w.win_end
               and (d.first_residential_ever is null or d.first_residential_ever >= d.demand_dt_alt), 1, 0) as in_window_alt
    from demand d cross join w
    -- ALREADY IN RESIDENTIAL CARE WHEN THE DEMAND EVENT HAPPENED is inside
    -- each in_window flag (rev 2.3 rule, tested against the demand event).
    qualify in_window = 1 or in_window_alt = 1
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
    select d.phn, d.demand_fye, d.demand_fye_alt, g.fye, g.postal_cd, g.mapped, g.in_town, g.in_area,
           iff(g.fye between d.demand_fye-3 and d.demand_fye-1, 1, 0)         as in_window,
           iff(g.fye <= d.demand_fye-1, 1, 0)                                  as pre_demand,
           iff(g.fye between d.demand_fye_alt-3 and d.demand_fye_alt-1, 1, 0) as in_window_alt   -- G1
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
           max(iff(in_window=1 and mapped=1, fye, null))                as latest_window_fye,
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
-- ever-shared count kept for reporting only (was the guard before rev 2.6)
strata_shared as (
    select upper(street_address) as street_u, postal_norm, count(distinct phn) as n_patients
    from strata_addr group by 1,2
),
-- G4: placeholder strings are never an address
strata_placeholder (pat) as (
    select * from values ('%NO FIXED%'),('%NFA%'),('%EVACUEE%'),('%UNKNOWN%'),('%HOMELESS%'),('%SHELTER%'),('%TRANSIENT%')
),
-- all versions ACTIVE on the demand date (rules 3, 8), one row per version
strata_active as (
    select d.phn, d.demand_dt, a.street_address, a.city_name, a.postal_norm, a.eff_from, a.eff_to, a.created,
           iff(exists (select 1 from strata_placeholder sp where upper(a.street_address) like sp.pat), 1, 0) as is_placeholder,
           -- G4: distinct people holding THIS address on THIS day
           (select count(distinct b.phn) from strata_addr b
             where upper(b.street_address) = upper(a.street_address) and b.postal_norm = a.postal_norm
               and b.eff_from <= d.demand_dt and (b.eff_to > d.demand_dt or b.eff_to is null)) as concurrent_n,
           pc.postalcode is not null                                  as mapped,
           case when pc.postalcode is not null and upper(trim(pc.csdname_2021)) = 'COCHRANE'
                     and upper(trim(pc.csdtype_2021)) = 'T'          then 'Town of Cochrane'
                when pc.postalcode is not null
                     and upper(trim(pc.local_name)) = 'COCHRANE | SPRINGBANK' then 'Cochrane catchment'
                when pc.postalcode is not null                       then 'Not a Cochrane-area resident'
                when a.postal_norm is not null and left(a.postal_norm,1) <> 'T'
                                                                     then 'Not a Cochrane-area resident'
                else 'UNRESOLVED' end                                 as class_raw
    from demand_in_window d
    join strata_addr a on a.phn = d.phn
                      and a.eff_from <= d.demand_dt
                      and (a.eff_to > d.demand_dt or a.eff_to is null)
    left join db_source_ah_postal_code.curated.tb_postal_code pc
           on upper(regexp_replace(pc.postalcode, '[^A-Za-z0-9]', '')) = a.postal_norm
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
strata_at_demand_alt as (
    select d.phn, a.postal_norm, a.street_address,
           iff(exists (select 1 from strata_placeholder sp where upper(a.street_address) like sp.pat), 1, 0) as is_placeholder,
           (select count(distinct b.phn) from strata_addr b
             where upper(b.street_address) = upper(a.street_address) and b.postal_norm = a.postal_norm
               and b.eff_from <= d.demand_dt_alt and (b.eff_to > d.demand_dt_alt or b.eff_to is null)) as concurrent_n,
           case when pc.postalcode is not null and upper(trim(pc.csdname_2021)) = 'COCHRANE'
                     and upper(trim(pc.csdtype_2021)) = 'T'          then 'Town of Cochrane'
                when pc.postalcode is not null
                     and upper(trim(pc.local_name)) = 'COCHRANE | SPRINGBANK' then 'Cochrane catchment'
                when pc.postalcode is not null                       then 'Not a Cochrane-area resident'
                when a.postal_norm is not null and left(a.postal_norm,1) <> 'T'
                                                                     then 'Not a Cochrane-area resident'
                else 'UNRESOLVED' end                                 as class_raw
    from demand_in_window d
    join strata_addr a on a.phn = d.phn
                      and a.eff_from <= d.demand_dt_alt
                      and (a.eff_to > d.demand_dt_alt or a.eff_to is null)
    left join db_source_ah_postal_code.curated.tb_postal_code pc
           on upper(regexp_replace(pc.postalcode, '[^A-Za-z0-9]', '')) = a.postal_norm
    qualify row_number() over (partition by d.phn order by a.eff_from desc, a.postal_norm) = 1
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
           iff(exists (select 1 from strata_placeholder sp where upper(a.addr_hx_line1) like sp.pat), 1, 0) as is_placeholder
    from db_source_epic_clarity.raw.pat_addr_chng_hx a
    join epic_phn e on e.pat_id = a.pat_id
    where a.addr_hx_line1 is not null or a.zip_hx is not null
),
epic_active as (
    select d.phn, d.demand_dt, a.line1, a.city, a.postal_norm, a.eff_from, a.eff_to, a.is_pobox, a.is_placeholder,
           iff(a.eff_from = m.max_start, 1, 0)                     as start_equals_source_max,
           (select count(distinct b.phn) from epic_addr b
             where upper(b.line1) = upper(a.line1) and b.postal_norm = a.postal_norm
               and b.eff_from <= d.demand_dt and (b.eff_to > d.demand_dt or b.eff_to is null)) as concurrent_n,
           case when pc.postalcode is not null and upper(trim(pc.csdname_2021)) = 'COCHRANE'
                     and upper(trim(pc.csdtype_2021)) = 'T'          then 'Town of Cochrane'
                when pc.postalcode is not null
                     and upper(trim(pc.local_name)) = 'COCHRANE | SPRINGBANK' then 'Cochrane catchment'
                when pc.postalcode is not null                       then 'Not a Cochrane-area resident'
                when a.postal_norm is not null and left(a.postal_norm,1) <> 'T'
                                                                     then 'Not a Cochrane-area resident'
                else 'UNRESOLVED' end                                 as class_raw
    from demand_in_window d
    join epic_addr a on a.phn = d.phn
                    and a.eff_from <= d.demand_dt
                    and (a.eff_to > d.demand_dt or a.eff_to is null)
    cross join epic_src_max m
    left join db_source_ah_postal_code.curated.tb_postal_code pc
           on upper(regexp_replace(pc.postalcode,'[^A-Za-z0-9]','')) = a.postal_norm
),
epic_summary as (
    select phn,
           count(*)                                                as n_active,
           count(distinct class_raw)                               as n_classes,
           iff(count(distinct class_raw) > 1, 1, 0)                as classes_disagree,
           max(is_pobox) as any_pobox, max(is_placeholder) as any_placeholder,
           max(iff(concurrent_n >= (select facility_min_patients from w), 1, 0)) as any_facility,
           max(start_equals_source_max)                            as any_start_equals_source_max,
           min(class_raw)                                          as class_if_unanimous
    from epic_active group by phn
),
epic_at_demand as (
    select ea.*, es.n_active, es.classes_disagree, es.any_pobox, es.any_placeholder, es.any_facility,
           es.any_start_equals_source_max,
           -- reviewer instruction 5: never choose between conflicting classes
           case when es.any_placeholder = 1 then 'NOT USED - placeholder address'
                when es.any_pobox = 1       then 'NOT USED - PO Box'
                when es.any_facility = 1    then 'NOT USED - facility address'
                when es.classes_disagree = 1 then 'CONFLICT - active addresses disagree'
                else es.class_if_unanimous end                       as epic_residency
    from epic_active ea join epic_summary es on es.phn = ea.phn
    qualify row_number() over (partition by ea.phn order by ea.eff_from desc, ea.postal_norm) = 1
),

-- rule 5 mapping is inside strata_active (same postal geography, never city_name)
strata_geo as (
    select s.*, s.class_raw as strata_residency_raw from strata_at_demand s
),

-- ── STEP 7 — ONE ROW PER PERSON ────────────────────────────────────────────
master as (
    select d.phn, d.demand_dt, d.demand_fye, d.demand_event_type, d.was_approved,
           d.demand_dt_alt, d.demand_fye_alt, d.first_approval_dt_alt, d.in_window, d.in_window_alt,   -- G1
           d.first_list_appearance, d.first_approval_dt, d.setting_at_list_entry,
           d.last_seen_on_list, d.on_list_at_followup, d.left_truncated, d.rated_cochrane,
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
           sg.concurrent_n                                     as strata_address_concurrent_n,      -- G4: people holding it that day
           iff(coalesce(sg.concurrent_n,0) >= w.facility_min_patients, 1, 0) as strata_address_is_facility,
           sg.is_placeholder                                   as strata_address_is_placeholder,    -- G4
           sg.from_equals_creation                             as strata_from_equals_creation,
           sg.n_active                                         as strata_n_active_at_demand,        -- G2
           sg.classes_disagree                                 as strata_active_classes_disagree,   -- G2
           case when sg.phn is null                                   then null
                when sg.is_placeholder = 1                            then 'NOT USED - placeholder address'
                when coalesce(sg.concurrent_n,0) >= w.facility_min_patients
                                                                      then 'NOT USED - facility address'
                else sg.strata_residency_raw end                        as strata_residency,
           -- G1: Strata verdict at the alternative anchor
           case when sga.phn is null                                  then null
                when sga.is_placeholder = 1                           then 'NOT USED - placeholder address'
                when coalesce(sga.concurrent_n,0) >= w.facility_min_patients
                                                                      then 'NOT USED - facility address'
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
           ep.any_facility                                     as epic_is_facility,
           ep.any_pobox                                        as epic_is_pobox,
           ep.any_placeholder                                  as epic_is_placeholder,
           ep.any_start_equals_source_max                      as epic_start_equals_source_max,
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
    cross join w
    left join residency  r  on r.phn  = d.phn
    left join outcome    o  on o.phn  = d.phn
    left join first_site fs on fs.phn = d.phn
    left join level3_after l3 on l3.phn = d.phn
    left join deaths     x  on x.phn  = d.phn
    left join strata_geo sg on sg.phn = d.phn
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

-- OUTPUT. Rev 2.3: NO FILTER. The full audit universe is returned. Everyone
-- confirmed non-resident under BOTH residency rules AND the fallback AND not
-- placed in Cochrane bears on nothing, so cochrane_facing = 0 for them; use
-- that flag for presentation, never as a WHERE clause on the QA extract.
select *
from classified
order by cohort nulls last, demand_dt
;
