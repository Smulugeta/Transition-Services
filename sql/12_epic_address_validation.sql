-- ============================================================================
-- EPIC / CONNECT CARE PAT_ADDR_CHNG_HX — SOURCE VALIDATION BEFORE ANY USE
--
-- Epic is NOT in the production residency hierarchy. Query 09 rev 2.7 carries
-- it as sensitivity-only columns (epic_*, cohort_epic_sens); the production
-- cohort column is unchanged. These blocks decide whether it should ever be
-- promoted.
--
-- WHAT THE FIRST SAMPLE ALREADY SHOWS
--   · Every visible EFF_START_DATE is 2026-09-01 — the day before this was
--     written. Several rows have EFF_END_DATE on the same day and every
--     address field null. That is the signature of a load / migration
--     timestamp, not a period of residence. Block 2 quantifies it. If the
--     start dates are load dates, NO row can be active on a 2021-2025 demand
--     date and Epic is at best a current-address snapshot.
--   · PO Box addresses appear (PO Box 2057 / 71220 Range Road 145A, T0G 1E0).
--     A PO Box postal code maps to the post office, not the residence.
--   · ZIP_HX is the postal code. Residency comes from the same postal
--     geography as Registry and Strata, never from CITY_HX.
-- ============================================================================

-- ── 1. IS IDENTITY_TYPE_ID 221 THE PHN? PHN QUALITY AND UNIQUENESS ─────────
-- The identity-type dimension names the type. Confirm 221 = Alberta PHN /
-- ULI before trusting the join.
select id_type_name, identity_type_id
from db_source_epic_clarity.raw.identity_id_type            -- CONFIRM table name in this Clarity build
where identity_type_id in ('221');

-- digit-length quality of identity_id under type 221 (count BEFORE any padding)
select case when d = 0 then '0 digits' when d between 1 and 8 then '1-8 digits'
            when d = 9 then '9 digits' else '>9 digits' end as digit_class,
       count(*) as rows_, count(distinct pat_id) as patients,
       count_if(digits = '000000000') as all_zero
from (select pat_id, regexp_replace(identity_id::string,'[^0-9]','') as digits,
             length(regexp_replace(identity_id::string,'[^0-9]','')) as d
      from db_source_epic_clarity.raw.identity_id where identity_type_id = '221')
group by 1 order by 1;

-- uniqueness both ways
select 'patients with >1 PHN' as check_, count(*) as n
from (select pat_id from db_source_epic_clarity.raw.identity_id where identity_type_id='221'
      group by pat_id having count(distinct identity_id) > 1)
union all
select 'PHNs held by >1 patient', count(*)
from (select identity_id from db_source_epic_clarity.raw.identity_id where identity_type_id='221'
      group by identity_id having count(distinct pat_id) > 1);

-- ── 2. ARE EFF_START_DATE / EFF_END_DATE RESIDENCE PERIODS OR LOAD DATES? ──
-- If most rows share one recent start date, that date is when the history
-- was loaded, not when anyone moved.
select eff_start_date::date as start_dt, count(*) as rows_, count(distinct pat_id) as patients,
       round(100.0*count(*)/sum(count(*)) over (),2) as pct_of_rows,
       count_if(eff_end_date::date = eff_start_date::date) as zero_length_rows,
       count_if(addr_hx_line1 is null and zip_hx is null) as rows_with_no_address
from db_source_epic_clarity.raw.pat_addr_chng_hx
group by 1 order by 2 desc limit 25;

-- the shape over time: how many rows START in each year? A real history has
-- starts spread over decades; a load has one spike.
select year(eff_start_date) as start_year, count(*) as rows_,
       count_if(eff_end_date is null) as still_open,
       min(eff_start_date)::date as earliest, max(eff_start_date)::date as latest
from db_source_epic_clarity.raw.pat_addr_chng_hx
group by 1 order by 1;

-- per patient: how many address rows, how many are zero-length / empty
select rows_per_patient, count(*) as patients from (
    select pat_id, count(*) as rows_per_patient from db_source_epic_clarity.raw.pat_addr_chng_hx group by pat_id
) group by 1 order by 1;

-- Is there ANY row whose start predates 2026 for the cohort's window? This is
-- the decisive number for "active at demand".
select count(*)                                                     as rows_,
       count_if(eff_start_date::date < '2026-01-01')                 as start_before_2026,
       count_if(eff_start_date::date < '2021-04-01')                 as start_before_window,
       count_if(eff_start_date::date = (select max(eff_start_date::date)
                                        from db_source_epic_clarity.raw.pat_addr_chng_hx)) as start_equals_source_max
