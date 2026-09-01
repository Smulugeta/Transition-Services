-- ============================================================================
-- COCHRANE CONTINUING CARE — DEMAND, CAPACITY USE AND ACCESS
-- Cohorts A / A2 / B / C / C2 · Fiscal years 2022–2026 · Type A and Type B
-- ============================================================================
--
-- ─────────────────────────────────────────────────────────────────────────────
-- 1. THE QUESTION
-- ─────────────────────────────────────────────────────────────────────────────
-- How much continuing care demand does the Town of Cochrane generate, how much
-- of it is served locally, and who occupies Cochrane's beds?
--
-- Four populations answer it:
--
--                          placed IN Cochrane    placed OUTSIDE Cochrane
--   Cochrane resident              A                       C
--   non-resident                   B                  (out of scope)
--
--   A + C  = total Town demand           C / (A+C) = share that had to leave
--   A + B  = use of Cochrane capacity    A / (A+B) = share of beds going local
--
-- A2 and C2 are the same as A and C for residents of the Cochrane catchment
-- (Springbank, rural Rocky View) who live outside the Town boundary.
--
--
-- ─────────────────────────────────────────────────────────────────────────────
-- 2. WHY THE PROVINCIAL REGISTRY — THE CORE OF THE METHOD
-- ─────────────────────────────────────────────────────────────────────────────
-- This is the unconventional part, and everything else depends on it.
--
-- THE PROBLEM: the placement system (Strata) records where people were
-- ADMITTED. It does not reliably record where they LIVED. Three fields look
-- like they should answer "was this person from Cochrane" and none of them do:
--
--   source_location  — the facility they came FROM, not their home. Someone who
--                      went home → hospital → Calgary nursing home → Bethany
--                      Cochrane shows "Calgary nursing home".
--
--   address history  — updates to the FACILITY on admission. In this cohort,
--                      50 patient-address records point at the Bethany Cochrane
--                      campus itself. Reading those as "Cochrane residents"
--                      would make the destination facility manufacture its own
--                      demand. The same address also appears in 24 different
--                      spellings, so it cannot be matched reliably.
--
--   postal code      — recorded inconsistently and often stale.
--
-- THE INSIGHT: the provincial registry holds ONE ROW PER PERSON PER FISCAL
-- YEAR, with the postal code they lived at that year, going back to the 1990s.
-- It is a longitudinal record of where every Albertan lived, every year.
--
-- That lets us ask a question no placement system can answer:
--
--      "Where did this person live in the years BEFORE they entered care?"
--
-- Pre-care years cannot contain a facility address, because the person was not
-- yet in a facility. The contamination problem disappears — not by cleaning the
-- data, but by choosing a time window in which it cannot occur.
--
-- THE ANCHOR: for each person we find their FIRST-EVER Type A/B admission —
-- the moment they entered residential care — and read their registry address
-- for the three fiscal years BEFORE it. The entry year itself is excluded so
-- that a move into a facility mid-year cannot leak in.
--
-- WHY FIRST TYPE A/B, and not first contact of any kind: day programs (ADP) and
-- hospital transition units (RCTP) are not residential care. Anchoring on those
-- sits a median 1.6 years — and up to 6.6 years — before the person actually
-- needed a bed, and misclassifies anyone who moved into Cochrane in between.
-- Tested on this cohort: it changes 21% of anchors.
--
-- WHY THREE YEARS: matches ALA's own lookback cap. Empirically the window
-- length is immaterial here — 2-year and 5-year windows return the identical
-- set of people, so every window between them does too.
--
-- GEOGRAPHY: the registry gives a postal code; the postal reference table turns
-- it into a place. Two of its columns look usable and are not:
--   · MUNICIPALITY — 22 Rocky View County postal codes are labelled 'COCHRANE'
--     (4 of them are actually in the Canmore area).
--   · postal prefix — T4C splits 562 Town / 41 Rocky View County.
-- We use the Statistics Canada census subdivision (CSDNAME_2021='COCHRANE' with
-- CSDTYPE_2021='T') for the Town — 568 postal codes, an actual legal boundary —
-- and the AHS local geography ('COCHRANE | SPRINGBANK', 1,177 codes) for the
-- wider catchment.
--
-- LINKAGE: registry to placement records via PHN. In this system the PHN is
-- held in patient.identifier1, dash-formatted ('76700-5400' → '767005400').
-- Match rate on validation: 100%.
--
--
-- ─────────────────────────────────────────────────────────────────────────────
-- 3. TWO OTHER THINGS THAT WOULD OTHERWISE GO WRONG
-- ─────────────────────────────────────────────────────────────────────────────
-- TWO WAIT CLOCKS, NOT ONE. There are two distinct populations. A NEW PLACEMENT
-- is someone entering residential care for the first time; their clock runs from
-- assessment/approval. A TRANSFER is someone already in a facility moving to
-- another; their clock runs from enabled_for_transfer_date. Medians differ by an
-- order of magnitude (~21 vs ~324 days), so a blended figure describes nobody.
--   Trap: do NOT identify transfers by "assessed_approved_date is null".
--   Legacy pre-2024 records have that field backfilled to equal the admission
--   date exactly, which produces a fake 0-day wait on people whose real transfer
--   wait was around a year. Use enabled_for_transfer_date being populated.
--
-- PEOPLE vs EPISODES. One person can have several placements. DEMAND is counted
-- per person on their FIRST-EVER placement — "did the Town's need get met
-- locally the first time it arose". CAPACITY USE is counted per episode,
-- because each one consumes a bed. Person-level counts must never be summed
-- across years; the same individual recurs.
--
--
-- ─────────────────────────────────────────────────────────────────────────────
-- 4. WHAT THIS DOES NOT MEASURE
-- ─────────────────────────────────────────────────────────────────────────────
-- · People who never got a bed — still waiting, withdrawn, or died waiting.
--   Everything here is conditioned on placement. That is cohort D and needs the
--   waitlist source.
-- · Whether displaced residents WANTED a Cochrane bed. We can show the rank of
--   the site they received, not the identity of the sites they asked for.
-- · Which community they were placed into — only whether it was Cochrane.
--
-- Known bias direction: cohort C (residents placed elsewhere) is discovered only
-- through a registry address, so registry gaps can only UNDERSTATE displacement,
-- never inflate it. The reported figure is a floor.
--
--
-- ─────────────────────────────────────────────────────────────────────────────
-- 5. HOW THE QUERY IS BUILT
-- ─────────────────────────────────────────────────────────────────────────────
--   STEP 0  define what counts as a Cochrane facility and as Type A/B care
--   STEP 1  all Type A/B admissions in the window, province-wide
--   STEP 2  PHN for linkage
--   STEP 3  everyone who ever held a Cochrane-area address
--   STEP 4  scope = placed in Cochrane OR ever a Cochrane resident
--   STEP 5  the episodes to classify
--   STEP 6  each person's full care journey (needed to find the anchor)
--   STEP 7  the anchor: first-ever Type A/B admission
--   STEP 8  assemble: fiscal years, pathway, wait clock
--   STEP 9  registry geography, year by year
--   STEP 10 residency flags over the 3-year pre-care window
--   STEP 11 classify into cohorts
--   STEP 12 report blocks
--
--   Section 7 of the output carries integrity checks. Read them first.
-- ============================================================================

