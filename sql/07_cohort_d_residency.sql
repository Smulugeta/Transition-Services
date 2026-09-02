-- ============================================================================
-- COHORT D — RESIDENCY FOR PEOPLE WHO WERE NEVER PLACED
--
-- STATUS: diagnostic. Query 08 is the controlling logic for A/B/C/D and is
-- what the report reads from. This query is kept because it isolates the
-- list-entry residency anchor so it can be tested on its own (block V).
--
-- TWO CORRECTIONS FROM REVIEW
--   · Missing registry information is now UNRESOLVED, never "not a resident".
--     The earlier version's unresolved branch could not fire — the GROUP BY
--     always produced a row — so every unmatched person fell through to
--     non-resident and cohort D was systematically understated.
--   · The person's outcome is read across every spell (ever_placed from
--     query 05), not from the first spell's exit_reason. 8.7% of people show
--     no placement on their first spell and were placed on a later one.
--
-- THE PROBLEM THIS SOLVES
-- Queries 01 and 02 determine residence by anchoring on a person's first-ever
-- Type A/B admission and reading the provincial registry for the three fiscal
-- years before it. Cohort D is defined by never having been admitted. The
-- anchor does not exist for them, which is why the province-wide spell file
-- (query 05) carries 52,877 people and residency for 1.2% of them.
--
-- THE FIX
-- Anchor on LIST ENTRY instead — the first day the person appears on the
-- waitlist. It is the same logical event as the admission anchor, one step
-- earlier in the pathway: the moment the system established that this person
-- needed residential care. The same contamination protection holds, because
-- the three fiscal years BEFORE someone joins a waitlist cannot contain the
-- facility they would later have been placed in.
--
-- WHY THE VALIDATION BLOCK AT THE BOTTOM IS NOT OPTIONAL
-- A/B/C anchor on admission; D anchors on list entry. Different anchors mean
-- the cohorts are not automatically comparable, and A + C + D is not a legal
-- sum until they are shown to be. Block V does that test on the ~159 people
-- who have BOTH a placement and a waitlist record: it computes residency both
-- ways for the same person and reports how often the two agree.
--   · High agreement  -> the anchors are interchangeable, report A + C + D.
--   · Low agreement   -> report D separately and say why. Do not sum.
-- Run block V and read it BEFORE using any number from blocks 1-4.
--
-- SCOPE NOTE — WHY THIS IS NOT FILTERED ON WHO RATED COCHRANE
-- Only 159 of the 317 placed Town of Cochrane residents ever rated a Cochrane
-- site — about half. Building cohort D from "people who asked for Cochrane"
-- would therefore miss roughly half of it, and would select on willingness to
-- ask rather than on residence. Residency is the filter. Which sites a person
-- rated is a separate question, answered by query 03.
-- ============================================================================
with

-- ── STEP 0 — CARE TYPE VOCABULARY ──────────────────────────────────────────
-- Same crosswalk as queries 01 and 05. Tagged, not filtered: Level 3 and
-- hospice/palliative are excluded from reported figures but must stay visible
-- so the exclusion can be seen rather than trusted.
scope_care_type (care_type, care_stream) as (
    select * from values
        ('CAL - Long Term Care',                           'Type A'),
        ('EDM - LTC',                                      'Type A'),
        ('CAL - Supportive Living Level 4 (DAL)',          'Type B'),
        ('CAL - Supportive Living Level 4 Dementia (DAL)', 'Type B'),
        ('EDM - DSL4 / DSL4D',                             'Type B'),
        ('CAL - Supportive Living Level 3 (PCH)',          'Type B - Level 3'),
        ('EDM - DSL3',                                     'Type B - Level 3'),
        ('EDM - Hospice',                                  'Hospice / Palliative'),
        ('CAL - Palliative',                               'Hospice / Palliative')
),

-- ── STEP 1 — THE SPELL TABLE FROM QUERY 05 ─────────────────────────────────
-- Materialise query 05 as a table or view and point this at it. Re-deriving
-- the spell logic here would let the two drift apart, and every figure in this
-- query depends on list_entry being computed identically.
spells as (
    select * from <schema>.cochrane_waitlist_spells      -- output of 05
),

