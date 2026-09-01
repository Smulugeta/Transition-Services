-- ============================================================================
-- COCHRANE CONTINUING CARE — CLIENT-LEVEL VALIDATION EXTRACT
-- One row per in-scope Type A/B episode, with every field that drives a
-- reported figure. Filter/pivot this and you must reproduce the report exactly.
-- Logic identical to the CEO report query — do not edit one without the other.
-- Level 3 episodes are RETAINED here on purpose. The reported figures exclude
-- them (see 01_demand_capacity_report.sql, STEP 0b); this extract carries the
-- care_stream column so a reviewer can apply that exclusion themselves and see
-- exactly which 3 Town residents it removes, rather than take it on trust.
-- No names: PHI minimised. Add p.given_name / p.last_name to pat_key only if
-- your privacy posture allows and only for internal checking.
-- ============================================================================
with
coch_site (site_name) as (
    select * from values
        ('CAL - Bethany Cochrane LTC_'),('CAL - Hawthorne SL4_'),('CAL - Hawthorne SL4D')
),
scope_care_type (care_type, care_stream) as (
    select * from values
        ('CAL - Long Term Care','Type A'),
        ('EDM - LTC','Type A'),
        ('CAL - Supportive Living Level 4 (DAL)','Type B'),
        ('CAL - Supportive Living Level 4 Dementia (DAL)','Type B'),
        ('EDM - DSL4 / DSL4D','Type B'),
        ('CAL - Supportive Living Level 3 (PCH)','Type B - Level 3'),
        ('CAL - Supportive Living Level 3 (DEL)','Type B - Level 3'),
        ('EDM - DSL3','Type B - Level 3')
),
cand_adm as (
    select a.*, trim(a.admission_location) as site, ct.care_stream
    from admissions a
    join scope_care_type ct on ct.care_type = trim(a.care_type)
    where a.admission_date >= '2021-04-01' and a.admission_date < '2026-04-01'
),
pat_key as (
    select p.id as patient_id,
           case when regexp_replace(p.identifier1::string,'[^0-9]','') = '' then null
                else lpad(regexp_replace(p.identifier1::string,'[^0-9]',''),9,'0') end as phn
    from patient p where p.id in (select distinct patient_id from cand_adm)
),
coch_phn as (
    select distinct lpad(r.phn::string,9,'0') as phn
    from db_source_ah_provincial_registry.curated.provincial_registry r
    join db_source_ah_postal_code.curated.tb_postal_code pc on pc.postalcode = r.postal_cd
    where upper(trim(pc.local_name)) = 'COCHRANE | SPRINGBANK'
),
in_scope as (
    select distinct a.patient_id from cand_adm a join coch_site s on s.site_name = a.site
    union
    select distinct k.patient_id from pat_key k join coch_phn c on c.phn = k.phn
),
episode as (
    select a.patient_id, a.admission_date, a.site, a.care_type, a.care_stream,
           a.source_location, a.assessed_approved_date, a.enabled_for_transfer_date,
           a.service_provider_rating,
           iff(s.site_name is not null,1,0)     as placed_in_cochrane,
           iff(s_src.site_name is not null,1,0) as from_cochrane_site,
           row_number() over (partition by a.patient_id order by a.admission_date) as admission_seq
    from cand_adm a
    join      in_scope  i     on i.patient_id    = a.patient_id
    left join coch_site s     on s.site_name     = a.site
    left join coch_site s_src on s_src.site_name = trim(a.source_location)
    where trim(a.source_location) <> a.site
),
journey as (
    select a.* from admissions a
    where a.patient_id in (select distinct patient_id from episode)
),
adm_counts as (
    select patient_id, count(*) as n_admissions_all_types from journey group by 1
),
first_ab as (
    select j.patient_id, j.admission_date as first_ab_dt,
           j.source_location as origin_setting, j.admission_location as first_ab_site
    from journey j join scope_care_type ct on ct.care_type = trim(j.care_type)
    qualify row_number() over (partition by j.patient_id order by j.admission_date) = 1
),
base as (
    select e.*, k.phn, c.n_admissions_all_types,
           f.first_ab_dt, f.origin_setting, f.first_ab_site,
           iff(month(e.admission_date)>=4, year(e.admission_date)+1, year(e.admission_date)) as adm_fye,
           iff(month(f.first_ab_dt)>=4, year(f.first_ab_dt)+1, year(f.first_ab_dt))          as first_ab_fye,
           iff(e.enabled_for_transfer_date is not null,'TRANSFER','NEW PLACEMENT')           as pathway,
           iff(e.enabled_for_transfer_date is not null,
               datediff('day', e.enabled_for_transfer_date::date, e.admission_date::date),
               datediff('day', e.assessed_approved_date::date,    e.admission_date::date))   as wait_days,
           iff(f.first_ab_dt >= '2021-04-01', 1, 0)                                          as is_true_first,
           datediff('day', f.first_ab_dt::date, e.admission_date::date) as days_in_care_before_placement
    from episode e
    join      first_ab   f on f.patient_id = e.patient_id
    join      adm_counts c on c.patient_id = e.patient_id
    left join pat_key    k on k.patient_id = e.patient_id
),
reg as (
    select lpad(r.phn::string,9,'0') as phn, r.fye,
           iff(upper(trim(pc.csdname_2021))='COCHRANE'
               and upper(trim(pc.csdtype_2021))='T',1,0)                as in_town,
           iff(upper(trim(pc.local_name))='COCHRANE | SPRINGBANK',1,0)  as in_area
    from db_source_ah_provincial_registry.curated.provincial_registry r
    join db_source_ah_postal_code.curated.tb_postal_code pc on pc.postalcode = r.postal_cd
    where lpad(r.phn::string,9,'0') in (select phn from base where phn is not null)
),
residency as (
    select b.patient_id,
        max(iff(g.in_town=1 and g.fye between b.first_ab_fye-3 and b.first_ab_fye-1,1,0)) as town_3yr,
        max(iff(g.in_area=1 and g.fye between b.first_ab_fye-3 and b.first_ab_fye-1,1,0)) as area_3yr,
        max(iff(g.fye between b.first_ab_fye-3 and b.first_ab_fye-1,1,0))                 as lookback_covered,
        max(iff(g.in_town=1,1,0))                                as town_ever,
        max(iff(g.in_town=1 and g.fye < b.first_ab_fye,1,0))     as town_any_before,
        count(distinct iff(g.in_town=1, g.fye, null))            as n_town_fye,
        min(iff(g.in_town=1, g.fye, null))                       as first_town_fye,
        max(iff(g.in_town=1, g.fye, null))                       as last_town_fye,
        count(distinct iff(g.in_area=1, g.fye, null))            as n_area_fye,
        count(distinct g.fye)                                    as n_registry_fye
    from base b left join reg g on g.phn = b.phn
    group by b.patient_id
),
ep as (
    select b.*, r.town_3yr, r.area_3yr, r.lookback_covered, r.town_ever, r.town_any_before,
           r.n_town_fye, r.first_town_fye, r.last_town_fye, r.n_area_fye, r.n_registry_fye,
        case when b.phn is null or r.n_registry_fye = 0 then 'UNRESOLVED'
             when r.town_3yr = 1                        then 'Town of Cochrane'
             when r.area_3yr = 1                        then 'Cochrane area'
             else                                            'Non-resident' end as residency,
        case when r.lookback_covered = 0 then 'LOW'
             when r.n_registry_fye >= 10 then 'HIGH'
             when r.n_registry_fye >=  5 then 'MEDIUM'
             else                             'LOW' end as confidence
    from base b left join residency r on r.patient_id = b.patient_id
    where not (coalesce(r.town_3yr,0)=0 and coalesce(r.area_3yr,0)=0 and b.placed_in_cochrane=0)
)