with

-- ── STEP 0a — WHAT COUNTS AS A COCHRANE FACILITY ────────────────────────────
-- An explicit list, never a text pattern. Two reasons this matters:
--   · 'CAL - Bethany Cochrane LTC_' ends in a literal underscore, which is a
--     wildcard in SQL LIKE — a pattern match would silently over- or under-match.
--   · 'CAL - Hawthorne SL4_' contains neither "Cochrane" nor "Bethany", so no
--     name pattern would ever find it. It is 61% of Cochrane's placement volume.
-- Cochrane's adult day programs are deliberately absent: attending a day program
-- is not a placement, and including them would inflate demand by ~11%.
coch_site (site_name) as (
    select * from values
        ('CAL - Bethany Cochrane LTC_'),      -- Type A, long-term care
        ('CAL - Hawthorne SL4_'),             -- Type B, supportive living
        ('CAL - Hawthorne SL4D')              -- Type B, supportive living dementia
),

-- ── STEP 0b — WHAT COUNTS AS TYPE A / TYPE B CARE ───────────────────────────
-- Confirmed against the full care_type vocabulary. "DAL" = Designated Assisted
-- Living, the pre-2024 name for Type B; the five-year window straddles that
-- renaming, so both namings appear. Edmonton zone uses its own labels for the
-- same care levels and is included because a Cochrane resident can be placed
-- anywhere in the province.
-- Level 3 is TAGGED here but EXCLUDED from the reported figures (see the
-- placement CTE at STEP 11). It is tagged rather than dropped outright because
-- the anchor at STEP 7 must still see it: if a person's first-ever residential
-- admission was level 3, that is genuinely when they entered residential care,
-- and dropping it here would misdate their residency window. Level 3 is out of
-- the reported scope because Cochrane has no level-3 capacity at all, so the
-- comparison "could they get a local bed" has no local bed to compare against.
-- It accounts for 3 Town residents across the five years.
scope_care_type (care_type, care_stream) as (
    select * from values
        ('CAL - Long Term Care',                           'Type A'),
        ('EDM - LTC',                                      'Type A'),
        ('CAL - Supportive Living Level 4 (DAL)',          'Type B'),
        ('CAL - Supportive Living Level 4 Dementia (DAL)', 'Type B'),
        ('EDM - DSL4 / DSL4D',                             'Type B'),
        ('CAL - Supportive Living Level 3 (PCH)',          'Type B - Level 3'),
        ('CAL - Supportive Living Level 3 (DEL)',          'Type B - Level 3'),
        ('EDM - DSL3',                                     'Type B - Level 3')
),

