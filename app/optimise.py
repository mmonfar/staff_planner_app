"""Find the cheapest staffing that is safe, deliverable, compliant and humane.

This is where ratios stop being an input. NICE SG1 is explicit that no single
nurse-to-patient ratio fits every ward and that each ward must set its own
establishment; this module does that, by solving for headcount rather than
asking for a ratio and reporting what it costs.

**Deliverability, not just volume.** An earlier version counted every care hour
the same, so a plan could be cheap because it was assistant-heavy — and
undeliverable, because a healthcare assistant may not give medication or make a
clinical assessment. Demand is now split into task categories (`app.roles`) and
covered per task, by roles permitted to do that task. The registered-nurse share
is no longer an imposed floor; it emerges from the work that only a registered
nurse may do.

**Why an exact solver and not a metaheuristic.** Twelve integer headcount
variables and a few dozen continuous allocation variables solve to proven
optimality in milliseconds. A genetic algorithm or annealer would return an
approximation, cost reproducibility, and buy nothing. Metaheuristics earn their
place at *individual rostering* — assigning named staff to dates, where the
space explodes — not here.

Every result is checked against two baselines before it is reportable: random
search and hill-climbing with random restarts, on a comparable budget. If a
solver cannot beat blind sampling, the objective or the encoding is broken and
tuning the solver only hides it.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import pulp

from app.planner import DAYS_PER_YEAR, Model
from app.roles import (
    DEFAULT_MIN_LEAD_SHARE,
    DEFAULT_TASK_PROFILE,
    UK,
    RoleCatalogue,
    Task,
    task_demand,
)
from app.wellbeing import ShiftPattern, assess

DEFAULT_COSTS = {"sn": 1.0, "pn": 0.65, "hca": 0.4, "porter": 0.3}

# An additional policy floor on registered-nurse hours, over and above whatever
# scope of practice already forces. A richer mix lowers both mortality
# (aiken-2014-lancet) and sickness absence (dallora-2025-jamanetwopen). This is
# the lever the epsilon-constraint sweep moves; 0.0 leaves scope to decide.
DEFAULT_MIN_RN_SHARE = 0.0

MAX_PER_ROLE_PER_SHIFT = 40
REGISTERED_ROLE = "sn"


def _solver():
    """CBC, preferring the non-deprecated entry point where it is installed."""
    if "COIN_CMD" in pulp.listSolvers(onlyAvailable=True):
        return pulp.COIN_CMD(msg=False)
    return pulp.PULP_CBC_CMD(msg=False)


@dataclass(frozen=True)
class Establishment:
    """A solved staffing plan."""

    headcount: dict[tuple[str, str], int]
    care_hours: float
    rn_share: float
    daily_cost: float
    status: str
    wellbeing_score: float = 0.0
    compliant: bool = True
    breaches: tuple[str, ...] = ()
    task_hours: dict[tuple[str, str], float] = field(default_factory=dict)

    def on_shift(self, shift: str) -> dict[str, int]:
        return {r: n for (r, s), n in self.headcount.items() if s == shift and n}

    def total_headcount(self) -> int:
        return sum(self.headcount.values())

    def hours_by_task(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for (role, task), hours in self.task_hours.items():
            out[task] = out.get(task, 0.0) + hours
        return out


def solve(
    model: Model,
    demand_hours: float,
    costs: dict[str, float] = None,
    min_rn_share: float = DEFAULT_MIN_RN_SHARE,
    roles: tuple[str, ...] = None,
    catalogue: RoleCatalogue = UK,
    task_profile: dict[Task, float] = None,
    min_lead_share: dict[Task, float] = None,
) -> Establishment:
    """Cheapest headcount that can actually deliver `demand_hours` of care.

    `demand_hours` is care hours for one day — take it from the stochastic
    layer's chosen percentile, not from mean demand.
    """
    costs = costs or DEFAULT_COSTS
    roles = roles or tuple(k for k in catalogue.keys() if k in costs)
    task_profile = task_profile or DEFAULT_TASK_PROFILE
    min_lead_share = min_lead_share or DEFAULT_MIN_LEAD_SHARE
    shifts = model.shifts
    day_hours = sum(shifts.values())

    demand_by_task = task_demand(demand_hours, task_profile)

    problem = pulp.LpProblem("establishment", pulp.LpMinimize)
    # `problem.add_variable` rather than `pulp.LpVariable(...)`: constructing
    # variables directly is deprecated and removed in PuLP 4.0.
    x = {
        (r, s): problem.add_variable(f"n_{r}_{s}", lowBound=0,
                                     upBound=MAX_PER_ROLE_PER_SHIFT, cat="Integer")
        for r in roles for s in shifts
    }
    # Hours each role spends on each task, per shift. Only created where the
    # role is permitted to cover the task, so scope is structural rather than a
    # constraint the solver could trade away.
    y = {
        (r, s, t): problem.add_variable(f"h_{r}_{s}_{t.value}", lowBound=0)
        for r in roles for s in shifts for t in Task
        if catalogue.roles[r].can_cover(t)
    }

    problem += pulp.lpSum(x[(r, s)] * shifts[s] * costs[r] for r in roles for s in shifts)

    for s, length in shifts.items():
        share = length / day_hours

        for r in roles:
            # Nobody can be allocated more hours than they are rostered for.
            allocated = pulp.lpSum(y[k] for k in y if k[0] == r and k[1] == s)
            problem += allocated <= x[(r, s)] * length, f"capacity_{r}_{s}"

        for t in Task:
            required = demand_by_task[t] * share
            if required <= 0:
                continue
            covering = [y[(r, s, t)] for r in roles if (r, s, t) in y]
            if not covering:
                raise ValueError(
                    f"no role in the {catalogue.jurisdiction} catalogue can cover "
                    f"{t.value}; the plan would be undeliverable"
                )
            problem += pulp.lpSum(covering) >= required, f"cover_{t.value}_{s}"

            # A task cannot be staffed entirely by people who may only assist.
            lead_floor = min_lead_share.get(t, 1.0)
            if lead_floor > 0:
                leading = [
                    y[(r, s, t)] for r in roles
                    if (r, s, t) in y and catalogue.roles[r].can_lead(t)
                ]
                if not leading:
                    raise ValueError(
                        f"no role may lead {t.value} in {catalogue.jurisdiction}"
                    )
                problem += (
                    pulp.lpSum(leading) >= lead_floor * required,
                    f"lead_{t.value}_{s}",
                )

        if REGISTERED_ROLE in roles:
            problem += x[(REGISTERED_ROLE, s)] >= 1, f"rn_present_{s}"
            if min_rn_share > 0:
                rostered = pulp.lpSum(x[(r, s)] * length for r in roles)
                problem += (
                    x[(REGISTERED_ROLE, s)] * length >= min_rn_share * rostered,
                    f"rn_floor_{s}",
                )

    problem.solve(_solver())
    status = pulp.LpStatus[problem.status]

    headcount = {k: int(round(v.value() or 0)) for k, v in x.items()}
    rostered_hours = sum(n * shifts[s] for (r, s), n in headcount.items())
    rn_hours = sum(n * shifts[s] for (r, s), n in headcount.items()
                   if r == REGISTERED_ROLE)
    rn_share = (rn_hours / rostered_hours) if rostered_hours else 0.0

    task_hours: dict[tuple[str, str], float] = {}
    for (r, s, t), var in y.items():
        value = var.value() or 0.0
        if value > 1e-6:
            key = (r, t.value)
            task_hours[key] = task_hours.get(key, 0.0) + value

    wb = assess(ShiftPattern(
        shift_hours=max(shifts.values()),
        weekly_hours=model.weekly_hours,
        night_share=1 / len(shifts),
        rn_share=rn_share,
    ))

    return Establishment(
        headcount=headcount,
        care_hours=rostered_hours,
        rn_share=rn_share,
        daily_cost=sum(n * shifts[s] * costs[r] for (r, s), n in headcount.items()),
        status=status,
        wellbeing_score=wb.score,
        compliant=wb.compliant,
        breaches=tuple(wb.breaches),
        task_hours=task_hours,
    )


def annual_cost(establishment: Establishment) -> float:
    return establishment.daily_cost * DAYS_PER_YEAR


# --- Pareto front ------------------------------------------------------------


def pareto_front(
    model: Model,
    demand_hours: float,
    costs: dict[str, float] = None,
    rn_shares: tuple[float, ...] = None,
    catalogue: RoleCatalogue = UK,
) -> list[Establishment]:
    """Exact Pareto front over cost and registered-nurse share.

    Traced by the epsilon-constraint method: the RN floor is stepped and cost
    re-minimised at each step. Because each solve is exact, the front is exact —
    where NSGA-II would return an approximation.

    A weighted sum of cost and quality is deliberately not used: weighted sums
    cannot recover solutions on non-convex regions of a Pareto frontier no
    matter how the weights are tuned, so they silently drop valid plans.

    The low-cost end of this front is now trustworthy in a way it was not
    before: scope of practice, rather than an arbitrary floor, sets how lean the
    mix can get.
    """
    rn_shares = rn_shares or tuple(round(0.05 * i, 2) for i in range(19))
    front = []
    for share in rn_shares:
        solution = solve(model, demand_hours, costs, min_rn_share=share,
                         catalogue=catalogue)
        if solution.status == "Optimal":
            front.append(solution)
    return _non_dominated(front)


def _non_dominated(solutions: list[Establishment]) -> list[Establishment]:
    """Keep plans that nothing else beats on both cost and RN share.

    Distinct floors often bind to the same integer plan, so identical points are
    collapsed first — otherwise the front reports the same staffing twice and
    overstates how many real choices a reader has.
    """
    seen, unique = set(), []
    for s in solutions:
        key = (round(s.daily_cost, 6), round(s.rn_share, 6))
        if key not in seen:
            seen.add(key)
            unique.append(s)

    keep = []
    for a in unique:
        dominated = any(
            b is not a
            and b.daily_cost <= a.daily_cost
            and b.rn_share >= a.rn_share
            and (b.daily_cost < a.daily_cost or b.rn_share > a.rn_share)
            for b in unique
        )
        if not dominated:
            keep.append(a)
    return sorted(keep, key=lambda s: s.daily_cost)


# --- baseline gate -----------------------------------------------------------


@dataclass
class BaselineResult:
    random_best: float
    hill_climb_best: float
    solver: float
    evaluations: int
    beats_random: bool = field(init=False)
    beats_hill_climb: bool = field(init=False)

    def __post_init__(self) -> None:
        self.beats_random = self.solver <= self.random_best
        self.beats_hill_climb = self.solver <= self.hill_climb_best

    @property
    def passed(self) -> bool:
        return self.beats_random and self.beats_hill_climb


def baseline_gate(
    model: Model,
    demand_hours: float,
    costs: dict[str, float] = None,
    min_rn_share: float = DEFAULT_MIN_RN_SHARE,
    evaluations: int = 4000,
    seed: int = 20260918,
    catalogue: RoleCatalogue = UK,
    task_profile: dict[Task, float] = None,
) -> BaselineResult:
    """Check the solver against blind search and hill-climbing with restarts.

    Not ceremony. If an optimiser cannot beat random sampling on the same
    budget, the fault is almost always in the objective or the encoding, and
    tuning the optimiser hides that rather than fixing it.
    """
    costs = costs or DEFAULT_COSTS
    roles = tuple(k for k in catalogue.keys() if k in costs)
    task_profile = task_profile or DEFAULT_TASK_PROFILE
    shifts = model.shifts
    day_hours = sum(shifts.values())
    demand_by_task = task_demand(demand_hours, task_profile)
    rng = random.Random(seed)

    def shortfall(plan) -> float:
        """Unmet task hours, greedily allocating the most restricted staff last.

        A plan's feasibility is not a headcount total: hours only count toward a
        task if the role holding them is allowed to do it.
        """
        total = 0.0
        for s, length in shifts.items():
            capacity = {r: plan.get((r, s), 0) * length for r in roles}
            # Cover the most restricted tasks first, otherwise a generalist's
            # hours get spent on work an assistant could have done.
            ordered = sorted(
                Task, key=lambda t: len([r for r in roles
                                         if catalogue.roles[r].can_cover(t)])
            )
            for t in ordered:
                required = demand_by_task[t] * (length / day_hours)
                able = sorted(
                    (r for r in roles if catalogue.roles[r].can_cover(t)),
                    key=lambda r: -costs[r],
                )
                for r in able:
                    if required <= 0:
                        break
                    used = min(capacity[r], required)
                    capacity[r] -= used
                    required -= used
                total += max(0.0, required)
            if plan.get((REGISTERED_ROLE, s), 0) < 1:
                total += length
        return total

    def evaluate(plan, penalise: bool = True) -> float:
        """Cost, with constraint violations priced in.

        Infeasible plans must not simply return infinity: almost every random
        plan is infeasible, so a hard rejection leaves the hill-climber on a
        flat landscape with nothing to climb. It then reports no solution and
        the gate passes vacuously, because the solver beat nothing.
        """
        cost = sum(n * shifts[s] * costs[r] for (r, s), n in plan.items())
        unmet = shortfall(plan)
        if not penalise:
            return math.inf if unmet > 1e-6 else cost
        return cost + unmet * max(costs.values()) * 10

    def random_plan():
        return {(r, s): rng.randint(0, 12) for r in roles for s in shifts}

    best_random = math.inf
    for _ in range(evaluations):
        best_random = min(best_random, evaluate(random_plan(), penalise=False))

    best_climb = math.inf
    restarts = 40
    per_restart = max(1, evaluations // restarts)
    for _ in range(restarts):
        current = random_plan()
        current_cost = evaluate(current)
        for _ in range(per_restart):
            candidate = dict(current)
            key = rng.choice(list(candidate))
            candidate[key] = max(0, candidate[key] + rng.choice((-1, 1)))
            cost = evaluate(candidate)
            if cost <= current_cost:
                current, current_cost = candidate, cost
        # Score on real cost, not the penalised objective, so the comparison
        # against the solver is like for like.
        best_climb = min(best_climb, evaluate(current, penalise=False))

    solved = solve(model, demand_hours, costs, min_rn_share=min_rn_share,
                   catalogue=catalogue, task_profile=task_profile)
    return BaselineResult(
        random_best=best_random,
        hill_climb_best=best_climb,
        solver=solved.daily_cost if solved.status == "Optimal" else math.inf,
        evaluations=evaluations,
    )