from db_source_epic_clarity.raw.pat_addr_chng_hx;

-- ── 7. FACILITY, PO BOX AND PLACEHOLDER ADDRESSES ──────────────────────────
-- Concurrent occupancy: distinct patients holding the same (line1, zip) on the
-- same day. Sampled quarterly. Facilities rise to the top; apartment units
-- with successive tenants do not.
with v as (
    select distinct pat_id, upper(trim(addr_hx_line1)) as line1,
           upper(regexp_replace(zip_hx,'[^A-Za-z0-9]','')) as zip,
           eff_start_date::date as f, coalesce(eff_end_date::date, current_date()) as t
    from db_source_epic_clarity.raw.pat_addr_chng_hx
    where addr_hx_line1 is not null
),
cal as (select dateadd('quarter', seq4(), '2015-01-01'::date) as d from table(generator(rowcount => 48))),
occ as (select v.line1, v.zip, c.d, count(distinct v.pat_id) as occupants
        from v join cal c on c.d between v.f and v.t group by 1,2,3)
select line1, zip, max(occupants) as peak_concurrent_occupants
from occ group by 1,2 having max(occupants) >= 3
order by 3 desc limit 100;

-- PO boxes and placeholders
select count(*) as rows_,
       count_if(upper(addr_hx_line1) like 'PO BOX%' or upper(addr_hx_line1) like 'P.O. BOX%'
                or upper(addr_hx_line1) like 'BOX %')                               as po_box_rows,
       count_if(upper(addr_hx_line1) like '%NO FIXED%' or upper(addr_hx_line1) like '%HOMELESS%'
                or upper(addr_hx_line1) like '%UNKNOWN%' or upper(addr_hx_line1) like '%EVACUEE%') as placeholder_rows,
       count_if(zip_hx is null)                                                     as null_postal_rows,
       count_if(country_hx is not null and upper(country_hx) not in ('CA','CAN','CANADA')) as foreign_rows
from db_source_epic_clarity.raw.pat_addr_chng_hx;

-- ── 6. POSTAL MAPPING RATE THROUGH THE SAME GEOGRAPHY TABLE ────────────────
select count(*) as rows_with_postal,
       count_if(pc.postalcode is not null) as mapped,
       count_if(pc.postalcode is null and left(upper(regexp_replace(a.zip_hx,'[^A-Za-z0-9]','')),1) = 'T') as alberta_unmapped,
       count_if(pc.postalcode is null and left(upper(regexp_replace(a.zip_hx,'[^A-Za-z0-9]','')),1) <> 'T') as out_of_province
from db_source_epic_clarity.raw.pat_addr_chng_hx a
left join db_source_ah_postal_code.curated.tb_postal_code pc
       on upper(regexp_replace(pc.postalcode,'[^A-Za-z0-9]','')) = upper(regexp_replace(a.zip_hx,'[^A-Za-z0-9]',''))
where a.zip_hx is not null;

-- ── CONTROL — PHN 49833-8261 (Strata: Surrey, active on the 2021-06-01 demand) ─
select b.identity_id as phn, a.addr_hx_line1, a.addr_hx_line2, a.city_hx, a.zip_hx, a.country_hx,
       a.eff_start_date, a.eff_end_date,
       iff(a.eff_start_date::date <= '2021-06-01'
           and (a.eff_end_date::date > '2021-06-01' or a.eff_end_date is null), 1, 0) as active_on_2021_06_01
from db_source_epic_clarity.raw.pat_addr_chng_hx a
join db_source_epic_clarity.raw.identity_id b on b.pat_id = a.pat_id and b.identity_type_id = '221'
where regexp_replace(b.identity_id::string,'[^0-9]','') = '498338261'
order by a.eff_start_date;
-- Expected if Epic carries real history: a Surrey / BC row active on that day.
-- Expected if EFF_START_DATE is a load date: no row active on that day at all.

-- Checks 3-5 and 8-11 (active-at-demand distribution, conflicts, the agreement
-- matrix against Registry, the 15 remaining unresolved, and the sensitivity
-- cohort) need the cohort's demand dates and are produced by query 09 rev 2.7
-- + analysis/07 rev 7.