-- ── STEP 1 — ALL TYPE A/B ADMISSIONS IN THE WINDOW, PROVINCE-WIDE ───────────
-- Deliberately unfiltered by geography: a Cochrane resident could be placed
-- anywhere, and cohort C is exactly those people. STEP 4 narrows it.
-- Dates are half-open (>= start, < end). BETWEEN against a timestamp column
-- cuts off at midnight on the end date and silently loses that day.
cand_adm as (
    select a.*,
           trim(a.admission_location) as site,
           ct.care_stream
    from admissions a
    join scope_care_type ct on ct.care_type = trim(a.care_type)
    where a.admission_date >= '2021-04-01'
      and a.admission_date <  '2026-04-01'
),

-- ── STEP 2 — PHN, THE LINK TO THE REGISTRY ─────────────────────────────────
-- The PHN sits in patient.identifier1 in dash-formatted style ('76700-5400').
-- Strip non-digits and left-pad to 9 so a leading zero lost to numeric typing
-- still matches the registry side. Anyone with no usable identifier resolves to
-- null and is reported as UNRESOLVED rather than guessed at.
pat_key as (
    select p.id as patient_id,
           case when regexp_replace(p.identifier1::string,'[^0-9]','') = '' then null
                else lpad(regexp_replace(p.identifier1::string,'[^0-9]',''),9,'0')
           end as phn
    from patient p
    where p.id in (select distinct patient_id from cand_adm)
),

-- ── STEP 3 — EVERYONE WHO EVER HELD A COCHRANE-AREA ADDRESS ────────────────
-- Deliberately broad ("ever", and the wider catchment rather than the Town).
-- This CTE only decides WHO WE LOOK AT. The actual residency test is the
-- precise 3-year pre-care window at STEP 10. Casting a wide net here and
-- classifying narrowly later means nobody is lost before they can be assessed.
coch_phn as (
    select distinct lpad(r.phn::string,9,'0') as phn
    from db_source_ah_provincial_registry.curated.provincial_registry r
    join db_source_ah_postal_code.curated.tb_postal_code pc
      on pc.postalcode = r.postal_cd
    where upper(trim(pc.local_name)) = 'COCHRANE | SPRINGBANK'
),

-- ── STEP 4 — THE IN-SCOPE POPULATION ───────────────────────────────────────
-- Placed at a Cochrane facility  OR  ever a Cochrane-area resident.
-- Building both arms from one population is what guarantees cohort A is
-- computed once and is identical between the "placed here" and "placed
-- elsewhere" halves of the analysis, rather than derived twice and drifting.
in_scope as (
    select distinct a.patient_id
    from cand_adm a join coch_site s on s.site_name = a.site
    union
    select distinct k.patient_id
    from pat_key k join coch_phn c on c.phn = k.phn
),

