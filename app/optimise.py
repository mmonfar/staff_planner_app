"""Find the cheapest skill mix that is safe, compliant and humane.

This is where ratios stop being an input. NICE SG1 is explicit that no single
nurse-to-patient ratio fits every ward and that each ward must set its own
establishment; this module does that, by solving for headcount rather than
asking for a ratio and reporting what it costs.

**Why an exact solver and not a metaheuristic.** The aggregate skill-mix
problem is tiny — three roles across two or three shifts, so nine to twelve
integer variables. Mixed-integer programming solves it to proven optimality in
milliseconds. A genetic algorithm or annealer would return an approximation,
cost reproducibility, and buy nothing. Metaheuristics earn their place at
*individual rostering* — assigning named staff to dates, where the space
explodes — not here.

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

from app.planner import DAYS_PER_YEAR, DEFAULT_COSTS, Model
from app.wellbeing import ShiftPattern, assess

# Care hours contributed per rostered hour, by role. Registered nurses can
# deliver any part of the care; support roles cannot, so a plan cannot be made
# safe simply by buying more of the cheapest grade — hence the skill-mix floor
# below rather than a pure cost minimisation.
ROLE_HOURS_CONTRIBUTION = {"sn": 1.0, "pn": 1.0, "hca": 1.0}

# Minimum share of care hours delivered by registered nurses. A richer mix
# lowers both mortality (aiken-2014-lancet) and sickness absence
# (dallora-2025-jamanetwopen). The floor is a policy choice, not a published
# constant — it is the lever the epsilon-constraint sweep moves.
DEFAULT_MIN_RN_SHARE = 0.55

MAX_PER_ROLE_PER_SHIFT = 40


def _solver():
    """CBC, preferring the non-deprecated entry point where it is installed.

    `PULP_CBC_CMD` is removed in PuLP 4.0 in favour of `COIN_CMD`; falling back
    keeps this working on either.
    """
    available = pulp.listSolvers(onlyAvailable=True)
    if "COIN_CMD" in available:
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

    def on_shift(self, shift: str) -> dict[str, int]:
        return {r: n for (r, s), n in self.headcount.items() if s == shift and n}

    def total_headcount(self) -> int:
        return sum(self.headcount.values())


def solve(
    model: Model,
    demand_hours: float,
    costs: dict[str, float] = None,
    min_rn_share: float = DEFAULT_MIN_RN_SHARE,
    roles: tuple[str, ...] = None,
) -> Establishment:
    """Cheapest headcount meeting `demand_hours` of care at the required mix.

    `demand_hours` is care hours for one day — take it from the stochastic
    layer's chosen percentile, not from mean demand.
    """
    costs = costs or DEFAULT_COSTS
    roles = roles or tuple(costs)
    shifts = model.shifts

    problem = pulp.LpProblem("establishment", pulp.LpMinimize)
    # `problem.add_variable` rather than `pulp.LpVariable(...)`: constructing
    # variables directly is deprecated and is removed in PuLP 4.0.
    x = {
        (r, s): problem.add_variable(f"x_{r}_{s}", lowBound=0,
                                     upBound=MAX_PER_ROLE_PER_SHIFT, cat="Integer")
        for r in roles for s in shifts
    }

    def hours(role, shift):
        return x[(role, shift)] * shifts[shift] * ROLE_HOURS_CONTRIBUTION[role]

    total_hours = pulp.lpSum(hours(r, s) for r in roles for s in shifts)
    rn_hours = pulp.lpSum(hours("sn", s) for s in shifts) if "sn" in roles else 0

    # Cost per care hour, so shift patterns of different lengths compare fairly.
    problem += pulp.lpSum(
        x[(r, s)] * shifts[s] * costs[r] for r in roles for s in shifts
    )

    problem += total_hours >= demand_hours, "coverage"
    # Every shift must be covered, and covered at the required mix. A global
    # skill-mix floor alone is gameable: the solver stacks registered nurses
    # onto one shift and leaves the night with a single nurse to 32 patients,
    # which satisfies the daily average and is indefensible on the ward.
    for s in shifts:
        share = shifts[s] / sum(shifts.values())
        shift_hours_total = pulp.lpSum(hours(r, s) for r in roles)
        problem += shift_hours_total >= share * demand_hours, f"cover_{s}"
        if "sn" in roles:
            problem += (
                hours("sn", s) >= min_rn_share * shift_hours_total,
                f"skill_mix_{s}",
            )
            problem += x[("sn", s)] >= 1, f"rn_present_{s}"

    problem.solve(_solver())
    status = pulp.LpStatus[problem.status]

    headcount = {k: int(round(v.value() or 0)) for k, v in x.items()}
    delivered = sum(
        n * shifts[s] * ROLE_HOURS_CONTRIBUTION[r] for (r, s), n in headcount.items()
    )
    rn_delivered = sum(
        n * shifts[s] for (r, s), n in headcount.items() if r == "sn"
    )
    pattern = ShiftPattern(
        shift_hours=max(shifts.values()),
        weekly_hours=model.weekly_hours,
        night_share=1 / len(shifts),
        rn_share=(rn_delivered / delivered) if delivered else 0,
    )
    wb = assess(pattern)

    return Establishment(
        headcount=headcount,
        care_hours=delivered,
        rn_share=(rn_delivered / delivered) if delivered else 0.0,
        daily_cost=sum(n * shifts[s] * costs[r] for (r, s), n in headcount.items()),
        status=status,
        wellbeing_score=wb.score,
        compliant=wb.compliant,
        breaches=tuple(wb.breaches),
    )


def annual_cost(establishment: Establishment) -> float:
    return establishment.daily_cost * DAYS_PER_YEAR


# --- Pareto front ------------------------------------------------------------


def pareto_front(
    model: Model,
    demand_hours: float,
    costs: dict[str, float] = None,
    rn_shares: tuple[float, ...] = None,
) -> list[Establishment]:
    """Exact Pareto front over cost and registered-nurse share.

    Traced by the epsilon-constraint method: the skill-mix floor is stepped and
    cost re-minimised at each step. Because each solve is exact, the resulting
    front is exact — where NSGA-II would return an approximation of it.

    A weighted sum of cost and quality is deliberately not used: weighted sums
    cannot recover solutions on non-convex regions of a Pareto frontier no
    matter how the weights are tuned, so they silently drop valid plans.
    """
    rn_shares = rn_shares or tuple(round(0.30 + 0.05 * i, 2) for i in range(13))
    front = []
    for share in rn_shares:
        solution = solve(model, demand_hours, costs, min_rn_share=share)
        if solution.status == "Optimal":
            front.append(solution)
    return _non_dominated(front)


def _non_dominated(solutions: list[Establishment]) -> list[Establishment]:
    """Keep plans that nothing else beats on both cost and RN share.

    Distinct skill-mix floors often bind to the same integer plan, so identical
    points are collapsed first — otherwise the front reports the same staffing
    twice and overstates how many real choices a reader has.
    """
    seen, unique = set(), []
    for s in solutions:
        key = (round(s.daily_cost, 6), round(s.rn_share, 6))
        if key not in seen:
            seen.add(key)
            unique.append(s)
    solutions = unique

    keep = []
    for a in solutions:
        dominated = any(
            b is not a
            and b.daily_cost <= a.daily_cost
            and b.rn_share >= a.rn_share
            and (b.daily_cost < a.daily_cost or b.rn_share > a.rn_share)
            for b in solutions
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
) -> BaselineResult:
    """Check the solver against blind search and hill-climbing with restarts.

    Not ceremony. If an optimiser cannot beat random sampling on the same
    budget, the fault is almost always in the objective or the encoding, and
    tuning the optimiser hides that rather than fixing it.
    """
    costs = costs or DEFAULT_COSTS
    roles = tuple(costs)
    shifts = model.shifts
    rng = random.Random(seed)

    def evaluate(plan, penalise: bool = True) -> float:
        """Cost, with constraint violations priced in.

        Infeasible plans must not simply return infinity. Almost every random
        plan is infeasible, so a hard rejection leaves the hill-climber on a
        flat landscape with nothing to climb — it then reports no solution at
        all, and the gate passes vacuously because the solver beat nothing.
        Pricing violations gives the search a gradient toward feasibility, so
        the baseline is a real contest.
        """
        cost = sum(n * shifts[s] * costs[r] for (r, s), n in plan.items())
        violation = 0.0

        for s in shifts:
            share = shifts[s] / sum(shifts.values())
            shift_hours = sum(n * shifts[t] for (r, t), n in plan.items() if t == s)
            violation += max(0.0, share * demand_hours - shift_hours)
            rn_hours = sum(
                n * shifts[t] for (r, t), n in plan.items() if t == s and r == "sn"
            )
            violation += max(0.0, min_rn_share * shift_hours - rn_hours)
            if plan.get(("sn", s), 0) < 1:
                violation += shifts[s]

        delivered = sum(n * shifts[s] for (r, s), n in plan.items())
        violation += max(0.0, demand_hours - delivered)

        if not penalise:
            return math.inf if violation > 1e-9 else cost
        # Penalty weight exceeds the dearest hour, so no violation can ever be
        # bought more cheaply than it can be fixed.
        return cost + violation * max(costs.values()) * 10

    def true_cost(plan) -> float:
        return evaluate(plan, penalise=False)

    def random_plan():
        return {(r, s): rng.randint(0, 12) for r in roles for s in shifts}

    best_random = math.inf
    for _ in range(evaluations):
        best_random = min(best_random, true_cost(random_plan()))

    # Hill climbing with random restarts, same evaluation budget.
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
        # Score the climber on real cost, not on its penalised objective, so
        # the comparison against the solver is like for like.
        best_climb = min(best_climb, true_cost(current))

    solved = solve(model, demand_hours, costs, min_rn_share=min_rn_share)
    return BaselineResult(
        random_best=best_random,
        hill_climb_best=best_climb,
        solver=solved.daily_cost if solved.status == "Optimal" else math.inf,
        evaluations=evaluations,
    )
