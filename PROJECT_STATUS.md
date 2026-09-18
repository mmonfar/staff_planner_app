# Staff Planner — Status Board

Maintained by the orchestrator session. Update on every completed task.

**Completion: 24 / 25 (96%). Scope-aware, licensed, CI'd.**

## The problem (restated 2026-09-18)

Find the **most appropriate staff mix** for a unit's **Case Mix Index**, subject
to **staff wellbeing** and **cost**. Three objectives that genuinely conflict.

This is a re-scope, not a tweak. Today `StaffPlanner` takes ratios as **input**
and scores two named scenarios — it is a calculator. The stated problem makes
ratios an **output**: the mix is the thing being solved for. The core
abstraction changes; the demand engine survives as the constraint function,
which is why tasks 5-7 are still required and not wasted.

### Formulation
- **Decision variables:** `x[role, shift]` — integer headcount, roles
  {SN, PN, HCA}. Optionally a binary for shift pattern (3x8 vs 2x12).
- **CMI drives demand, quadratically.** CMI is retained as the acuity index
  *because it is universally comparable* — DRG-based, so it travels across
  MS-DRG / G-DRG / AR-DRG / NordDRG systems. SNCT does not leave the UK.
  Form (yang-2023-bmcnurs): `DNW = 92.3 + 4.8*CMI + 2.4*CMI^2` min/patient/day.
  **Not linear** — a plain `HPPD x CMI` scaling is wrong even where it holds.
  CMI is a parameter, not a decision variable, so demand is computed before the
  solve and the MILP stays linear.
- **Coefficients are locally calibrated, never shipped.** The published
  coefficients fail cross-check against SNCT by ~2x (2.9 vs 5.9-10.2 HPPD).
  The form transfers; the numbers do not. SNCT's band is the validation gate on
  the output, not the driver.
- **Objectives:** (1) cost; (2) care quality — shortfall vs CMI-adjusted demand
  and SN skill-mix share; (3) wellbeing — overtime per nurse, consecutive
  nights, shift-length fatigue, load per nurse when short.
- **Hard constraints:** coverage >= CMI-adjusted demand; regulatory minimum SN
  share; max OT per nurse; optional budget ceiling.

### Method
**Exact MILP + epsilon-constraint -> exact Pareto front.** The space is tiny
(9-18 integer variables). Rule 0: exact before metaheuristic, and here exact is
also tractable, so a metaheuristic buys nothing and costs reproducibility.

**NSGA-II is the fallback, not the plan.** Escalate only if the wellbeing
objective turns genuinely nonlinear (fatigue in consecutive shifts often does),
or if scope extends from aggregate skill mix to **individual rostering**
(assigning named staff to dates) — that explodes combinatorially and MILP stops
being tractable. Aggregate mix = MILP. Individual roster = metaheuristic.

