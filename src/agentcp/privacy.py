"""Reversible pseudonymisation around the model call.

Three endpoints of one mechanism, and they only work as a set:

1. **Mask before the call.** The model is given ``<EMAIL_1>``, not the
   reporter's address. It does not need to know who that is; it needs to
   know that a person is being discussed.
2. **Restore after the response.** The human reading the answer *does*
   need the real value, or the answer is not actionable -- "email the
   reporter" is useless if you cannot see which reporter.
3. **Check a permission before restoring.** Restoring is the privileged
   half. A viewer without the right sees the placeholders.

Why reversible rather than deleted: deletion makes the output safe and
useless at the same time. The value has to come back for someone, which
means the question is *who*, which means there has to be a check -- so the
check belongs here, next to the mapping, not in whatever caller happens to
be assembling the response.

Why these three live in one module: if masking is in a gateway, restoring
is in a view layer and the permission is in a template, nothing can assert
that a value masked on the way out is restorable only on the way back to
someone entitled to it. Splitting them is how the guarantee is lost.

This is rule matching, not NER. See ``docs/scope.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Entity kinds, in the order patterns are applied. An address contains an
#: ``@`` and so does a handle; matching addresses first stops a handle
#: pattern from eating half of one.
PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("HOST", re.compile(r"\b[a-z0-9][a-z0-9-]*\.internal\b")),
    ("USER", re.compile(r"@[A-Za-z][\w-]{2,}")),
)

#: Matches a placeholder this module could have produced. Deleted once as
#: dead code, which it was until a test needed to walk checkpointed state
#: looking for a leaked mapping: "no real value escaped" is cheap to assert
#: and "no placeholder-keyed dict escaped" is the half that catches a map
#: smuggled out flattened.
PLACEHOLDER = re.compile(r"<(EMAIL|HOST|USER)_(\d+)>")

class RestoreDenied(PermissionError):
    """The viewer may not see real values behind the placeholders."""


class TraceMismatch(ValueError):
    """The mapping belongs to a different run."""


@dataclass(frozen=True)
class Viewer:
    """Who is asking to see the unmasked text."""

    name: str
    may_unmask: bool = False


@dataclass(frozen=True)
class Mapping:
    """Placeholder -> real value, bound to the run that produced it.

    Bound to a ``trace_id`` because a mapping is not a general-purpose
    dictionary: ``<EMAIL_1>`` means a different person in another run, and
    a mapping that silently resolved placeholders from a different run
    would leak one run's values into another's output.
    """

    trace_id: str
    pairs: dict[str, str] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.pairs)


def mask(text: str, trace_id: str) -> tuple[str, Mapping]:
    """Replace recognised entities with placeholders.

    Repeats of the same value get the same placeholder, so the model can
    still tell that two mentions are the same entity -- that relationship
    is usually what the judgement depends on.

    Returns the masked text and the mapping needed to undo it.
    """
    pairs: dict[str, str] = {}
    seen: dict[str, str] = {}
    counters: dict[str, int] = {}

    def substitute(match: re.Match, kind: str) -> str:
        real = match.group(0)
        if real in seen:
            return seen[real]
        counters[kind] = counters.get(kind, 0) + 1
        placeholder = f"<{kind}_{counters[kind]}>"
        seen[real] = placeholder
        pairs[placeholder] = real
        return placeholder

    out = text
    for kind, pattern in PATTERNS:
        out = pattern.sub(lambda m, k=kind: substitute(m, k), out)
    return out, Mapping(trace_id=trace_id, pairs=pairs)


def restore(text: str, mapping: Mapping, *, trace_id: str, viewer: Viewer) -> str:
    """Put the real values back, if *viewer* is allowed to see them.

    Refuses outright rather than restoring what it can. A partially
    restored response is the worst of both: it still leaks, and it reads
    as though nothing was withheld.
    """
    if mapping.trace_id != trace_id:
        raise TraceMismatch(
            f"mapping belongs to run {mapping.trace_id!r}, not {trace_id!r}"
        )
    if not viewer.may_unmask:
        raise RestoreDenied(f"{viewer.name} may not unmask this run")

    out = text
    for placeholder, real in mapping.pairs.items():
        out = out.replace(placeholder, real)
    return out


def leaks(text: str, mapping: Mapping) -> list[str]:
    """Real values from *mapping* still present in *text*.

    Used by the tests to assert on the whole output rather than on the
    positions the substitution happened to touch.
    """
    return [real for real in mapping.pairs.values() if real in text]
