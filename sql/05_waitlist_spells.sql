-- ============================================================================
-- COHORT D — WAITLIST SPELLS, EXITS AND OUTCOMES
--
-- WHAT THIS IS
-- The placement analysis (01) is conditioned on placement: it counts people who
-- eventually got a bed. This query covers the people who did not — those still
-- waiting, those who withdrew, and those who died before a bed opened. That is
-- cohort D, and it is what turns "demand that was served" into "total demand".
--
-- THE SHAPE PROBLEM AND HOW IT IS SOLVED
-- The waitlist source is a DAILY census: one row per person per rated site per
-- day, 1,826 consecutive dates over five years. Selecting it raw returns tens
-- of millions of rows and answers nothing, because the grain is wrong.
--
-- The fix is not to drop census_date — that destroys the entry date, which is
-- the one thing the whole question depends on. The fix is to collapse it into
-- SPELLS: a continuous run of days on the list. A gap of more than one day
-- means the person came off the list and returned, which is a separate wait.
--
-- WHY SPELLS AND NOT MIN/MAX PER PERSON
-- 29.3% of people leave the list and come back. Taking min(census_date) to
-- max(census_date) per person merges those separate waits into one. On the
-- Cochrane cohort that inflated the longest wait from a median of 45 days to a
-- median of 247 days — a 5x overstatement of the headline number.
--
-- THREE THINGS THIS QUERY WILL NOT DO
--   1. It does not join on current_location. That field is a census snapshot
--      that moves while people wait (52.5% of people change setting), whereas
--      source_location is fixed at admission. Joining a moving field to a fixed
--      one silently drops ~13% of admissions and makes placed people look like
--      they were never placed. current_location is an OUTPUT, never a key.
--   2. It does not read a death date as "died waiting". 37.9% of spells carry a
--      death date; only 17.3% of those died without ever being placed. The rest
--      were placed and died in care later, which is what long-term care is.
--      Conflating the two overstates deaths-on-the-waitlist by 5.8x.
--   3. It does not treat a person vanishing from the census as an exit. 39% of
--      apparent disappearances continue under a new patient_transfer_id within
--      90 days — the person did not leave, they were re-registered.
--   4. It does not let one admission satisfy more than one spell. An earlier
--      version bounded the admission only from below (>= list_entry), so a
--      person who left, returned, and was then placed had the placement
--      credited to BOTH spells: 2,890 spell rows wrongly marked placed. The
--      admission is now bounded by the next spell's entry as well.
--   5. It does not decide cohort D from a single spell. The spell-level
--      exit_reason is a diagnostic. The person-level columns ever_placed and
--      first_placement_date are what cohort D is read from — 8.7% of people
--      show no placement on their first spell but were placed on a later one.
--      Query 08 is the controlling person-level logic.
--
-- LEFT-TRUNCATION — READ BEFORE QUOTING ANY WAIT
-- The census begins 2021-04-01. Anyone already on the list that day shows a
-- list_entry of 2021-04-01 regardless of when they really joined: 1,604
-- people. Their list_entry and days_observed understate the true wait, and an
-- equivalent person who joined before the window and was never placed is
-- invisible. The left_truncated flag marks them so every figure can be run
-- with and without.
-- ============================================================================
with

-- ── PARAMETERS ─────────────────────────────────────────────────────────────
-- died_waiting_days is a JUDGEMENT CALL and it moves the answer materially:
-- 7 days -> 4,555 people, 30 -> 5,445, 90 -> 6,366, 180 -> 7,199. Whatever is
-- chosen must be stated in the same sentence as the number it produces, every
-- time. 30 days reads as "died at or around the point they left the list".
params as (select 30 as died_waiting_days, 90 as reregister_days),

-- ── STEP 0 — CARE TYPE VOCABULARY ──────────────────────────────────────────
-- Tagged, not filtered. Hospice and palliative clients are EXPECTED to die and
-- will inflate any death-related figure: 58% of spells entering from a hospice
-- or palliative setting carry a death date, against 37.9% overall. Reporting
-- them inside "died waiting for continuing care" is a different claim from the
-- one it appears to be. Split on care_stream in every death-related output.
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