-- ── STEP 2 — THE ANCHOR: FIRST TIME THIS PERSON EVER JOINED THE LIST ───────
-- Fixed ONCE per person, exactly as residency is in query 01. A person's
-- origin does not change because they were re-registered under a new transfer
-- id, or because they came back onto the list a year later.
-- FYE = fiscal year ENDING 31 March: April-December -> year + 1, else year.
anchor as (
    select phn,
           min(list_entry)                                    as first_list_entry,
           min_by(care_stream,       list_entry)              as care_stream_at_entry,
           min_by(location_at_entry, list_entry)              as setting_at_entry,
           max(left_truncated)                                as left_truncated,
           -- PERSON-LEVEL, across every spell. Never the first spell's exit.
           max(ever_placed)                                   as ever_placed,
           min(first_placement_date)                          as first_placement_date,
           max(still_waiting_any_spell)                       as still_waiting,
           max(iff(exit_reason = 'DIED WAITING', 1, 0))        as died_waiting_any_spell
    from spells
    where phn is not null
    group by phn
),
based as (
    select a.*,
           iff(month(a.first_list_entry) >= 4,
               year(a.first_list_entry) + 1,
               year(a.first_list_entry))                      as entry_fye
    from anchor a
),

-- ── STEP 3 — REGISTRY ADDRESS RESOLVED TO A LEGAL BOUNDARY ─────────────────
-- Town of Cochrane is the Statistics Canada census subdivision, not the
-- reference table's municipality field (which mislabels 22 Rocky View County
-- codes) and not the T4C prefix (which splits 562 Town / 41 county).
geo as (
    select lpad(r.phn::string,9,'0')                          as phn,
           r.fye,
           iff(upper(trim(pc.csdname_2021)) = 'COCHRANE'
               and upper(trim(pc.csdtype_2021)) = 'T', 1, 0)  as in_town,
           iff(upper(trim(pc.local_name)) = 'COCHRANE | SPRINGBANK', 1, 0) as in_area
    from db_source_ah_provincial_registry.curated.provincial_registry r
    join db_source_ah_postal_code.curated.tb_postal_code pc
      on pc.postalcode = r.postal_cd
),

-- ── STEP 4 — THE THREE-YEAR PRE-CARE WINDOW ────────────────────────────────
-- Ends the year BEFORE list entry, so a move into a facility during the entry
-- year cannot leak in. Identical window to query 01.
residency as (
    select b.phn,
           max(iff(g.in_town = 1
                   and g.fye between b.entry_fye - 3 and b.entry_fye - 1, 1, 0)) as town_3yr,
           max(iff(g.in_area = 1
                   and g.fye between b.entry_fye - 3 and b.entry_fye - 1, 1, 0)) as area_3yr,
           count(distinct g.fye)                                                 as n_registry_fye,
           -- years of address INSIDE the lookback window. Zero here means the
           -- test could not be run, which is not the same as failing it.
           count(distinct iff(g.fye between b.entry_fye - 3 and b.entry_fye - 1,
                              g.fye, null))                                      as n_window_fye
    from based b
    left join geo g on g.phn = b.phn
    group by b.phn
),

cohort_d as (
    select b.*,
           coalesce(r.town_3yr, 0)                            as town_3yr,
           coalesce(r.area_3yr, 0)                            as area_3yr,
           coalesce(r.n_registry_fye, 0)                      as n_registry_fye,
           coalesce(r.n_window_fye, 0)                        as n_window_fye,
           -- A verdict of "not a resident" requires an address IN THE WINDOW
           -- that is somewhere else. No registry record, or a record with no
           -- address in the three lookback years, is UNRESOLVED. Treating
           -- either as non-resident silently shrinks cohort D.
           case when coalesce(r.town_3yr,0) = 1         then 'Town of Cochrane'
                when coalesce(r.area_3yr,0) = 1         then 'Cochrane catchment'
                when coalesce(r.n_registry_fye,0) = 0   then 'UNRESOLVED - no registry record'
                when coalesce(r.n_window_fye,0)   = 0   then 'UNRESOLVED - no address in lookback window'
                else                                         'Not a Cochrane-area resident' end as residency,
           case when coalesce(r.n_registry_fye,0) >= 10 then 'HIGH'
                when coalesce(r.n_registry_fye,0) >=  5 then 'MEDIUM'
                else                                        'LOW'  end             as confidence
    from based b
    left join residency r on r.phn = b.phn
)

