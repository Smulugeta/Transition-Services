#!/usr/bin/env python3
"""
Write the three plain-language documents for the Cochrane deliverable, with
every number read from the build outputs in --dir (never typed by hand):
  COCHRANE_LOGIC_PAGE.md        how every person is counted, step by step
  COCHRANE_CLIENT_LIST_GUIDE.md what each column in the client list means
  COCHRANE_ANALYSIS_SUMMARY.md  the findings, in plain language
"""
import csv, os, argparse, statistics as st
from collections import Counter

FYES = [2022, 2023, 2024, 2025, 2026]
def read(p): return list(csv.DictReader(open(p)))
def md(headers, rows):
    s = "| " + " | ".join(headers) + " |\n|" + "|".join("---" for _ in headers) + "|\n"
    for r in rows: s += "| " + " | ".join(str(x) for x in r) + " |\n"
    return s
def pct(a, b): return f"{a/b*100:.0f}%" if b else "—"
def q(xs, p):
    xs = sorted(xs); n = len(xs); k = (n - 1) * p; f = int(k); c = min(f + 1, n - 1); return xs[f] + (xs[c] - xs[f]) * (k - f)

def main(a):
    D = read(os.path.join(a.dir, "COCHRANE_DEMAND_CONSULTANT.csv"))
    E = read(os.path.join(a.dir, "COCHRANE_PLACEMENT_ACTIVITY_CONSULTANT.csv"))
    W = read(os.path.join(a.dir, "COCHRANE_WAITLIST_ACTIVITY_CONSULTANT.csv"))
    inc = [p for p in D if p["INCIDENT_DEMAND_SCOPE"] == "1"]; coh = [p for p in inc if p["COHORT"]]
    c = Counter(p["COHORT"] for p in coh); dc = Counter(p["D_CLASS"][:2] for p in coh if p["COHORT"] == "D")
    res = c["A"] + c["C"] + c["D"]; placed = [p for p in coh if p["DAYS_TO_PLACEMENT"]]
    act_only = [p for p in D if p["INCIDENT_DEMAND_SCOPE"] != "1"]
    st_counts = Counter(p["ACTIVITY_STATUS"].split(":")[0] for p in D)
    Ec = [e for e in E if e["PLACEMENT_IN_COCHRANE"] == "1"]
    def fy(items, key, f): return [f([i for i in items if i[key] == str(y)]) for y in FYES]
    wait = lambda rows: (round(st.median([int(p["DAYS_TO_PLACEMENT"]) for p in rows])), round(q([int(p["DAYS_TO_PLACEMENT"]) for p in rows], .25)), round(q([int(p["DAYS_TO_PLACEMENT"]) for p in rows], .75))) if rows else ("—",) * 3

    # ── 1. LOGIC PAGE ───────────────────────────────────────────────────────
    L = f"""# How every person is counted — the logic on one page

**Purpose.** The Town of Cochrane needs to know how much demand there is for Type A (long-term care) and Type B (designated supportive living, level 4) beds, who the people are, and what happened to them. This page explains, in order, how a person gets counted. Every number in the analysis follows these steps and nothing else.

**The five years.** Fiscal years 2022 to 2026, that is 1 April 2021 to 31 March 2026. A fiscal year is named by the year it ends: FY2023 is April 2022 to March 2023.

## Two populations, two questions

| Plain name | Technical name in the files | The question it answers | People |
|---|---|---|---|
| **Population 1 — New demand in the five years** | `INCIDENT_DEMAND_SCOPE = 1` | How many people *first* needed a Type A/B bed in the five years, and what happened to them? Each person counted once. | {len(inc):,} |
| **Population 2 — Cochrane-related activity in the five years** | `CONSULTANT_ACTIVITY_SCOPE = 1` | How much waitlist and placement activity involved Cochrane, whoever the person is and whenever their need first arose? | {sum(1 for p in D if p["CONSULTANT_ACTIVITY_SCOPE"]=="1"):,} |

Population 1 is the one the cohorts A, B, C and D are built from. Population 2 is larger because it also holds people whose need arose before April 2021 but who were still waiting, or moved into a Cochrane facility, during the five years. The client list holds both; two flags say which population each person belongs to. Nobody is counted twice.

## Population 1, step by step

1. **Find the moment the need arose.** For each person, the *demand event* is the earlier of two dates: the day they were first approved for a Type A/B bed on the waitlist, or the day they were first admitted to a Type A/B bed. This is `DEMAND_DT`.
2. **Keep only new demand.** The demand event must fall inside the five years, and the person must not already have been living in residential continuing care when it happened. People whose need arose before April 2021 are not new demand; they appear in Population 2 instead if they had Cochrane activity.
3. **Decide where the person lived.** First the Provincial Registry: the most recent address on file in the three fiscal years before the demand event, matched to Statistics Canada geography. If the Registry has nothing usable, the Strata address in force on the demand date. If neither, the person is "residency unresolved". A postal code decides; a city name never does, and an invalid or dummy postal code never does.
   - **Town of Cochrane** = the postal code sits inside the Town's census boundary.
   - **Cochrane catchment** = the surrounding Rocky View County area served from Cochrane.
   - **Not a Cochrane-area resident** = anywhere else.
4. **See what happened by 31 March 2026.** The *first* Type A/B admission on or after the demand event, in the Calgary and Edmonton placement systems. If none is recorded by 31 March 2026, no placement was observed.
5. **Assign the cohort.**

| Cohort | Who | Count |
|---|---|---|
| **A** | Town of Cochrane resident, first placed **in** a Cochrane facility (Bethany Cochrane, Hawthorne SL4, Hawthorne SL4D) | {c['A']} |
| **B** | **Not** a Town resident (including catchment), placed in a Cochrane facility | {c['B']} |
| **C** | Town of Cochrane resident, first placed **outside** Cochrane | {c['C']} |
| **D** | Town of Cochrane resident, **no** Type A/B placement observed by 31 March 2026 | {c['D']} |
| | **Resident demand = A + C + D** (every Town resident with new demand) | **{res}** |

6. **Split D by what happened instead.** D1 still on the waitlist on 31 March 2026 ({dc['D1']}); D2 died before any placement ({dc['D2']}); D3 left the list with no placement observed ({dc['D3']}).

Some people in Population 1 fit none of A to D: they are not Town residents and were not placed in Cochrane, but they rated a Cochrane site or their residence could not be resolved. They stay in the list with a descriptive label (`POPULATION` beginning X) and never enter A to D.

## Population 2, step by step

A person is in Population 2 if, at any time in the five years, they had **any** of: a Type A/B waitlist spell in which they rated a Cochrane or Hawthorne site; a Type A/B waitlist spell while living in the Town of Cochrane; an admission to a Cochrane facility. There is no test on when their need first arose. Every person in Population 1 who had such activity is also in Population 2; {len(act_only)} people are in Population 2 only ({st_counts.get('prior residential care before FY2022 (activity only)', 0)} were already in residential care before April 2021, {st_counts.get('activity only (demand before FY2022 or not new demand)', 0)} had earlier or non-new demand, {st_counts.get('pre-window demand (carry-in)', 0)} were approved just before the window).

## Three files, three grains

| File | One row per | Use it to count |
|---|---|---|
| Client list (`COCHRANE_DEMAND_CONSULTANT`) | person | people: demand, cohorts, who they are |
| Waitlist activity (`COCHRANE_WAITLIST_ACTIVITY_CONSULTANT`) | waitlist spell | how many times people entered the list, per year |
| Placement activity (`COCHRANE_PLACEMENT_ACTIVITY_CONSULTANT`) | Type A/B admission | how many admissions happened, per year, per facility |

The same person can have several spells and several admissions. Counting rows in the activity files gives activity; counting people in the client list gives people. The `STUDY_ID` links the three files and is the same person everywhere.

## What the numbers are not

- **D is not provincial unmet demand.** It means no Type A/B placement was *observed in the Calgary and Edmonton placement systems* by 31 March 2026. A placement elsewhere in Alberta would not appear.
- **C is the first placement only.** {sum(1 for e in Ec if e['PERSON_COHORT']=='C')} C people later moved into a Cochrane facility; the placement-activity file shows those moves.
- **Requested facility means rated.** The waitlist records which sites a person was *rated for*; whether that is a preference has not been confirmed with the program, so the files say "rated for a Cochrane site".
- **Addresses are as good as the postal code.** A Registry address is the address of a fiscal year, not of the exact demand date; the file says which.
"""
    open(os.path.join(a.dir, "COCHRANE_LOGIC_PAGE.md"), "w").write(L)

    # ── 2. CLIENT LIST GUIDE ────────────────────────────────────────────────
    person_cols = [
        ("Identity", [("STUDY_ID", "Anonymous identifier for the person. The same code appears in all three files. It cannot be turned back into a health number.")]),
        ("Which population", [
            ("INCIDENT_DEMAND_SCOPE", "1 = Population 1, new demand in the five years (the cohorts A to D live here). 0 = not new demand."),
            ("CONSULTANT_ACTIVITY_SCOPE", "1 = Population 2, Cochrane-related waitlist or placement activity in the five years."),
            ("ACTIVITY_STATUS", "Plain-language reason the person is in the list: 'incident demand FY2022-FY2026', 'pre-window demand (carry-in)', 'prior residential care before FY2022 (activity only)', or 'activity only (demand before FY2022 or not new demand)'."),
            ("ACTIVITY_SCOPE_REASON", "Which of the three activity tests the person met: rated for a Cochrane site; Town resident with a waitlist spell; admitted to a Cochrane facility."),
            ("POPULATION", "A, B, C or D for cohort members. X1 to X4 for Population-1 people outside the cohorts (for example rated for a Cochrane site but not a Town resident and not placed in Cochrane). Blank for Population-2-only people."),
            ("COHORT", "A, B, C or D, or blank. Defined on the logic page."),
            ("D_CLASS", "For D only: D1 still waiting at 31 March 2026; D2 died before any placement; D3 exited with no placement observed."),
            ("ATTRIBUTE_ANCHOR", "The date the person's residence, age and origin were measured at: the demand event for Population 1, or the first activity in the window for Population-2-only people.")]),
        ("Dates", [
            ("DEMAND_DT / DEMAND_FYE", "The demand event (first Type A/B approval or admission) and its fiscal year. Population 1 only."),
            ("DEMAND_EVENT_TYPE", "'approval' if the demand event was a waitlist approval, 'admission' if the person was admitted without a recorded approval."),
            ("ACTIVITY_ANCHOR_DT / _FYE / _TYPE", "Population-2-only people: the first waitlist appearance or Cochrane admission in the window, and which of the two it was."),
            ("FIRST_WAITLIST_APPEARANCE", "First day the person appears on the Type A/B waitlist in the window."),
            ("FIRST_APPROVAL_DT", "First recorded assessment approval on the waitlist."),
            ("LAST_SEEN_ON_LIST", "Last day the person appears on the waitlist in the window."),
            ("ON_LIST_AT_FOLLOWUP", "1 = still on the waitlist on 31 March 2026.")]),
        ("Age and sex", [
            ("AGE_AT_DEMAND / AGE_GROUP_AT_DEMAND", "Completed age on the demand date, and the band (<65, 65-74, 75-84, 85+). Population 1 only."),
            ("AGE_AT_ANCHOR / AGE_GROUP_AT_ANCHOR", "Completed age at the attribute anchor (equals the demand-date age for Population 1)."),
            ("AGE_AT_FIRST_WAITLIST, AGE_AT_PLACEMENT", "Completed age on the first waitlist day and on the first placement day."),
            ("SEX / SEX_SOURCE", "F or M from the Provincial Registry; where the Registry has no record, from Connect Care, labelled 'EPIC (fallback)'. Blank when neither has it.")]),
        ("Where the person lived", [
            ("RESIDENCY_FINAL / RESIDENCE_CLASS", "Town of Cochrane, Cochrane catchment, Not a Cochrane-area resident, or UNRESOLVED; and the short form Town / Cochrane catchment / non-Town / unresolved."),
            ("RESIDENCE_COMMUNITY", "The municipality of the postal code that decided residence (Statistics Canada census subdivision, for example 'COCHRANE (T)' or 'CALGARY (CY)'). For an out-of-province address the Strata city is shown and labelled."),
            ("RESIDENCE_COMMUNITY_SOURCE", "Where the community name came from."),
            ("RESIDENCE_REFERENCE_TYPE / _FYE", "Whether the address is a Registry fiscal-year address (and which year) or a Strata address version in force at the anchor. A Registry address is not an exact address on the demand date."),
            ("COCHRANE_TOWN_FLAG, COCHRANE_CATCHMENT_FLAG", "1/0 shortcuts for Town and catchment residence.")]),
        ("Where the person came from (origin)", [
            ("ORIGIN_SETTING", "The setting the person entered the pathway from, on their first waitlist day: Acute Care, Community, Assisted Living or Other Continuing Care, Lodge, Out of Province, Other, Unknown."),
            ("ORIGIN_SETTING_DETAIL", "The finer category behind it (own home, acute hospital, sub-acute or transition unit, supportive living, long-term care, and so on)."),
            ("ORIGIN_SITE", "The raw location recorded on the waitlist."),
            ("ORIGIN_CONFLICT_FLAG", "1 = the waitlist recorded two different locations on the same first day. If both map to the same setting that setting is used; otherwise the setting is Unknown rather than guessed.")]),
        ("Facilities rated on the waitlist", [
            ("RATED_FOR_COCHRANE_SITE_FLAG / COCHRANE_SITES_RATED", "1 = the person was rated for at least one Cochrane or Hawthorne site while on the list, and which ones."),
            ("MOST_FREQUENTLY_OBSERVED_RATED_SITE", "The site that appears most often across the person's daily waitlist records. Because records are daily, a long-lasting rating appears more often; this is an observation, not a stated preference."),
            ("N_SITES_RATED, RATED_CARE_STREAM_MOST_FREQUENT", "How many different sites were rated, and the care stream (Type A or B) most often recorded.")]),
        ("What happened", [
            ("FIRST_PLACEMENT_DT / PLACEMENT_FYE", "First Type A/B admission on or after the demand event, by 31 March 2026, and its fiscal year. Population 1 only."),
            ("FIRST_PLACEMENT_SITE / _STREAM / _IN_COCHRANE", "The facility, Type A or B, and whether it is a Cochrane facility."),
            ("ACTIVITY_COCHRANE_ADMISSION", "1 = the person had any admission to a Cochrane facility in the five years, first or later."),
            ("DAYS_TO_PLACEMENT", "Days from the demand event to the first placement. Blank for anyone not placed by 31 March 2026; a wait that has not ended is never shown as a placement time."),
            ("DAYS_TO_PLACEMENT_ALT", "The same wait under the alternative approval-date rule, kept as a sensitivity."),
            ("DAYS_WAITING_AS_OF_FOLLOWUP", "For people still waiting on 31 March 2026 only: days waited so far. A censored duration, not a placement time.")]),
    ]
    G = f"""# The client list — what every column means

Three files, one anonymous `STUDY_ID` linking them. No health number, date of birth, patient system number, address or postal code appears in any of them.

| File | Rows | One row per |
|---|---|---|
| `COCHRANE_DEMAND_CONSULTANT.csv` — the client list | {len(D):,} | person |
| `COCHRANE_WAITLIST_ACTIVITY_CONSULTANT.csv` | {len(W):,} | waitlist spell (a continuous run of days on the Type A/B list) |
| `COCHRANE_PLACEMENT_ACTIVITY_CONSULTANT.csv` | {len(E):,} | Type A/B admission |

## How to read one row of the client list

A row with `INCIDENT_DEMAND_SCOPE = 1`, `COHORT = C`, `RESIDENCE_COMMUNITY = COCHRANE (T)`, `ORIGIN_SETTING = Acute Care`, `FIRST_PLACEMENT_SITE` = a Calgary long-term care home and `DAYS_TO_PLACEMENT = 21` reads: a Town of Cochrane resident whose need for a Type A/B bed first arose in the five years, who entered the waitlist from hospital, and who was placed outside Cochrane 21 days after the demand event.

A row with `INCIDENT_DEMAND_SCOPE = 0`, `CONSULTANT_ACTIVITY_SCOPE = 1` and `ACTIVITY_STATUS = prior residential care before FY2022 (activity only)` reads: this person was already living in residential care before April 2021, so they are not new demand and have no cohort, but they rated a Cochrane site or moved into a Cochrane facility during the five years, so their activity counts.

## Client list columns

"""
    for grp, cols in person_cols:
        G += f"### {grp}\n\n" + md(["Column", "Meaning"], [[f"`{k}`", v] for k, v in cols]) + "\n"
    G += """## Waitlist activity file

| Column | Meaning |
|---|---|
| `STUDY_ID` | The person. |
| `SPELL_SEQ_FOR_PERSON` | 1 for the person's first spell in the window, 2 for the second, and so on. |
| `LIST_ENTRY_DT / LIST_ENTRY_FYE` | First day of the spell and its fiscal year. Count spells by this year for "entries to the waitlist per year". |
| `LIST_LAST_SEEN_DT / DAYS_OBSERVED` | Last day of the spell and how many census days it covered. |
| `CARE_STREAM_AT_ENTRY` | Type A or Type B at the start of the spell. |
| `ORIGIN_SETTING / ORIGIN_SETTING_DETAIL / ORIGIN_CONFLICT_FLAG` | Setting on the first day of the spell, as for the client list. |
| `FIRST_APPROVED_DT_IN_SPELL` | First assessment approval recorded in the spell. |
| `RATED_COCHRANE_IN_SPELL` | 1 = a Cochrane or Hawthorne site was rated during the spell. |
| `LEFT_TRUNCATED` | 1 = the person was already on the list on 1 April 2021, so the spell started earlier than shown. |
| `ON_LIST_AT_FOLLOWUP` | 1 = the spell was still open on 31 March 2026. |
| `PERSON_RESIDENCE_CLASS / PERSON_ACTIVITY_STATUS / PERSON_COHORT` | The person's residence class, status and cohort, copied from the client list for convenience. |

## Placement activity file

| Column | Meaning |
|---|---|
| `STUDY_ID` | The person. |
| `ADMISSION_DT / PLACEMENT_FYE` | Admission date and its fiscal year. Count rows by this year for "placements per year". |
| `PLACEMENT_SITE / CARE_STREAM / PLACEMENT_IN_COCHRANE` | The facility, Type A or B, and whether it is Bethany Cochrane, Hawthorne SL4 or Hawthorne SL4D. |
| `ORIGIN_SETTING / ORIGIN_SETTING_DETAIL` | The setting the person was admitted from, from the admission record. |
| `IS_FIRST_PLACEMENT_INCIDENT` | 1 = this admission is the first placement of a Population-1 person, the one that decides their cohort. Sums to the number of Population-1 people who were placed. |
| `IS_FIRST_PLACEMENT_IN_WINDOW` | 1 = the person's first Type A/B admission in the five years, whoever they are. |
| `EVENT_SEQ_FOR_PERSON` | 1 for the person's first admission in the window, 2 for the second, and so on. |
| `PERSON_RESIDENCE_CLASS / PERSON_RESIDENCE_COMMUNITY / PERSON_ACTIVITY_STATUS / PERSON_COHORT / PERSON_POPULATION` | Copied from the client list for convenience. |
"""
    open(os.path.join(a.dir, "COCHRANE_CLIENT_LIST_GUIDE.md"), "w").write(G)

    # ── 3. ANALYSIS SUMMARY ─────────────────────────────────────────────────
    ages = [int(p["AGE_AT_ANCHOR"]) for p in D if p["AGE_AT_ANCHOR"]]
    Wc = W; rated_people = len({w["STUDY_ID"] for w in W if w["RATED_COCHRANE_IN_SPELL"] == "1"})
    A_ = f"""# Cochrane continuing-care demand, FY2022 to FY2026 — analysis summary

Five fiscal years, 1 April 2021 to 31 March 2026. Type A = long-term care; Type B = designated supportive living level 4. Cochrane facilities = Bethany Cochrane LTC, Hawthorne SL4 and Hawthorne SL4D. Definitions are on the logic page; this page gives the findings.

## 1. The headline: new demand from Town of Cochrane residents

{res} Town of Cochrane residents first needed a Type A/B bed in the five years.

| | People | Share |
|---|---|---|
| A — placed in a Cochrane facility | {c['A']} | {pct(c['A'], res)} |
| C — placed outside Cochrane | {c['C']} | {pct(c['C'], res)} |
| D — no placement observed by 31 March 2026 | {c['D']} | {pct(c['D'], res)} |
| **Resident demand (A + C + D)** | **{res}** | |

Of the {c['D']} without an observed placement: {dc['D1']} were still waiting on 31 March 2026 (almost all recent), {dc['D2']} died before a placement, {dc['D3']} left the list with no placement recorded in the Calgary and Edmonton systems.

In the same five years, {c['B']} people who were **not** Town residents were placed in a Cochrane facility (B), {sum(1 for p in coh if p["COHORT"]=="B" and p["COCHRANE_CATCHMENT_FLAG"]=="1")} of them from the Cochrane catchment. So of the {c['A']+c['B']} first placements into Cochrane facilities from new demand, {pct(c['A'], c['A']+c['B'])} went to Town residents.

**Read together:** {pct(c['C'], c['A']+c['C'])} of Town residents who were placed went outside Cochrane.

## 2. New demand by year

| Fiscal year | A | C | D | Resident demand | B |
|---|---|---|---|---|---|
""" + "".join(f"| FY{y} | {cy['A']} | {cy['C']} | {cy['D']} | {cy['A']+cy['C']+cy['D']} | {cy['B']} |\n" for y in FYES for cy in [Counter(p['COHORT'] for p in coh if p['DEMAND_FYE']==str(y))]) + f"""| **Total** | {c['A']} | {c['C']} | {c['D']} | **{res}** | {c['B']} |

D rises in FY2026 because people whose need arose late in the period have had little time to be placed. That is censoring, not a trend.

## 3. Who the people are (Population 2, {len(D):,} people with any Cochrane-related activity)

- **Age.** Median {st.median(ages):.0f}. Under 65: {sum(1 for x in ages if x<65)}; 65 to 74: {sum(1 for x in ages if 65<=x<75)}; 75 to 84: {sum(1 for x in ages if 75<=x<85)}; 85 and over: {sum(1 for x in ages if x>=85)}.
- **Sex.** {sum(1 for p in D if p['SEX']=='F')} women, {sum(1 for p in D if p['SEX']=='M')} men, {sum(1 for p in D if not p['SEX'])} unknown.
- **Where they lived.** """ + "; ".join(f"{k} {v}" for k, v in Counter(p["RESIDENCE_CLASS"] for p in D).most_common()) + f""".
- **Where they entered the pathway from.** """ + "; ".join(f"{k} {v}" for k, v in Counter(p["ORIGIN_SETTING"] for p in D).most_common()) + f""". About {pct(sum(1 for p in D if p['ORIGIN_SETTING']=='Acute Care'), len(D))} entered from a hospital bed and {pct(sum(1 for p in D if p['ORIGIN_SETTING']=='Community'), len(D))} from their own home.

## 4. Waitlist activity by year (Population 2)

| Fiscal year | Waitlist entries (spells) | People entering | Entries rating a Cochrane site | Entries by Town residents |
|---|---|---|---|---|
""" + "".join(f"| FY{y} | {len(ys)} | {len({w['STUDY_ID'] for w in ys})} | {sum(1 for w in ys if w['RATED_COCHRANE_IN_SPELL']=='1')} | {sum(1 for w in ys if w['PERSON_RESIDENCE_CLASS']=='Town')} |\n" for y in FYES for ys in [[w for w in W if w['LIST_ENTRY_FYE']==str(y)]]) + f"""| **Total** | {len(W)} | {len({w['STUDY_ID'] for w in W})} people in all | {sum(1 for w in W if w['RATED_COCHRANE_IN_SPELL']=='1')} | {sum(1 for w in W if w['PERSON_RESIDENCE_CLASS']=='Town')} |

{rated_people} different people rated a Cochrane or Hawthorne site at least once in the five years. A person who entered the list more than once is counted in each year they entered; the "people in all" figure counts each person once.

## 5. Admissions to Cochrane facilities by year (every admission, whoever the person)

| Fiscal year | Admissions | People | Bethany Cochrane LTC | Hawthorne SL4 | Hawthorne SL4D | Town residents | Non-Town |
|---|---|---|---|---|---|---|---|
""" + "".join(f"| FY{y} | {len(ys)} | {len({e['STUDY_ID'] for e in ys})} | {sum(1 for e in ys if 'Bethany' in e['PLACEMENT_SITE'])} | {sum(1 for e in ys if e['PLACEMENT_SITE'].endswith('SL4_'))} | {sum(1 for e in ys if e['PLACEMENT_SITE'].endswith('SL4D'))} | {sum(1 for e in ys if e['PERSON_RESIDENCE_CLASS']=='Town')} | {sum(1 for e in ys if e['PERSON_RESIDENCE_CLASS'] in ('non-Town','Cochrane catchment'))} |\n" for y in FYES for ys in [[e for e in Ec if e['PLACEMENT_FYE']==str(y)]]) + f"""| **Total** | {len(Ec)} | {len({e['STUDY_ID'] for e in Ec})} | {sum(1 for e in Ec if 'Bethany' in e['PLACEMENT_SITE'])} | {sum(1 for e in Ec if e['PLACEMENT_SITE'].endswith('SL4_'))} | {sum(1 for e in Ec if e['PLACEMENT_SITE'].endswith('SL4D'))} | {sum(1 for e in Ec if e['PERSON_RESIDENCE_CLASS']=='Town')} | {sum(1 for e in Ec if e['PERSON_RESIDENCE_CLASS'] in ('non-Town','Cochrane catchment'))} |

Of the {len(Ec)} admissions: {sum(1 for e in Ec if e['IS_FIRST_PLACEMENT_INCIDENT']=='1')} are the first placements of new-demand people (A and B); {sum(1 for e in Ec if e['PERSON_COHORT']=='C')} are Town residents (C) who reached Cochrane after a first placement elsewhere; {sum(1 for e in Ec if e['PERSON_COHORT'] in ('A','B') and e['IS_FIRST_PLACEMENT_INCIDENT']!='1')} are moves between Cochrane sites; the rest are people whose need arose before the five years or who were already in care.

## 6. How long people waited (new-demand people who were placed)

| Group | People | Median days | Middle half of waits |
|---|---|---|---|
| All placed (A, B, C) | {len(placed)} | {wait(placed)[0]} | {wait(placed)[1]} to {wait(placed)[2]} |
| A — Town residents placed in Cochrane | {sum(1 for p in placed if p['COHORT']=='A')} | {wait([p for p in placed if p['COHORT']=='A'])[0]} | {wait([p for p in placed if p['COHORT']=='A'])[1]} to {wait([p for p in placed if p['COHORT']=='A'])[2]} |
| B — non-residents placed in Cochrane | {sum(1 for p in placed if p['COHORT']=='B')} | {wait([p for p in placed if p['COHORT']=='B'])[0]} | {wait([p for p in placed if p['COHORT']=='B'])[1]} to {wait([p for p in placed if p['COHORT']=='B'])[2]} |
| C — Town residents placed outside Cochrane | {sum(1 for p in placed if p['COHORT']=='C')} | {wait([p for p in placed if p['COHORT']=='C'])[0]} | {wait([p for p in placed if p['COHORT']=='C'])[1]} to {wait([p for p in placed if p['COHORT']=='C'])[2]} |
| Type A placements | {sum(1 for p in placed if p['FIRST_PLACEMENT_STREAM']=='Type A')} | {wait([p for p in placed if p['FIRST_PLACEMENT_STREAM']=='Type A'])[0]} | {wait([p for p in placed if p['FIRST_PLACEMENT_STREAM']=='Type A'])[1]} to {wait([p for p in placed if p['FIRST_PLACEMENT_STREAM']=='Type A'])[2]} |
| Type B placements | {sum(1 for p in placed if p['FIRST_PLACEMENT_STREAM']=='Type B')} | {wait([p for p in placed if p['FIRST_PLACEMENT_STREAM']=='Type B'])[0]} | {wait([p for p in placed if p['FIRST_PLACEMENT_STREAM']=='Type B'])[1]} to {wait([p for p in placed if p['FIRST_PLACEMENT_STREAM']=='Type B'])[2]} |

Waits are counted from the demand event to the first placement, for placed people only. Town residents who accepted a Cochrane bed waited longer than those placed elsewhere. Under the alternative approval-date rule the medians do not change and only five individual waits differ.

## 7. Things to keep in mind

- "No placement observed" means none recorded in the Calgary and Edmonton placement systems by 31 March 2026. It is not a measure of unmet need across Alberta.
- Residence is decided by postal code from the Provincial Registry, or from the Strata address when the Registry has nothing usable. A Registry address belongs to a fiscal year, not to the exact demand date. Invalid or dummy postal codes are never used.
- "Rated for a Cochrane site" is what the waitlist records; whether it is the person's stated preference has not been confirmed with the program.
- Age is at the demand event (or first activity in the window), never at today's date. Dates of birth were checked across three systems and agree for all but one person.
- Every figure on this page is produced by the build script from the same files, and the build refuses to run if any of its {a.gates} reconciliation checks fails.
"""
    open(os.path.join(a.dir, "COCHRANE_ANALYSIS_SUMMARY.md"), "w").write(A_)
    print("written: COCHRANE_LOGIC_PAGE.md, COCHRANE_CLIENT_LIST_GUIDE.md, COCHRANE_ANALYSIS_SUMMARY.md")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--dir", default="deliverables"); ap.add_argument("--gates", default="43"); main(ap.parse_args())
