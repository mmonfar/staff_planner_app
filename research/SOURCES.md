# Evidence Register

**Generated from `research/evidence.db` — do not edit by hand.**
Regenerate with `python research/ingest.py report`.

## Parameters

| key | value | unit | binding | confidence | source |
|---|---|---|---|---|---|
| `acuity.cmi.baseline` | 1.0 | index | default | partial | cms-cmi |
| `acuity.cmi_to_dnw.coefficients_transfer` | false | boolean | hard | verified | yang-2023-bmcnurs |
| `acuity.cmi_to_dnw.form` | DNW = 92.3 + 4.8*CMI + 2.4*CMI^2 | minutes/patient/day | default | verified | yang-2023-bmcnurs |
| `acuity.cmi_to_dnw.r_squared` | 0.627 | R^2 | soft | verified | yang-2023-bmcnurs |
| `acuity.niw.exists` | true | boolean | soft | partial | knauf-2006-niw |
| `gap.cmi_to_nursing_workload` | RESOLVED-AS-FORM | - | hard | partial | yang-2023-bmcnurs |
| `acuity.nas.observed_mean` | 66.2 | % (pooled); 45.5-101.8 across 19 adult ICUs | soft | verified | nas-icu-workload |
| `acuity.nas.point_value` | 4.8 | minutes of RN FTE time per NAS point | soft | verified | nas-icu-workload |
| `acuity.nas.range` | 0 - 176.8 | % of one nurse's 24h per patient | soft | verified | nas-icu-workload |
| `acuity.snct.hppd_by_level` | L0=4.35, L1a=6.10, L1b=7.55, L2=8.65, L3=26.2 | hours/patient/day | soft | verified | snct-multipliers-nihr |
| `acuity.snct.hppd_by_level_aau` | L0=5.58, L1a=7.29, L1b=9.13, L2=9.92, L3=26.2 | hours/patient/day | soft | verified | snct-multipliers-nihr |
| `acuity.snct.hppd_range` | 5.9-10.2 | hours/patient/day | soft | verified | snct-nihr-2020 |
| `acuity.snct.specialling_multiplier` | 5.47 | WTE multiplier | soft | verified | snct-nihr-2020 |
| `demand.establishment_policy` | p90 | percentile of demand | soft | verified | snct-nihr-2020 |
| `demand.mobility_factor` | 1.2 | multiplier | default | verified | yang-2023-bmcnurs |
| `demand.rest_factor` | 1.46 | multiplier | default | verified | yang-2023-bmcnurs |
| `demand.snct_uplift` | 0.22 | fraction | soft | verified | snct-multipliers-nihr |
| `gap.snct_level_multipliers` | RESOLVED | multiplier per level | soft | verified | snct-multipliers-nihr |
| `gap.ca_medsurg_ratio` | 1:5 or 1:6 | nurse:patients | hard | unverified | ca-title22-70217 |
| `quality.mortality_or_per_10pct_degree_nurses` | 0.929 | odds ratio (95% CI 0.886-0.973) | soft | verified | aiken-2014-lancet |
| `quality.mortality_or_per_extra_patient` | 1.068 | odds ratio (95% CI 1.031-1.106) | soft | verified | aiken-2014-lancet |
| `quality.staffing_gap_vs_adverse_events` | -0.567 | Pearson r (p = 0.021) | soft | verified | yang-2023-bmcnurs |
| `quality.staffing_gap_vs_satisfaction` | 0.653 | Pearson r (p = 0.006) | soft | verified | yang-2023-bmcnurs |
| `skillmix.single_ratio_exists` | false | boolean | hard | partial | nice-sg1-2014 |
| `wellbeing.max_night_hours` | 8 | hours per 24h (averaged) | hard | partial | ewtd-2003-88-ec |
| `wellbeing.max_weekly_hours` | 48 | hours/week (averaged) | hard | partial | ewtd-2003-88-ec |
| `wellbeing.min_daily_rest` | 11 | consecutive hours per 24h | hard | partial | ewtd-2003-88-ec |
| `wellbeing.min_weekly_rest` | 24 | uninterrupted hours per 7 days | hard | partial | ewtd-2003-88-ec |

## Sources

