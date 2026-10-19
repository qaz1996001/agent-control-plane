"""A real model wired into the one seam that is meant for one.

``agentcp.agents.Judge`` is ``(prompt, context) -> dict``. Everything in
``src/agentcp`` is written against that Protocol and nothing else, so putting a
real model behind it is the whole integration -- no change to the router, the
budget, the tool registry, or the gate.

This file lives in ``examples/`` on purpose. ``src/agentcp`` has no provider
SDK, no model id, and no API key in it, and ``tests/test_routing.py`` asserts
the control plane still runs with every model entry point poisoned. That
assertion is the project's argument; importing a provider into ``src`` would
quietly retract it. So the model goes where the other integration seams go:
next to ``adapters.py``.

The model used here is Gemma 4 E4B served by a local Ollama
(``ollama pull gemma4:e4b``). Nothing below is specific to Gemma beyond the
model tag -- the request is plain JSON over HTTP with the standard library, so
there is no new dependency to install and nothing to configure.

What is worth watching in the output: **the model's answer is type-coerced at
the boundary.** A 4B-class model will sometimes return a severity outside the
enum, or an empty response. The code below rejects that and falls back to the
deterministic default, counting the failure. The control plane never sees a
value it did not ask for -- which is the point of putting the judgement inside
a step instead of letting it pick the next one.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

DEFAULT_MODEL = "gemma4:e4b"
DEFAULT_BASE_URL = "http://127.0.0.1:11434"

# -- the two judgement points, and the shape each one must return ----------
#
# ``agents.triage_node`` asks "classify severity"; ``agents.reviewer_node``
# asks "review diff". Those are the only two prompts the control plane ever
# sends, so the schema is known ahead of time and does not have to be guessed
# from the model's reply. Ollama takes it as the ``format`` parameter and
# constrains decoding to it.

SEVERITIES = ["low", "normal", "high", "critical"]

CALL_SITES = {
    "classify severity": {
        "instruction": (
            "You are triaging a bug ticket. Reply with its severity, "
            f"one of: {', '.join(SEVERITIES)}."
        ),
        "schema": {
            "type": "object",
            "properties": {"severity": {"type": "string", "enum": SEVERITIES}},
            "required": ["severity"],
        },
    },
    "review diff": {
        "instruction": (
            "You are reviewing a pull request. Decide whether it may proceed. "
            "Reply with approved (true/false) and a short list of comments."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "approved": {"type": "boolean"},
                "comments": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["approved", "comments"],
        },
    },
}

# The same values as ``agents._default_severity`` / ``_default_verdict``
# (src/agentcp/agents.py:97-102). Duplicated rather than imported: a fallback
# the example controls is clearer than reaching into a private name, and it
# keeps the example honest about what it substitutes.
FALLBACKS = {
    "classify severity": {"severity": "normal"},
    "review diff": {"approved": True, "comments": []},
}


class OllamaUnavailable(RuntimeError):
    """The local model server could not be reached, or has no such model.

    Distinct from a bad reply: an unreachable server is an environment
    problem the operator has to fix, not something to paper over with a
    default.
    """


class GemmaJudge:
    """A ``Judge`` backed by a local Ollama model.

    Parameters
    ----------
    model : str
        Ollama model tag, e.g. ``gemma4:e4b``.
    base_url : str
        Where Ollama listens.
    timeout : float
        Seconds to wait per call. A cold model takes a while to load.
    verbose : bool
        Print each request and the raw reply, so the demo shows what the
        model actually said rather than only what survived validation.

    Attributes
    ----------
    calls : int
        Judgement calls made.
    fallbacks : list of str
        One entry per call whose reply had to be discarded, with the reason.
        Reported at the end of the run; an empty list is the good case.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 180.0,
        verbose: bool = True,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.verbose = verbose
        self.calls = 0
        self.fallbacks: list[str] = []

    # -- the Judge protocol ------------------------------------------------

    def __call__(self, prompt: str, context: dict) -> dict:
        site = CALL_SITES.get(prompt)
        if site is None:
            # The control plane grew a judgement point this example does not
            # know about. Say so loudly; returning {} lets the node's own
            # ``.get(..., default)`` take over.
            self._log(f"  ! unknown judgement point {prompt!r}; returning nothing")
            return {}

        self.calls += 1
        raw, eval_count = self._chat(site["instruction"], context, site["schema"])
        self._log(f"  model said  {raw!r}")

        value, problem = _coerce(prompt, raw)
        if problem is not None:
            self.fallbacks.append(f"{prompt}: {problem}")
            value = dict(FALLBACKS[prompt])
            self._log(f"  ! rejected ({problem}); falling back to {value}")

        # Report on the call as well as answer it. ``consult`` settles its
        # token estimate against ``tokens`` and records ``provider`` as what
        # actually answered; both are stripped before the verdict reaches the
        # node's report. ``text`` is what was generated, so the budget guard
        # counts the real output rather than a re-serialised summary of it --
        # and it stays the raw reply even on the fallback path, because those
        # tokens were produced and billed whether or not the answer was usable.
        value = dict(value)
        value["provider"] = f"ollama:{self.model}"
        value["text"] = raw
        if eval_count is not None:
            value["tokens"] = eval_count
        return value

    # -- transport ---------------------------------------------------------

    def _chat(self, instruction: str, context: dict, schema: dict) -> tuple[str, int | None]:
        """One non-streaming ``/api/chat`` call.

        Returns
        -------
        (content, eval_count)
            The raw reply, and the provider's own count of the tokens it
            generated -- ``None`` if this Ollama build did not report one.
        """
        payload = {
            "model": self.model,
            "stream": False,
            "format": schema,
            "options": {"temperature": 0},   # deterministic, so the demo repeats
            "messages": [
                {"role": "system", "content": instruction},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
        }
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.load(resp)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace").strip()
            raise OllamaUnavailable(f"HTTP {exc.code} from Ollama: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise OllamaUnavailable(f"cannot reach Ollama at {self.base_url}: {exc}") from exc
        count = body.get("eval_count")
        return (
            (body.get("message") or {}).get("content") or "",
            count if isinstance(count, int) else None,
        )

    def _log(self, line: str) -> None:
        if self.verbose:
            print(line)


def make_gemma_judge(**kwargs) -> GemmaJudge:
    """Build a ``Judge`` for ``build_graph(judge=...)``."""
    return GemmaJudge(**kwargs)


# -- validation ------------------------------------------------------------

def _coerce(prompt: str, raw: str) -> tuple[dict, str | None]:
    """Turn a raw reply into the dict the node expects.

    Returns
    -------
    (value, problem)
        ``problem`` is ``None`` when the reply was usable; otherwise it is a
        short reason and ``value`` must not be used.
    """
    if not raw.strip():
        return {}, "empty reply"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {}, f"not JSON ({exc.msg})"
    if not isinstance(data, dict):
        return {}, f"expected an object, got {type(data).__name__}"

    if prompt == "classify severity":
        severity = data.get("severity")
        if severity not in SEVERITIES:
            return {}, f"severity {severity!r} not in {SEVERITIES}"
        return {"severity": severity}, None

    if prompt == "review diff":
        approved = data.get("approved")
        if not isinstance(approved, bool):
            return {}, f"approved {approved!r} is not a boolean"
        comments = data.get("comments", [])
        if not isinstance(comments, list) or not all(isinstance(c, str) for c in comments):
            return {}, "comments is not a list of strings"
        return {"approved": approved, "comments": comments}, None

    return {}, f"no validator for {prompt!r}"


def probe(
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    timeout: float = 300.0,
) -> None:
    """Fail early and legibly if the model is not actually servable.

    Deliberately does more than check ``/api/tags``. A listed model is not
    necessarily a usable one: an interrupted pull leaves the manifest in
    place with its blobs missing, so ``ollama list`` reports the model at
    full size and the first real call fails with a 404 halfway through a
    run. So this loads it with a throwaway generation and lets that be the
    check -- which also pays the model-loading cost here, where the message
    explains the wait, rather than inside the first node.

    Raises
    ------
    OllamaUnavailable
        Server down, tag not pulled, or pulled but not loadable.
    """
    base = base_url.rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=10) as resp:
            tags = [m.get("model") for m in json.load(resp).get("models", [])]
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OllamaUnavailable(
            f"cannot reach Ollama at {base_url}: {exc}\n"
            "  start it with:  ollama serve"
        ) from exc
    if model not in tags:
        raise OllamaUnavailable(
            f"{model!r} is not pulled; have {tags or '(none)'}\n"
            f"  pull it with:  ollama pull {model}"
        )
    GemmaJudge(model=model, base_url=base_url, timeout=timeout, verbose=False)._chat(
        "Reply with the severity 'low'.", {}, CALL_SITES["classify severity"]["schema"]
    )
