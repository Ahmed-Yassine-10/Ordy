"""Parameter slots (doc 04 §6).

Workflows carry `{slots}` filled at run time from validated action arguments. Values are
treated strictly as data: when interpolated into a selector they are sanitized so a
crafted product name can never restructure the selector it lands in.
"""

from __future__ import annotations

import re

from ordy_automation.models import Step
from ordy_automation.safety import sanitize_for_selector

SLOT_RE = re.compile(r"\{([a-z][a-z0-9_]*)\}")


class MissingParameter(KeyError):
    """A workflow slot has no corresponding value in the action arguments."""


def slots_in(text: str) -> set[str]:
    return set(SLOT_RE.findall(text or ""))


def bind(template: str | None, params: dict[str, str], *, for_selector: bool = False) -> str | None:
    if template is None:
        return None

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in params:
            raise MissingParameter(name)
        value = str(params[name])
        return sanitize_for_selector(value) if for_selector else value

    return SLOT_RE.sub(replace, template)


def bind_step(step: Step, params: dict[str, str]) -> Step:
    """Return a copy of the step with all slots resolved."""
    return Step(
        op=step.op,
        target=step.target,
        url=bind(step.url, params),
        strategy=[bind(s, params, for_selector=True) or "" for s in step.strategy],
        value=bind(step.value, params),
        fields={k: bind(v, params) or "" for k, v in step.fields.items()},
        expect=step.expect,
        never_fill=list(step.never_fill),
        capture=step.capture,
        requires=step.requires,
    )