-- ── STEP 1 — THE CENSUS, NARROWED ──────────────────────────────────────────
-- Half-open on the upper bound. BETWEEN against a timestamp column cuts off at
-- midnight on the end date and silently loses that day.
wl as (
    select w.patient_id, w.patient_transfer_id, w.phn,
           trim(w.care_type)      as care_type,
           ct.care_stream,
           w.current_location,
           w.assess_approved_date,
           w.enabled_for_transfer_date,
           w.census_date::date    as census_date
    from db_team_continuing_seniors_care.calgary_bi.ts_waitlist_trend_with_ratings_1671 w
    join scope_care_type ct on ct.care_type = trim(w.care_type)
    where w.census_date >= '2021-04-01'
      and w.census_date <  '2026-04-01'
),

-- One row per person-transfer-DAY. Collapsing the rated sites away here is
-- what stops the row explosion: a person rating three sites must not have
-- their wait counted three times. Rated sites come out of query 03 instead,
-- keyed on the same patient_id + patient_transfer_id.
daily as (
    select distinct patient_id, patient_transfer_id, phn, care_type, care_stream,
           current_location, assess_approved_date, enabled_for_transfer_date, census_date
    from wl
),

-- ── STEP 2 — FIND THE SPELL BOUNDARIES ─────────────────────────────────────
-- A gap of more than one day since the previous census row starts a new spell.
flagged as (
    select d.*,
           iff(datediff('day',
                 lag(census_date) over (partition by patient_id, patient_transfer_id
                                        order by census_date),
                 census_date) > 1, 1, 0) as spell_start
    from daily d
),
numbered as (
    select f.*,
           sum(spell_start) over (partition by patient_id, patient_transfer_id
                                  order by census_date
                                  rows between unbounded preceding and current row) as spell_no
    from flagged f
),

-- ── STEP 3 — ONE ROW PER SPELL ─────────────────────────────────────────────
-- min_by / max_by take the attribute AS AT the first and last day of the spell.
-- location_at_entry is the "acute site or community" answer; taking the modal
-- or latest value instead would answer a different question.
spell as (
    select patient_id, patient_transfer_id, phn, spell_no,
           min(care_type)                        as care_type,
           min(care_stream)                      as care_stream,
           min(census_date)                      as list_entry,
           max(census_date)                      as list_last_seen,
           count(distinct census_date)           as days_observed,
           min_by(current_location, census_date) as location_at_entry,
           max_by(current_location, census_date) as location_at_exit,
           min(assess_approved_date)::date       as assess_approved_date,
           min(enabled_for_transfer_date)::date  as enabled_for_transfer_date
    from numbered
    group by 1,2,3,4
),

-- ── STEP 3b — WHERE THE NEXT SPELL OF THE SAME TRANSFER BEGINS ─────────────
-- Used to bound the admission join from above. An admission that lands after
-- the next spell has already started belongs to that spell, not this one.
-- Bounding only from below credited one placement to every prior spell.
spell_b as (
    select s.*,
           lead(list_entry) over (partition by patient_id, patient_transfer_id
                                  order by spell_no)        as next_entry_same_transfer
    from spell s
),

-- ── STEP 4 — THE FIRST AND LAST CENSUS IN THE EXTRACT ──────────────────────
-- Anyone present on this date has not finished waiting. Their duration is
-- censored, not zero, and they must stay in the denominator: dropping them
-- measures only the people who got in, which biases every wait downward.
census_bounds as (select min(census_date) as first_dt, max(census_date) as last_dt from wl),

-- ── STEP 5 — ATTACH PLACEMENT AND DEATH ────────────────────────────────────
-- The admission join is on the episode key ONLY (patient_id +
-- patient_transfer_id) plus a date sanity bound. See header note 1.
-- qualify de-duplicates: a PHN can carry more than one vital-stats row, and a
-- person can have more than one admission after the spell opened. Take the
-- earliest of each — the first bed offered, the one death that matters.
resolved as (
    select s.* exclude (next_entry_same_transfer),
           cb.last_dt                             as last_census_date,
           iff(s.list_entry = cb.first_dt, 1, 0)  as left_truncated,
           b.admission_date::date                 as admission_date,
           b.admission_location,
           b.source_location,                     -- output only, never a join key
           p.birth_date,                          -- CONFIRM this column exists on
                                                  -- patient; taking it from the
                                                  -- admissions table leaves every
                                                  -- never-placed person with no age
           v.dethdate::date                       as death_date,
           iff(s.list_last_seen = cb.last_dt, 1, 0) as still_waiting
    from spell_b s
    cross join census_bounds cb
    left join db_source_strata_health_pathways.raw.admissions b
           on b.patient_id          = s.patient_id
          and b.patient_transfer_id = s.patient_transfer_id
          and b.admission_date::date >= s.list_entry
          -- bounded from ABOVE by the next spell of this transfer, so one
          -- admission can satisfy exactly one spell. Open-ended on the final
          -- spell: the placement normally lands after the last census day.
          and b.admission_date::date <  coalesce(s.next_entry_same_transfer, '9999-12-31'::date)
    left join db_source_strata_health_pathways.raw.patient p
           on p.id = s.patient_id
    left join db_source_ah_vital_stats.curated.tb_vital_stats_deaths_adhoc v
           on v.stkh_num_1 = s.phn
    qualify row_number() over (partition by s.patient_id, s.patient_transfer_id, s.spell_no
                               order by b.admission_date, v.dethdate) = 1
),