-- ── STEP 5 — THE EPISODES TO CLASSIFY ──────────────────────────────────────
-- One row per in-scope Type A/B admission.
--   · Same-site moves are dropped: changing beds inside one facility is not an
--     admission and would double-count demand.
--   · Moves BETWEEN two Cochrane facilities are KEPT and flagged. Hawthorne →
--     Bethany is a genuine Type B → Type A progression — the campus-of-care
--     pathway working — but it is internal movement, not new demand on the
--     Town. from_cochrane_site separates the two so neither is lost.
episode as (
    select a.patient_id, a.admission_date, a.site, a.care_type, a.care_stream,
           a.source_location, a.assessed_approved_date, a.enabled_for_transfer_date,
           a.service_provider_rating,
           iff(s.site_name     is not null,1,0) as placed_in_cochrane,
           iff(s_src.site_name is not null,1,0) as from_cochrane_site,
           row_number() over (partition by a.patient_id
                              order by a.admission_date) as admission_seq
    from cand_adm a
    join      in_scope  i     on i.patient_id    = a.patient_id
    left join coch_site s     on s.site_name     = a.site
    left join coch_site s_src on s_src.site_name = trim(a.source_location)
    where trim(a.source_location) <> a.site
),

-- ── STEP 6 — THE FULL CARE JOURNEY ─────────────────────────────────────────
-- Every admission these people ever had, of every care type and any date.
-- Needed only to locate the anchor at STEP 7. Without it we would read the
-- sending facility as the person's origin: home → hospital → Calgary nursing
-- home → Bethany Cochrane would be recorded as coming from Calgary.
journey as (
    select a.* from admissions a
    where a.patient_id in (select distinct patient_id from episode)
),

-- ── STEP 7 — THE ANCHOR: FIRST-EVER TYPE A/B ADMISSION ─────────────────────
-- The single most important line in the query. This is the moment the person
-- entered residential care, and the residency window is measured backwards
-- from here.
--   · Restricted to Type A/B. Day programs and hospital transition units are
--     not residential care; anchoring on them sits a median 1.6 years (max 6.6)
--     too early and misses anyone who moved into Cochrane in the interval.
--   · Fixed ONCE per person, so residency never changes across their later
--     episodes. A person's origin does not change because they moved beds.
-- Also yields origin_setting: what kind of place they entered care from.
first_ab as (
    select j.patient_id,
           j.admission_date  as first_ab_dt,
           j.source_location as origin_setting
    from journey j
    join scope_care_type ct on ct.care_type = trim(j.care_type)
    qualify row_number() over (partition by j.patient_id
                               order by j.admission_date) = 1
),

-- ── STEP 8 — ASSEMBLE: FISCAL YEARS, PATHWAY, WAIT CLOCK ───────────────────
-- FYE = fiscal year ENDING 31 March, matching ALA's convention:
--   April–December → year + 1     January–March → year
--
-- pathway / wait_days: see the header. The pathway test is
-- "enabled_for_transfer_date is populated", NOT "assessed_approved_date is
-- null" — legacy records have the approval date backfilled to equal the
-- admission date, producing a fake 0-day wait on year-long transfer waits.
-- Both clocks are truncated to whole days so timestamp arithmetic doesn't shift
-- every figure by up to a day.
--
-- is_true_first marks people whose first-ever residential placement falls
-- inside the window. Those already in care beforehand are excluded from DEMAND
-- (their in-window episode is a later placement, not a first one) but retained
-- for CAPACITY USE, because they still occupy a bed.
base as (
    select e.*, k.phn, f.first_ab_dt, f.origin_setting,
           iff(month(e.admission_date)>=4,
               year(e.admission_date)+1, year(e.admission_date))          as adm_fye,
           iff(month(f.first_ab_dt)>=4,
               year(f.first_ab_dt)+1,    year(f.first_ab_dt))             as first_ab_fye,
           iff(e.enabled_for_transfer_date is not null,
               'TRANSFER','NEW PLACEMENT')                                as pathway,
           iff(e.enabled_for_transfer_date is not null,
               datediff('day', e.enabled_for_transfer_date::date, e.admission_date::date),
               datediff('day', e.assessed_approved_date::date,    e.admission_date::date)
           )                                                              as wait_days,
           iff(f.first_ab_dt >= '2021-04-01', 1, 0)                       as is_true_first
    from episode e
    join      first_ab f on f.patient_id = e.patient_id
    left join pat_key  k on k.patient_id = e.patient_id
),