## Done
| # | Task | Evidence |
|---|---|---|
| 1 | Repo structure | `.gitignore`, `pyproject.toml`, pinned `requirements.txt` |
| 2 | Test harness | `tests/test_planner.py` — 8 pass, 4 strict xfail |
| 3 | UI-layer bugs | sidebar costs wired, `styles.css` loaded, dead code removed, figure leak closed |
| 4 | Method verdict | brain ledger, twice revised; exact-first ladder settled |
| 18 | Evidence store + standards research | `research/evidence.db` — 8 sources, 22 params, 21 retrievals logged |
| 5 | **Demand formula fixed** | per-shift summation; SN 20 FTE at 1:8/census 32, matches independent 24/7 check exactly |
| 6 | **Overtime model fixed** | overtime now reduces establishment; capped at real demand; `needs` and `costs` describe one plan |
| 7 | **Shift patterns tile 24h** | A is 8+8+8; `Model.__post_init__` rejects anything else |
| 8 | HPPD output gate | A 7.21, B 9.69 — both inside SNCT 5.9–10.2 |
| 19 | **Absence uplift** | annual leave and unplanned absence modelled separately; implied uplift 1.147 reported against the 1.46 benchmark |
| 20 | **Stochastic demand** | `app/stochastic.py` — NB census, Dirichlet acuity mix, p90 policy, analytic baseline gate |
| 12 | **Acuity baseline** | `app/acuity.py` — SNCT ladder L0 4.35 → L3 26.2 HPPD (6.0x); CMI tilts the mix, ladder converts to hours |
| 26 | **Scope of practice** | `app/roles.py` — 10 task categories, per-role capability, porter added; RN share now emerges rather than being imposed |
| 9 | **LICENSE** | Apache 2.0 |
| 10 | **CI** | `.github/workflows/tests.yml` — pytest on 3.11/3.12, plus a check that SOURCES.md is in step with evidence.db |
| 24 | **Optimiser surfaced in UI** | solved plan per shift, baseline-gate status, Pareto front chart + table, decision recorder |
| 25 | **Decision audit trail** | `app/audit.py` + `research/planning_log.db` — scenario, plan, gate status, evidence fingerprint, rationale, supersession |
| 23 | **Absence feedback wired** | understaffing raises sickness, which raises the establishment; `absence_is_endogenous` on by default |
| 15 | **Baseline gate** | `app/optimise.py` — random 271.2, hill-climb 231.6, MILP 206.4 on Model A |
| 16 | **MILP solver** | CBC via PuLP; per-shift coverage AND per-shift skill-mix floor; wellbeing carried through |
| 17 | **Exact Pareto front** | epsilon-constraint over the skill-mix floor; deduplicated, non-dominated |
| 13 | **Wellbeing index** | `app/wellbeing.py` — 5 studies, 17 sourced parameters; EWTD breach flags; endogenous absence loop |
| 21 | **UI rebuilt** | ratio-vs-demand verdict, demand distribution, acuity mix, case-mix sweep, evidence panel |
| 22 | **Uplift resolved** | sourced 22% (SNCT), single total, no double-count with `vacation_days` |

## Pending
| # | Task | Blocks | P |
|---|---|---|---|
| 21 | **Surface stochasticity in the UI** — the app still shows single numbers; p90 band, shortfall risk and gate status are computed but not displayed | — | P0 |
| 11 | MCP config: pin interpreter, drop duplicate defs (cross-repo) | — | P2 |
| 14 | NSGA-II — **only if** 16 proves intractable or wellbeing goes nonlinear | — | HOLD |

## Sequencing
5 -> 6 -> 7 land as one change (shared hour basis; splitting leaves the model
inconsistent). 8 verifies. Then 12 and 13 in parallel — both are modelling
tasks needing domain input, not code. Then 16, gated by 15. Then 17.
9, 10, 11 independent, any time. 14 stays on HOLD until 16 reports.

## Wellbeing findings that change the model
- **Absence is endogenous.** Understaffing raises sickness absence, which
  worsens understaffing (dallora-2025). `unplanned_absence` is still an
  exogenous input to `StochasticPlanner`; `wellbeing.absence_feedback()` exists
  but is not yet wired into establishment sizing. **Task 23, P1.**
- **Model B breaches the EWTD night-work default** and scores 79.9/100 against
  Model A's 100. Cheaper in money is not cheaper overall.
- **Cost and wellbeing are not purely opposed.** A richer RN mix lowers sickness
  absence (OR 0.98 per +10% RN hours), so it buys back part of its own cost.
  This matters for the Pareto front — the two objectives are not a clean
  trade-off everywhere.

## Open modelling questions
- **Neither ratio meets acuity-driven demand at p90 once CMI rises.** Model A is
  short at every case mix tested; Model B copes only at CMI 1.0. That gap is now
  the headline output, not a footnote.
- **Above CMI ~1.9 the demand HPPD leaves the SNCT band** (10.36 at CMI 2.0).
  Correct behaviour — a ward that acute is no longer a general ward — but the UI
  must say so rather than silently reporting a number.
- **RETRACTED: "CMI is a weak lever."** That came from a curve fitted inside one
  surgical specialty, where restricted acuity range attenuates the slope. The
  SNCT ladder spans 6.0x. Acuity is the dominant driver.