select
    -- ── identity ──
    patient_id, phn,

    -- ── which rows feed which report section ──
    admission_seq,
    is_true_first,
    iff(admission_seq = 1 and is_true_first = 1, 1, 0)   as in_demand_population,

    -- ── the episode ──
    admission_date, adm_fye, site, care_type, care_stream,
    placed_in_cochrane, from_cochrane_site,
    iff(placed_in_cochrane=1,'Placed in Cochrane','Placed outside Cochrane') as dest,

    -- ── wait clock (audit trail: both source dates shown) ──
    pathway, wait_days, assessed_approved_date, enabled_for_transfer_date,

    -- ── the anchor ──
    first_ab_dt, first_ab_fye, first_ab_site,
    days_in_care_before_placement, n_admissions_all_types,

    -- ── place of origin ──
    origin_setting,
    source_location as immediate_source,
    case when upper(origin_setting) like '%RURAL - HOME%'
           or upper(origin_setting) in ('CAL - HOME','EDM - PERSONAL RESIDENCE') then 'Own home / community'
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
         else 'Other / unclear' end                       as origin_group,

    -- ── residency: verdict AND the evidence behind it ──
    residency,
    town_3yr, area_3yr,
    first_ab_fye - 3 as lookback_from_fye,
    first_ab_fye - 1 as lookback_to_fye,
    lookback_covered,
    n_town_fye, first_town_fye, last_town_fye, n_area_fye, n_registry_fye,
    town_ever, town_any_before,
    confidence,

    -- ── preference ──
    service_provider_rating,
    case coalesce(service_provider_rating::string,'NULL')
         when '1' then '1st choice' when '2' then '2nd choice'
         when '0' then 'not a ranked site (r0)'
         else 'rank '||coalesce(service_provider_rating::string,'NULL') end as rating_label,

    -- ── final classification ──
    case
        when phn is null or n_registry_fye = 0        then 'UNRESOLVED'
        when town_3yr=1 and placed_in_cochrane=1      then 'A  - Town resident, placed in Cochrane'
        when area_3yr=1 and placed_in_cochrane=1      then 'A2 - Area resident, placed in Cochrane'
        when town_3yr=1 and placed_in_cochrane=0      then 'C  - Town resident, placed OUTSIDE'
        when area_3yr=1 and placed_in_cochrane=0      then 'C2 - Area resident, placed OUTSIDE'
        when placed_in_cochrane=1                     then 'B  - Non-resident, placed in Cochrane'
        else                                               'OUT OF SCOPE' end as cohort

from ep
order by patient_id, admission_date;