-- ── STEP 9 — REGISTRY GEOGRAPHY, YEAR BY YEAR ──────────────────────────────
-- One row per person per fiscal year, resolved to two geographies.
--   in_town : Statistics Canada census subdivision — the legal Town boundary.
--             568 postal codes. This is the scope Cochrane asked for.
--   in_area : AHS local geography — Town plus Springbank and rural Rocky View.
--             1,177 postal codes. The catchment the campus actually serves.
-- MUNICIPALITY is not used: 22 Rocky View County postal codes carry
-- MUNICIPALITY='COCHRANE', four of which AHS assigns to Canmore. Postal prefix
-- is not used either: T4C splits 562 Town / 41 Rocky View County.
reg as (
    select lpad(r.phn::string,9,'0') as phn,
           r.fye,
           iff(upper(trim(pc.csdname_2021))='COCHRANE'
               and upper(trim(pc.csdtype_2021))='T',1,0)               as in_town,
           iff(upper(trim(pc.local_name))='COCHRANE | SPRINGBANK',1,0) as in_area
    from db_source_ah_provincial_registry.curated.provincial_registry r
    join db_source_ah_postal_code.curated.tb_postal_code pc
      on pc.postalcode = r.postal_cd
    where lpad(r.phn::string,9,'0') in (select phn from base where phn is not null)
),

-- ── STEP 10 — THE RESIDENCY TEST ───────────────────────────────────────────
-- Did this person live in Cochrane in the three fiscal years BEFORE they
-- entered residential care? The entry year itself is excluded, so a move into
-- a facility partway through that year cannot leak into the answer.
-- lookback_covered records whether the registry observed them at all during
-- those years — a "not from Cochrane" verdict built on no observation is not
-- the same as one built on thirty years of history, and the output says which.
residency as (
    select b.patient_id,
        max(iff(g.in_town=1
                and g.fye between b.first_ab_fye-3 and b.first_ab_fye-1,1,0)) as town_3yr,
        max(iff(g.in_area=1
                and g.fye between b.first_ab_fye-3 and b.first_ab_fye-1,1,0)) as area_3yr,
        max(iff(g.fye between b.first_ab_fye-3 and b.first_ab_fye-1,1,0))     as lookback_covered,
        count(distinct g.fye)                                                 as n_registry_fye
    from base b
    left join reg g on g.phn = b.phn
    group by b.patient_id
),

-- ── STEP 11 — CLASSIFY ─────────────────────────────────────────────────────
-- residency is person-level and fixed; placed_in_cochrane is per episode.
-- Together they give the cohort grid from the header.
-- UNRESOLVED is a genuine third state, never folded into a resident/non-
-- resident bucket: doing so would push unknowns in whichever direction the
-- missing data happened to fall.
-- The final WHERE drops non-residents placed outside Cochrane — they bear on
-- neither Cochrane demand nor Cochrane capacity.
ep as (
    select b.*, r.town_3yr, r.area_3yr, r.n_registry_fye, r.lookback_covered,
        case when b.phn is null or r.n_registry_fye = 0 then 'UNRESOLVED'
             when r.town_3yr = 1                        then 'Town of Cochrane'
             when r.area_3yr = 1                        then 'Cochrane area'
             else                                            'Non-resident' end as residency,
        case when r.lookback_covered = 0 then 'LOW'
             when r.n_registry_fye >= 10 then 'HIGH'
             when r.n_registry_fye >=  5 then 'MEDIUM'
             else                             'LOW' end as confidence
    from base b
    left join residency r on r.patient_id = b.patient_id
    where not (coalesce(r.town_3yr,0)=0
           and coalesce(r.area_3yr,0)=0
           and b.placed_in_cochrane=0)
),

