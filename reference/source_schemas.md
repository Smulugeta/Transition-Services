# Source schemas confirmed by `describe table` (2026-09-03, sql/13 block 0)

Only columns relevant to the deliverable are listed. "Seen" = present in the
describe output; usability is a separate judgement recorded in the notes.

## Strata `patient` (45 columns)
| Column | Type | Note |
|---|---|---|
| `ID` | NUMBER | = `PATIENT_ID` |
| `IDENTIFIER1` | VARCHAR(64) | = PHN (raw; digits extracted, exactly 9, not all zeros) |
| `IDENTIFIER1_IS_AUTOGEN` | BOOLEAN | system-generated PHN flag; useful for the linkage note |
| `BIRTH_DATE` | TIMESTAMP_NTZ | **DOB candidate (primary)** |
| `GENDER` | VARCHAR(16) | **null in this feed; do not use** (user, 2026-09-03) |
| `DECEASED_DATE` | TIMESTAMP_NTZ | QA cross-check against vital stats only |
| `HC_PATIENT_STATUS`, `CREATION_DATE`, `MODIFICATION_DATE`, `ADDRESS_ID` | | |

## Strata `admissions` (29 columns)
`ADMISSION_NOTICE_ID`, `PATIENT_ID`, `PATIENT_TRANSFER_ID`, `PHN`, `BIRTH_DATE`
(secondary DOB, placed people only), `ADMISSION_DATE`, `ADMISSION_LOCATION`,
`SOURCE_LOCATION`, `CARE_TYPE`, `ASSESSED_APPROVED_DATE`,
`ENABLED_FOR_TRANSFER_DATE`, `TRANSFER_CONFIRMED_DATE`, `ACCEPTED_DATE`,
`DISCHARGE_DATE`, `DISCHARGE_DESTINATION`, `DISCHARGE_REASON`, `PRIORITY_CODE`,
`SERVICE_PROVIDER_RATING`, `VACANCY_NAME`. No sex/gender.

## Waitlist `ts_waitlist_trend_with_ratings_1671` (27 columns)
`CENSUS_DATE`, `PATIENT_ID`, `PATIENT_TRANSFER_ID`, `PHN`, `CURRENT_LOCATION`,
`CARE_TYPE`, `PATIENT_STATUS`, `PREMATCH_AWT`, `IN_PROCESS_DATE`,
`ENABLED_FOR_TRANSFER_DATE`, `ASSESS_APPROVED_DATE`,
`CALCULATED_ASSESS_APPROVED_DATE`, `PRIORITY_NAME`, `DELAY_REASON`,
`DELAYED_DATE`, `RATING`, `SERVICE_PROVIDER_RATED_SITE`, `RUN_DATE`.
No DOB, no sex/gender. Carries `PATIENT_ID`, so the PHN→PATIENT_ID linkage can
be cross-checked against the waitlist as well as the patient table.

## Provincial Registry (22 columns, all seen)
`PROVINCIAL_REGISTRY_ID`, `PHN` (NUMBER — leading zero lost, hence the padding
rule), `BIRTH_DT` (TIMESTAMP_NTZ) with `BIRTH_DT_SRC`, **`SEX` (VARCHAR(1),
values F, M)**, `AGE_GRP_CD`, `POSTAL_CD`, `RHA`, `ACTIVE_COVERAGE`,
`DEATH_IND`, `BIRTH_IND`, `IN_MIGRATION_IND`, `OUT_MIGRATION_IND`,
`PERS_REAP_END_DATE` (+ `_SRC`, `_RSN_CODE`), `FYE`, `ETL_LOAD_DATE`. One row
per person per fiscal year, so DOB and SEX are taken as one value per PHN and
conflicts across years are counted (block 5).

## Working source decisions (provisional, pending blocks 5-6)
- **DOB primary:** Strata `patient.BIRTH_DATE` (covers waitlisted and placed
  alike); fallback Registry `BIRTH_DT`; `DEMOGRAPHIC_SOURCE` records which.
  Agreement between the two is to be measured before either is trusted.
- **Sex/gender primary: Registry `SEX`** (F/M). Strata `GENDER` is null; Epic
  is not used for a production demographic. No fallback: where the registry
  has no row the field is missing and counted as such.
- **Origin:** waitlist `CURRENT_LOCATION` at the census row nearest
  `DEMAND_DT`; `SOURCE_LOCATION` for admission-only events. Confirmed columns.
- **Requested facility:** `SERVICE_PROVIDER_RATED_SITE` + `RATING` + `CARE_TYPE`
  on the waitlist. Confirmed columns.