### `yang-2023-bmcnurs`
- **Construction and application of a nursing human resource allocation model based on the case mix index**
- BMC Nursing 22:466 · 2023 · CN · study
- <https://doi.org/10.1186/s12912-023-01632-y>
- retrieved 2026-09-18 via web
- Yang Y, He M, Yang Y, et al. THE CMI-to-nursing bridge. 271 inpatients, 36 nurses, one hepatobiliary surgery department, Mianyang Central Hospital, Aug-Sep 2022. Single-department single-country study - the functional FORM is reusable, the COEFFICIENTS are not.

### `cms-cmi`
- **Case Mix Index: average MS-DRG relative weight across a hospital's inpatient discharges**
- CMS / industry reference · 2026 · US · reference
- <https://www.definitivehc.com/resources/glossary/case-mix-index>
- retrieved 2026-09-18 via web
- Definition consistent across sources. CMI 1.0 = Medicare baseline complexity. NOTE: CMI is a REIMBURSEMENT weight, not a nursing-workload weight - see gap.cmi_to_nursing_workload.

### `ca-title22-70217`
- **California Code of Regulations Title 22 s.70217, licensed nurse-to-patient ratios (AB 394, 1999)**
- California DPH · 1999 · US · statute
- <https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=199920000AB394>
- retrieved 2026-09-18 via web
- GAP: sources disagree between 1:5 and 1:6 for medical/surgical (likely the 2005 phase-down). Primary CDPH and CHCF fetches failed (DNS/timeout). Do not encode until resolved.

### `ewtd-2003-88-ec`
- **Directive 2003/88/EC concerning certain aspects of the organisation of working time**
- European Parliament and Council · 2003 · EU · statute
- <https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=celex:32003L0088>
- retrieved 2026-09-18 via web
- Healthcare derogations exist (opt-out, reference periods); treat limits as defaults to be overridden per jurisdiction, not absolutes.

### `nas-icu-workload`
- **Nursing Activities Score: 23-item instrument scoring percentage of one nurse's 24h per patient**
- NAS literature incl. systematic review of 70 studies / 56,000+ ICU patients · 2025 · INTL · standard
- <https://www.scielo.br/j/reeusp/a/pWCHRkfXMtswmznjG76qf5v/>
- retrieved 2026-09-18 via web
- Independent corroboration from critical care: nursing time per patient ranges 0-176.8% of one nurse-day.

### `nice-sg1-2014`
- **Safe staffing for nursing in adult inpatient wards in acute hospitals (SG1)**
- NICE · 2014 · UK · guideline
- <https://www.nice.org.uk/guidance/sg1>
- retrieved 2026-09-18 via web
- Primary chapters returned 403; content from NICE's own indexed pages. Establishes that NO single ratio fits all wards - each ward sets its own establishment. This is the mandate for an optimiser rather than a fixed-ratio calculator.

### `snct-nihr-2020`
- **The Safer Nursing Care Tool as a guide to nurse staffing requirements on hospital wards: observational and modelling study**
- NIHR Journals Library (HS&DR 8.16) · 2020 · UK · study
- <https://www.ncbi.nlm.nih.gov/books/NBK555316/>
- retrieved 2026-09-18 via web
- Key design input: establishments set to MEAN demand under-deliver; meeting demand 90% of the time gave the best outcomes.

### `snct-multipliers-nihr`
- **SNCT acuity multipliers and HPPD by dependency level (Table 31)**
- NIHR Journals Library (HS&DR 8.16), Methodological details · 2020 · UK · standard
- <https://www.ncbi.nlm.nih.gov/books/NBK555317/>
- retrieved 2026-09-18 via web
- The acuity ladder. Level 0 -> Level 3 spans 4.35 -> 26.2 HPPD, a 6.0x spread. Cross-validates with the separately retrieved specialling figure (5.47 multiplier = 24 HPPD): both imply the same WTE-to-HPPD conversion of ~0.228.

### `knauf-2006-niw`
- **Nursing Cost by DRG: Nursing Intensity Weights**
- Policy, Politics & Nursing Practice · 2006 · US · study
- <https://doi.org/10.1177/1527154406297910>
- retrieved 2026-09-18 via web
- Knauf RA, Ballard K, Mossman PN, Lichtig LK. The principled DRG->nursing bridge: Nursing Intensity Weights allocate nursing cost per DRG. New York State is the only DRG system that identifies nursing separately. Full text not retrieved - abstract-level only.