- **RESOLVED: roles are no longer interchangeable.** Demand splits across 10
  task categories and each role carries what it may perform versus assist with.
  The registered share now emerges at ~36% from restricted work alone.
- **Task profile is an assumption.** How care hours divide across categories is
  not an activity study, and it drives how much of the establishment must be
  registered. Replace with local observation; vary it by unit type.
- **Only the UK catalogue is populated**, and from a considered reading rather
  than an NMC extract. No catalogue is marked verified.
- **Assumptions still needing local data:** `census_dispersion` 1.6,
  `cmi_sd` 0.15, `mix_concentration` 40, `cmi_tilt` 1.0, and `DEFAULT_BASE_MIX`.
  The tilt and base mix matter most — they set how CMI maps onto the ladder.

## Gates
- **5-7** done only when the 4 xfails flip green **without** editing assertions.
- **12** UNBLOCKED. A validated CMI→nursing-worktime mapping exists, so CMI
  stays the portable index as intended. Remaining need is **calibration data**
  (local CMI and nursing-time observations), not method. Until calibrated, ship
  the form with the published coefficients clearly flagged as placeholder and
  the SNCT band enforced as a hard output gate.
- **Output gate:** any computed HPPD outside 5.9–10.2 is a bug signal, not a
  result. Fail loudly.
- **13** limits are now sourced (EWTD) — but all four are `partial` confidence
  and healthcare derogations apply. Needs the owner's jurisdiction to confirm.
- **16-17** unreportable until 15's baselines are beaten on equal budget. If a
  method cannot beat blind random sampling, the objective or representation is
  broken — fix that, do not tune the method.
- No weighted "safety-adjusted cost" scalar. Weighted sums cannot recover
  solutions on non-convex regions of the Pareto frontier.

## Queued: task profile activity study
`DEFAULT_TASK_PROFILE` in `app/roles.py` divides care hours across the ten task
categories. It is an estimate, not an activity study, and it directly sets how
much of the establishment must be registered — a profile with more medication
and assessment forces more registered hours, one with more personal care forces
fewer. It is therefore the single assumption with the most leverage over the
answer.

To resolve: a work-sampling or time-and-motion study on the unit, or a published
activity study for the specialty. Vary the profile by unit type — a surgical
ward and a stroke unit do not divide their hours alike. Deferred deliberately,
not forgotten; tracked as `gap.task_profile_unsourced`.

## Queued: regulatory scope by jurisdiction
`app/roles.py` `from_regulator()` is a documented stub, not a promise. The
procedure is written into its docstring: fetch the regulator's scope-of-practice
publication, extract grades and permitted activities, map onto `Task` keeping
the regulator's own wording for audit, record as a source with its retrieval
date, and mark `verified` only after a human check.

Two constraints found while scoping it:
- Scope is often **not national** — per state in the US, per province in Canada.
  Canada's RPN is a regulated profession in BC, AB, SK and MB only. "US" is not
  one answer.
- Saudi Arabia reportedly has **no clearly articulated scope for all nursing
  categories**, so an empty result there may be correct rather than a scraping
  failure.

Regulators located and recorded: DoH Abu Dhabi (AE), CNO and CLPNA (CA).
Spain's TCAE scope was not found in this pass.

## Two records, two purposes
- `research/evidence.db` — what the literature says. Committed; regenerable.
- `research/planning_log.db` — what this app recommended, on what inputs, under
  which evidence version. **Gitignored**: operational, per-deployment, and may
  carry names. Each run stores an evidence fingerprint, so if a multiplier later
  changes, past decisions surface as stale rather than silently wrong.
- Method decisions (why MILP, why acuity-driven) live in the refs-books brain
  ledger — 3 entries for this project, cross-project by design.

## Evidence rules
Every clinical or regulatory constant used by the model must resolve through
`research/ingest.py get <key>` and carry a source. No magic numbers in
`planner.py`. Regenerate `research/SOURCES.md` after any change to the store.

## Data caveat
Runs on mock data. Safe to build and validate the machinery now; **no output is
clinically meaningful** until real census, CMI and acuity data replace the
mocks. Never present results as staffing advice.
