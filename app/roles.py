"""Who may do what: care tasks, roles, and scope of practice by jurisdiction.

The solver previously treated a care hour as a care hour — a healthcare
assistant's hour counted the same as a registered nurse's, and only a blunt
"minimum RN share" stopped the optimiser buying the cheapest grade. That is
wrong in a way that matters: an HCA cannot administer medication or carry out a
clinical assessment, so a plan that is cheap because it is HCA-heavy may be
undeliverable rather than merely thin.

Care demand is therefore split into task categories, and each role carries the
set it may **perform** and the set it may only **assist** with. Coverage is then
required per task, not in aggregate. The registered-nurse share stops being an
imposed policy floor and becomes an *emergent* property: RN-only tasks force RN
hours, whatever the cost function would prefer.

This also makes support roles expressible. A porter cannot deliver nursing
care, but can take the second pair of hands on a reposition or a transfer —
real hours that currently get charged to an HCA who is then not somewhere else.

**Jurisdictions.** Role structures are not universal. Spain's TCAE, Canada's
LPN and RPN, the UK's nursing associate, and the cadres used across the Gulf do
not map onto one another, and a planner that assumes one country's grades will
mis-plan in another. Catalogues are therefore keyed by jurisdiction. Only the
UK catalogue is populated from a considered reading; the rest are declared as
stubs so their absence is visible rather than silently defaulting to UK grades.
See `from_regulator` for how these are intended to be filled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Task(str, Enum):
    """Categories of nursing work, split by who is permitted to do them."""

    MEDICATION = "medication"
    CLINICAL_ASSESSMENT = "clinical_assessment"
    CLINICAL_PROCEDURE = "clinical_procedure"
    WOUND_CARE = "wound_care"
    OBSERVATIONS = "observations"
    PERSONAL_CARE = "personal_care"
    REPOSITIONING = "repositioning"
    MOBILITY_TRANSFER = "mobility_transfer"
    ESCORT_TRANSPORT = "escort_transport"
    DOCUMENTATION = "documentation"


# Share of care hours falling in each task category. An ASSUMPTION, not a
# sourced distribution: it should come from local observation or an activity
# study. It is exposed so it can be replaced per unit type — a surgical ward and
# a stroke unit do not divide their hours the same way.
DEFAULT_TASK_PROFILE: dict[Task, float] = {
    Task.MEDICATION: 0.14,
    Task.CLINICAL_ASSESSMENT: 0.10,
    Task.CLINICAL_PROCEDURE: 0.08,
    Task.WOUND_CARE: 0.06,
    Task.OBSERVATIONS: 0.12,
    Task.PERSONAL_CARE: 0.22,
    Task.REPOSITIONING: 0.10,
    Task.MOBILITY_TRANSFER: 0.08,
    Task.ESCORT_TRANSPORT: 0.04,
    Task.DOCUMENTATION: 0.06,
}


@dataclass(frozen=True)
class Role:
    """A staff grade and what it is permitted to do.

    `performs` is work the role may carry out on its own authority. `assists` is
    work it may contribute hours to but not lead — the second pair of hands on a
    reposition, say. Both count toward covering a task; the distinction is kept
    because a task cannot be staffed entirely by assistants, which
    `min_lead_share` enforces.
    """

    key: str
    title: str
    performs: frozenset[Task]
    assists: frozenset[Task] = frozenset()
    regulated: bool = True
    verified: bool = False
    source: str | None = None

    def can_cover(self, task: Task) -> bool:
        return task in self.performs or task in self.assists

    def can_lead(self, task: Task) -> bool:
        return task in self.performs


# Fraction of a task's hours that must come from staff who may *lead* it rather
# than merely assist. 1.0 for tasks no assistant may share; below 1.0 where a
# second person is genuinely substitutable.
DEFAULT_MIN_LEAD_SHARE: dict[Task, float] = {
    Task.REPOSITIONING: 0.5,        # commonly a two-person task; one may assist
    Task.MOBILITY_TRANSFER: 0.5,
    Task.ESCORT_TRANSPORT: 0.0,     # can be delegated outright
}


@dataclass(frozen=True)
class RoleCatalogue:
    """The grades that exist in one jurisdiction, and their scope."""

    jurisdiction: str
    roles: dict[str, Role]
    notes: str = ""
    verified: bool = False

    def __getitem__(self, key: str) -> Role:
        return self.roles[key]

    def keys(self) -> tuple[str, ...]:
        return tuple(self.roles)

    def covering(self, task: Task) -> tuple[str, ...]:
        return tuple(k for k, r in self.roles.items() if r.can_cover(task))

    def leading(self, task: Task) -> tuple[str, ...]:
        return tuple(k for k, r in self.roles.items() if r.can_lead(task))

    def unstaffable(self, task: Task) -> bool:
        """True when no role in this jurisdiction may lead the task."""
        return not self.leading(task)


_ALL = frozenset(Task)

# --- United Kingdom ---------------------------------------------------------
# Considered reading rather than a citation-backed extract. The shape is right;
# the detail should be checked against NMC standards before operational use.

UK = RoleCatalogue(
    jurisdiction="UK",
    verified=False,
    notes=(
        "Registered nurse, nursing associate, healthcare assistant, porter. "
        "The nursing associate is a regulated UK grade with no direct analogue "
        "in most other systems, which is precisely why catalogues are not "
        "portable."
    ),
    roles={
        "sn": Role("sn", "Registered Nurse", performs=_ALL),
        "pn": Role(
            "pn", "Nursing Associate / Practical Nurse",
            performs=frozenset({
                Task.WOUND_CARE, Task.OBSERVATIONS, Task.PERSONAL_CARE,
                Task.REPOSITIONING, Task.MOBILITY_TRANSFER,
                Task.ESCORT_TRANSPORT, Task.DOCUMENTATION,
            }),
            assists=frozenset({Task.MEDICATION, Task.CLINICAL_PROCEDURE}),
        ),
        "hca": Role(
            "hca", "Healthcare Assistant",
            performs=frozenset({
                Task.PERSONAL_CARE, Task.REPOSITIONING, Task.MOBILITY_TRANSFER,
                Task.ESCORT_TRANSPORT, Task.OBSERVATIONS,
            }),
            regulated=False,
        ),
        "porter": Role(
            "porter", "Porter / Support Worker",
            performs=frozenset({Task.ESCORT_TRANSPORT}),
            assists=frozenset({Task.REPOSITIONING, Task.MOBILITY_TRANSFER}),
            regulated=False,
        ),
    },
)


def _stub(jurisdiction: str, note: str) -> RoleCatalogue:
    """An acknowledged gap.

    Deliberately empty rather than a copy of the UK grades: silently planning a
    Spanish or Emirati ward with British roles would be worse than refusing to
    plan it at all.
    """
    return RoleCatalogue(jurisdiction=jurisdiction, roles={}, notes=note,
                         verified=False)


CATALOGUES: dict[str, RoleCatalogue] = {
    "UK": UK,
    "ES": _stub("ES", "Enfermero/a and TCAE (auxiliar de enfermería). TCAE scope "
                      "is set nationally and does not map onto the UK HCA."),
    "US": _stub("US", "RN, LPN/LVN and CNA. Scope is set state by state, so a "
                      "single US catalogue is a simplification."),
    "CA": _stub("CA", "RN, LPN and RPN (registered psychiatric nurse, a regulated "
                      "profession only in BC, AB, SK and MB). Provincial "
                      "regulators define scope."),
    "AE": _stub("AE", "Department of Health Abu Dhabi publishes a nursing scope "
                      "of practice (Nov 2022) tying activity to education, "
                      "licensure and competence."),
    "SA": _stub("SA", "Scope of practice is not clearly articulated for all "
                      "nursing categories, which is itself the finding — a "
                      "catalogue here will need primary work, not a lookup."),
}


def catalogue(jurisdiction: str = "UK") -> RoleCatalogue:
    try:
        return CATALOGUES[jurisdiction]
    except KeyError:
        raise KeyError(
            f"no role catalogue for {jurisdiction!r}; "
            f"known: {sorted(CATALOGUES)}"
        ) from None


def from_regulator(jurisdiction: str) -> RoleCatalogue:
    """Build a catalogue from published regulatory scope-of-practice documents.

    Not implemented. The intended shape, recorded so the work is actionable
    rather than aspirational:

    1. Fetch the regulator's scope-of-practice publication for the jurisdiction
       (UAE: Department of Health Abu Dhabi; Canada: the provincial college —
       CNO, BCCNM, CLPNA; UK: NMC; US: the state board).
    2. Extract the grades it recognises and the activities each is permitted.
    3. Map those activities onto this module's `Task` categories, keeping the
       regulator's own wording alongside so a mapping decision can be audited.
    4. Record each as a source in `research/evidence.db` with its retrieval date,
       and mark the catalogue `verified=True` only once a human has checked the
       mapping.

    Two warnings for whoever builds it. Scope is not always national — it is set
    per state in the US and per province in Canada, so "US" is not one answer.
    And at least one jurisdiction has no clear articulated scope for all nursing
    categories, so an empty result may be the correct one rather than a scraping
    failure.
    """
    raise NotImplementedError(
        f"scope of practice for {jurisdiction!r} must be sourced from its "
        "regulator; see this function's docstring for the intended procedure"
    )


def task_demand(
    total_hours: float, profile: dict[Task, float] = None
) -> dict[Task, float]:
    """Split care hours across task categories."""
    profile = profile or DEFAULT_TASK_PROFILE
    total_share = sum(profile.values())
    if abs(total_share - 1.0) > 1e-6:
        raise ValueError(f"task profile sums to {total_share:.4f}, must sum to 1")
    return {task: total_hours * share for task, share in profile.items()}
