# Staff Planner — Status Board

Maintained by the orchestrator session. Update on every completed task.

**Completion: 18 / 21 (86%). Ratios are now an output, not an input.**

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
| 24 | **Surface the optimiser in the UI** — solver and Pareto front are model-side only; the app still shows ratio-vs-demand, not the solved establishment | — | P0 |
| 9 | LICENSE (needs owner's choice) | — | P2 |
| 10 | CI — pytest on push | — | P2 |
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
- **All roles contribute equally to care hours** (`ROLE_HOURS_CONTRIBUTION` is
  1.0 across SN/PN/HCA), so only the skill-mix floor distinguishes grades. Real
  scopes of practice differ — some care can only be delivered by a registered
  nurse. Needs a clinical view before the front is trusted at low RN shares.
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

## Evidence rules
Every clinical or regulatory constant used by the model must resolve through
`research/ingest.py get <key>` and carry a source. No magic numbers in
`planner.py`. Regenerate `research/SOURCES.md` after any change to the store.

## Data caveat
Runs on mock data. Safe to build and validate the machinery now; **no output is
clinically meaningful** until real census, CMI and acuity data replace the
mocks. Never present results as staffing advice.