### `aiken-2014-lancet`
- **Nurse staffing and education and hospital mortality in nine European countries: a retrospective observational study**
- The Lancet · 2014 · EU · study
- <https://doi.org/10.1016/S0140-6736(13)62631-8>
- retrieved 2026-09-18 via web
- Aiken LH, Sloane DM, Bruyneel L, et al. Lancet 383(9931):1824-1830. Numbers read from the UNIC research-portal abstract mirror; thelancet.com returned 403.

## Retrieval log

Every query run, including the ones that returned nothing — so gaps are
visible rather than silently missing.

| ran | tool | query | result |
|---|---|---|---|
| 2026-09-18 | WebSearch | CMS case mix index definition DRG relative weight | definition obtained, consistent across sources |
| 2026-09-18 | WebSearch | NICE safe staffing adult inpatient wards nursing hours per patient day | SG1 found; confirmed no universal ratio |
| 2026-09-18 | WebSearch | California AB 394 nurse to patient ratio medical surgical Title 22 | CONFLICT 1:5 vs 1:6 - logged as gap |
| 2026-09-18 | WebSearch | European Working Time Directive 2003/88/EC limits | 48h week / 11h rest / 8h night / 24h weekly obtained |
| 2026-09-18 | WebSearch | Safer Nursing Care Tool multipliers per acuity level | per-level multipliers NOT public - logged as gap |
| 2026-09-18 | WebSearch | Aiken 2014 Lancet nurse staffing mortality | study located |
| 2026-09-18 | WebFetch | nice.org.uk/guidance/sg1/chapter/Recommendations | FAILED 403 |
| 2026-09-18 | WebFetch | nice.org.uk/guidance/sg1/chapter/Safe-nursing-indicators | FAILED 403 |
| 2026-09-18 | WebFetch | ncbi.nlm.nih.gov/books/NBK555329 (SNCT methods) | specialling multiplier 5.47 equals 24 HPPD |
| 2026-09-18 | WebFetch | ncbi.nlm.nih.gov/books/NBK555316 (SNCT summary) | 5.9-10.2 HPPD range; p90 establishment policy |
| 2026-09-18 | WebFetch | pubmed.ncbi.nlm.nih.gov/24581683 | FAILED cookie wall |
| 2026-09-18 | WebFetch | thelancet.com PIIS0140-6736(13)62631-8 | FAILED 403 |
| 2026-09-18 | WebFetch | pure.unic.ac.cy Aiken abstract mirror | OR 1.068 and 0.929 with CIs obtained |
| 2026-09-18 | WebFetch | ulh.nhs.uk Shelford SNCT pack | FAILED DNS |
| 2026-09-18 | WebFetch | cdph.ca.gov AFL-08-07 | FAILED DNS |
| 2026-09-18 | WebFetch | chcf.org min nurse staffing ratios PDF | FAILED timeout |
| 2026-09-18 | WebSearch | nursing intensity weights DRG nursing care hours per case | NIW concept located (knauf-2006-niw); NY State only DRG system pricing nursing separately |
| 2026-09-18 | WebSearch | case mix index correlation nursing workload validity | FOUND THE BRIDGE: quadratic CMI-to-nursing-worktime model, R2 0.627 |
| 2026-09-18 | WebSearch | SNCT acuity level 0 1a 1b 2 3 multiplier table | confirmed 5 levels + 22% uplift; multipliers proprietary to Shelford |
| 2026-09-18 | WebSearch | RAFAELA OPCq nursing intensity classification | OPCq/PAONCIL located; 25.2 NCI points per nurse on adult wards |
| 2026-09-18 | WebSearch | Nursing Activities Score NAS ICU nursing time | 0-176.8% range, 4.8 min/point, pooled mean 66.2% obtained |
| 2026-09-18 | WebFetch | ncbi.nlm.nih.gov/books/NBK555317 (SNCT Table 31) | FULL MULTIPLIER TABLE OBTAINED - general wards and acute admissions units |
| 2026-09-18 | WebFetch | partnersinpaediatrics.org CYP-SNCT PDF | FAILED - unparseable PDF |
| 2026-09-18 | WebFetch | pmc.ncbi.nlm.nih.gov/articles/PMC10698983 (Yang 2023) | equation, R2, units, sample, staffing formula and outcome correlations all obtained |
| 2026-09-18 | WebFetch | pubmed.ncbi.nlm.nih.gov/17242393 (Knauf NIW) | FAILED cookie wall |
| 2026-09-18 | WebFetch | ncbi.nlm.nih.gov/pmc/articles/PMC10698983 | 301 redirect to pmc.ncbi.nlm.nih.gov |