-- ── THE DEMAND POPULATION ──────────────────────────────────────────────────
-- One row per PERSON, on their first-ever residential placement.
--   admission_seq = 1  → their earliest in-window episode
--   is_true_first = 1  → and that episode is genuinely their first-ever
-- Both conditions are required. Without the second, someone placed in 2018 and
-- transferred in 2024 would be counted as new demand in 2024.
placement as (
    select *,
           iff(placed_in_cochrane=1,'Placed in Cochrane','Placed outside Cochrane') as dest
    from ep
    where admission_seq = 1 and is_true_first = 1
      -- Level 3 out of reported scope (see STEP 0b). Applied HERE, not at
      -- STEP 1, so the anchor and the residency window are unaffected.
      and care_stream <> 'Type B - Level 3'
)

-- ════════════════════════════════════════════════════════════════════════════
-- STEP 12 — REPORT BLOCKS
-- Long format: SECTION / ROW_LABEL / COL_LABEL / values. Pivots cleanly in
-- Excel. null::number casts in the first branch set the column types for the
-- whole union.
-- ════════════════════════════════════════════════════════════════════════════
select * from (

-- 1. DEMAND — of Town residents entering care, where did their first
--    placement go? The headline table.
select '1. DEMAND (Town residents, first placement)'         as section,
       care_stream                                           as row_label,
       dest                                                  as col_label,
       count(*)                                              as n_people,
       null::number                                          as n_episodes,
       round(100.0*count(*)/sum(count(*)) over (partition by care_stream),1) as pct,
       null::number(10,1)                                    as median_days,
       null::number(10,1)                                    as p90_days
from placement where residency='Town of Cochrane' group by 1,2,3

-- 1b. Same, all care levels combined.
union all
select '1. DEMAND (Town residents, first placement)', 'ALL Type A/B', dest,
       count(*), null,
       round(100.0*count(*)/sum(count(*)) over (),1), null, null
from placement where residency='Town of Cochrane' group by 1,2,3

-- 2. DEMAND over time. Is local access improving or deteriorating?
--    Percentages are within each fiscal year.
union all
select '2. DEMAND by fiscal year (Town residents)', adm_fye::string, dest,
       count(*), null,
       round(100.0*count(*)/sum(count(*)) over (partition by adm_fye::string),1), null, null
from placement where residency='Town of Cochrane' group by 1,2,3

-- 3. CAPACITY USE — who occupies Cochrane's beds. Counted on ALL episodes,
--    not just first placements, because every admission consumes a bed.
--    n_people within a care stream will not sum across streams: one person can
--    hold a Type B and later a Type A placement. Use the ALL row for totals.
union all
select '3. CAPACITY USE (all placements into Cochrane)', residency, care_stream,
       count(distinct patient_id), count(*),
       round(100.0*count(*)/sum(count(*)) over (partition by care_stream),1), null, null
from ep where placed_in_cochrane = 1 and care_stream <> 'Type B - Level 3' group by 1,2,3

union all
select '3. CAPACITY USE (all placements into Cochrane)', residency, 'ALL',
       count(distinct patient_id), count(*),
       round(100.0*count(*)/sum(count(*)) over (),1), null, null
from ep where placed_in_cochrane = 1 and care_stream <> 'Type B - Level 3' group by 1,2,3

-- 4. TIME TO PLACEMENT. NEW PLACEMENTS ONLY — transfers run a different clock
--    and mixing them produces a median that describes nobody. Median and 90th
--    percentile, not mean: the distribution has a long right tail.
union all
select '4. TIME TO PLACEMENT (new placements only)', residency, dest,
       count(*), null, null,
       median(wait_days)::number(10,1),
       (percentile_cont(0.90) within group (order by wait_days))::number(10,1)
from placement where pathway='NEW PLACEMENT' and wait_days is not null group by 1,2,3

-- 5. WITHDRAWN — RANK OF THE SITE RECEIVED.
--    This block reported service_provider_rating as the person's preference
--    rank for the site they were admitted to. It does not mean that, and the
--    block is removed rather than corrected.
--
--    Tested against the waitlist source (TS_WAITLIST_TREND_WITH_RATINGS_1671):
--    of 344 admissions into Cochrane facilities, 285 were to a site the person
--    had never listed as a preference — and 187 of those 285 carry a rating of
--    1. One client waited 894 days for Bethany Airdrie, was placed at Bethany
--    Cochrane, and the admission record scores that placement 1.
--
--    Recorded preference lives in the waitlist source, not here. See
--    04_displacement_check.py, which is what the 138-of-220 displacement
--    finding rests on. Do not reinstate this block.

-- 6. PLACE OF ORIGIN — the setting a Town resident entered care from, taken at
--    their first-ever residential admission. Answers "does the pathway into
--    care run through hospital, or from the community?"
union all
select '6. PLACE OF ORIGIN (Town residents)',
       case when upper(origin_setting) like '%RURAL - HOME%'                        then 'Own home - rural'
            when upper(origin_setting) in ('CAL - HOME','EDM - PERSONAL RESIDENCE') then 'Own home'
            when upper(origin_setting) like '%LODGE%'                               then 'Lodge'
            when upper(origin_setting) like '%SL4%'
              or upper(origin_setting) like '%ASSISTED LIVING%'                     then 'Supportive living'
            when upper(origin_setting) like '%HOSPITAL%'
              or upper(origin_setting) like '%FOOTHILLS%'
              or upper(origin_setting) like '%LOUGHEED%'
              or upper(origin_setting) like '%ROCKYVIEW%'
              or upper(origin_setting) like '%MEDICAL CENTRE%'
              or upper(origin_setting) like '%HEALTH CAMPUS%'                       then 'Acute hospital'
            when upper(origin_setting) like '%RCTP%'
              or upper(origin_setting) like '%REHAB%'
              or upper(origin_setting) like '%GERIATRIC%'
              or upper(origin_setting) like '% IT%'                                 then 'Transition / rehab'
            when upper(origin_setting) like '%LTC%'                                 then 'Other continuing care'
            else 'Other / unclear' end,
       dest, count(*), null,
       round(100.0*count(*)/sum(count(*)) over (),1), null, null
from placement where residency='Town of Cochrane' group by 1,2,3

-- 7. DATA QUALITY AND INTEGRITY CHECKS — read before using any figure above.
union all
select '7. DATA QUALITY', 'Demand population (first-ever placement in window)', 'people',
       count(*), null, null, null, null
from placement

-- People already in residential care before the window opened. Their in-window
-- episode is a later placement, so they are excluded from demand.
union all
select '7. DATA QUALITY', 'Excluded: already in care before 2021-04-01', 'people',
       count(distinct patient_id), null, null, null, null
from ep where admission_seq=1 and is_true_first=0 and care_stream <> 'Type B - Level 3'

-- How much registry history each residency verdict rests on. A "not from
-- Cochrane" verdict on two years of history is weaker than one on thirty.
union all
select '7. DATA QUALITY', 'Residency confidence (demand population)', confidence,
       count(*), null, round(100.0*count(*)/sum(count(*)) over (),1), null, null
from placement group by 1,2,3

union all
select '7. DATA QUALITY', 'All in-scope episodes', 'people / episodes',
       count(distinct patient_id), count(*), null, null, null
from ep

-- INTEGRITY CHECK 1 — every demand row must be that person's first-ever
-- Type A/B admission. MUST be 100% "match". Anything else invalidates the
-- demand figures and the cause needs finding before anything is circulated.
union all
select '7. DATA QUALITY',
       'CHECK 1: demand row = first-ever Type A/B admission',
       iff(admission_date = first_ab_dt, 'match', 'MISMATCH - investigate'),
       count(*), null, round(100.0*count(*)/sum(count(*)) over (),1), null, null
from placement group by 1,2,3

-- INTEGRITY CHECK 2 — the demand population must be exactly one row per
-- person. n_people and n_episodes MUST be equal. If they differ, someone is
-- being counted twice and every demand percentage is wrong.
union all
select '7. DATA QUALITY', 'CHECK 2: demand population uniqueness',
       'distinct people / rows',
       count(distinct patient_id), count(*), null, null, null
from placement

) order by section, row_label, col_label;