-- ════════════════════════════════════════════════════════════════════════════
-- REPORT BLOCKS. Same long format as query 01 so the two can be stacked.
-- ════════════════════════════════════════════════════════════════════════════
select * from (

-- 1. COHORT D SIZED, BY RESIDENCY AND OUTCOME. The headline: how many Town of
--    Cochrane residents needed residential care and never received a bed.
select 'D1. COHORT D by residency and outcome'      as section,
       residency                                    as row_label,
       case when ever_placed = 1            then 'placed (any spell)'
            when still_waiting = 1          then 'still waiting at end of follow-up'
            when died_waiting_any_spell = 1 then 'died, no placement observed'
            else 'no placement observed by end of follow-up' end as col_label,
       count(*)                                     as n_people,
       round(100.0*count(*)/sum(count(*)) over (partition by residency),1) as pct
from cohort_d
where care_stream_at_entry in ('Type A','Type B')   -- reported scope; see STEP 0
group by 1,2,3

-- 2. THE COMPLETED DEMAND DENOMINATOR. A + C is demand that was eventually
--    served; adding D gives total local need. LEGAL ONLY IF BLOCK V PASSES.
union all
select 'D2. Total Town demand (A + C + D)', 'Town of Cochrane',
       case when ever_placed = 1            then 'placed (cohorts A + C)'
            when still_waiting = 1          then 'still waiting (censored)'
            when died_waiting_any_spell = 1 then 'died, no placement observed'
            else 'no placement observed by end of follow-up' end,
       count(*), round(100.0*count(*)/sum(count(*)) over (),1)
from cohort_d
where residency = 'Town of Cochrane'
  and care_stream_at_entry in ('Type A','Type B')
group by 1,2,3

-- 3. SETTING AT LIST ENTRY — the "acute site or community" question, for the
--    never-placed. Comparable with block 6 of query 01, which is the same
--    breakdown for people who were placed.
union all
select 'D3. Setting at list entry (Town residents)',
       case when upper(setting_at_entry) like '%RURAL - HOME%'                       then 'Own home - rural'
            when upper(setting_at_entry) in ('CAL - HOME','EDM - PERSONAL RESIDENCE') then 'Own home'
            when upper(setting_at_entry) like '%LODGE%'                              then 'Lodge'
            when upper(setting_at_entry) like '%SL4%'
              or upper(setting_at_entry) like '%ASSISTED LIVING%'                    then 'Supportive living'
            when upper(setting_at_entry) like '%HOSPITAL%'
              or upper(setting_at_entry) like '%FOOTHILLS%'
              or upper(setting_at_entry) like '%LOUGHEED%'
              or upper(setting_at_entry) like '%ROCKYVIEW%'
              or upper(setting_at_entry) like '%MEDICAL CENTRE%'
              or upper(setting_at_entry) like '%HEALTH CAMPUS%'                      then 'Acute hospital'
            when upper(setting_at_entry) like '%RCTP%'
              or upper(setting_at_entry) like '%REHAB%'                              then 'Transition / rehab'
            when upper(setting_at_entry) like '%LTC%'                                then 'Other continuing care'
            else 'Other / unclear' end,
       iff(ever_placed = 1, 'placed', 'no placement observed'), count(*),
       round(100.0*count(*)/sum(count(*)) over (),1)
from cohort_d
where residency = 'Town of Cochrane' and care_stream_at_entry in ('Type A','Type B')
group by 1,2,3

-- 4. HOW MUCH REGISTRY HISTORY EACH VERDICT RESTS ON. A "not from Cochrane"
--    verdict on two years of history is weaker than one on thirty. Compare
--    against query 01: 86.4% HIGH, 5.0% under five years.
union all
select 'D4. Residency confidence', residency, confidence, count(*),
       round(100.0*count(*)/sum(count(*)) over (partition by residency),1)
from cohort_d
group by 1,2,3

) order by section, row_label, col_label;


-- ════════════════════════════════════════════════════════════════════════════
-- BLOCK V — ANCHOR EQUIVALENCE. RUN THIS FIRST.
--
-- For everyone who has BOTH a placement and a waitlist record, compute
-- residency both ways and compare. This is the test that decides whether
-- A + C + D is a legal sum or whether D must be reported on its own.
--
-- READ IT AS: of people whose residency the admission anchor calls "Town",
-- what share does the list-entry anchor also call "Town"? Disagreement is not
-- automatically an error — someone can genuinely move between joining a
-- waitlist and being admitted — but it caps how far the two can be combined.
-- ════════════════════════════════════════════════════════════════════════════
-- select
--     p.residency                      as residency_by_admission_anchor,
--     d.residency                      as residency_by_list_entry_anchor,
--     count(*)                         as n_people,
--     round(100.0*count(*)/sum(count(*)) over (partition by p.residency),1) as pct_of_admission_verdict
-- from <schema>.cochrane_client_level p          -- output of query 02
-- join cohort_d d on d.phn = p.phn
-- group by 1,2
-- order by 1,2;