-- ── STEP 6 — DID THE PERSON CONTINUE UNDER A NEW REGISTRATION? ─────────────
-- 39% of apparent disappearances are not exits. The person's transfer was
-- closed and a new one opened, often within days. Without this test they land
-- in "left the list, outcome unknown" and inflate cohort D.
continued as (
    select r.*,
           lead(list_entry) over (partition by patient_id
                                  order by list_entry, patient_transfer_id, spell_no)
                                                  as next_spell_entry,
           lead(patient_transfer_id) over (partition by patient_id
                                  order by list_entry, patient_transfer_id, spell_no)
                                                  as next_spell_transfer
    from resolved r
)

-- ── STEP 7 — CLASSIFY THE EXIT ─────────────────────────────────────────────
-- Order matters. Placement and death outrank re-registration; a resolved
-- outcome is never overwritten by evidence that the person also reappeared.
select c.* exclude (next_spell_entry, next_spell_transfer),

       -- PERSON-LEVEL OUTCOME. Cohort D is read from these, never from the
       -- spell-level exit_reason below. "Did this person ever receive a
       -- placement across every spell we can see" is the question; "what
       -- happened at the end of their first spell" is not.
       max(iff(c.admission_date is not null, 1, 0))
           over (partition by c.patient_id)                              as ever_placed,
       min(c.admission_date) over (partition by c.patient_id)            as first_placement_date,
       max(c.still_waiting) over (partition by c.patient_id)             as still_waiting_any_spell,

       iff(c.admission_date is not null,
           datediff('day', c.list_entry, c.admission_date), null)     as days_to_list_placement,

       -- the wait clock the report uses, for comparability with query 01
       iff(c.admission_date is not null and c.assess_approved_date is not null,
           datediff('day', c.assess_approved_date, c.admission_date), null) as days_approved_to_admission,

       case
         when c.still_waiting = 1
              then 'STILL WAITING (censored)'
         when c.admission_date is not null and c.death_date is not null
              and c.death_date < c.admission_date
              then 'ANOMALY - admitted after death date'
         when c.admission_date is not null and c.death_date is not null
              then 'PLACED, died later in care'
         when c.admission_date is not null
              then 'PLACED'
         when c.death_date is not null
              and c.death_date >= c.list_last_seen
              and datediff('day', c.list_last_seen, c.death_date) <= p.died_waiting_days
              then 'DIED WAITING'
         when c.death_date is not null and c.death_date < c.list_entry
              then 'ANOMALY - death precedes list entry'
         when c.death_date is not null
              then 'left list, died later'
         when c.next_spell_entry is not null
              and c.next_spell_transfer <> c.patient_transfer_id
              and datediff('day', c.list_last_seen, c.next_spell_entry)
                  between 0 and p.reregister_days
              then 'RE-REGISTERED under a new transfer'
         when c.next_spell_entry is not null
              and datediff('day', c.list_last_seen, c.next_spell_entry)
                  between 0 and p.reregister_days
              then 'returned to the list later'
         else 'LEFT LIST - outcome unknown'
       end                                                            as exit_reason,

       -- assessed and approved = genuinely ready for placement. 17% of the
       -- never-placed were still in process and were never waiting for a bed.
       iff(c.assess_approved_date is not null, 1, 0)                  as was_approved

from continued c
cross join params p
order by c.patient_id, c.list_entry
;
