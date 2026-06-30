"""
promote.py — Step 3 "Own": turn a fork into a first-class owned repo.

GitHub has no API to detach a fork from its upstream network, so promotion is
a decision + a git checklist the user runs (same model as migration.py). The
*decision* is an ordinary plan verdict (keep / absorb-into-hub / archive); this
module only produces the detach checklist.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def _rule_checklist(fork: dict, hub: str | None, parent: str | None) -> list[str]:
    name = fork["name"]
    up = parent or "its upstream"
    steps = [
        f"Confirm you want {name} as your own repo, independent of {up}.",
        f"Create the destination owned repo (git-suite can create it), or use "
        f"GitHub → Settings → 'Leave fork network' on {name}.",
        f"Mirror history: `git clone --mirror` {name}, then `git push --mirror` "
        f"to the destination — preserves all branches/tags.",
        "Re-point local remotes and any CI to the destination repo.",
        f"Pull any wanted changes from {up} one last time, then cut the link "
        f"(no more syncing from upstream).",
    ]
    if hub:
        steps.append(
            f"Standardise {name} to {hub}'s baseline (structure, docs, tests) so "
            f"the hub can compose it.")
    steps.append(f"Archive or delete the old fork {name} on GitHub once the "
                 f"destination is live.")
    return steps


async def _llm_checklist(fork: dict, hub: str | None, parent: str | None,
                         readme: str | None) -> list[str] | None:
    from services import llm
    if not llm.has_provider():
        return None
    try:
        prompt = f"""You are planning how to PROMOTE a GitHub fork into a first-class
owned repo that no longer depends on its upstream (GitHub has no API to detach
a fork, so this is a manual git plan).

Fork:
  name: {fork['name']}
  forked from: {parent or 'unknown upstream'}
  language: {fork.get('language') or 'unknown'}
  description: {fork.get('aim') or '(none)'}
  README excerpt:
  ---
  {(readme or '(no README)')[:1500]}
  ---

Destination hub (if any): {hub or '(standalone — no hub)'}

Write a concrete, ordered checklist (5-8 steps) to own this repo independently:
detach from the fork network (mirror push to a fresh repo, or leave-fork-network),
re-point remotes/CI, cut upstream sync, and {('standardise it to the hub baseline'
if hub else 'keep it standalone')}. Each step is one imperative sentence.

Return ONLY a JSON array of strings, no markdown."""
        steps = await llm.complete_json(prompt, max_tokens=700)
        if isinstance(steps, list) and steps:
            return [str(s) for s in steps]
    except Exception as exc:
        log.warning("LLM promote checklist failed for %s: %s", fork.get("name"), exc)
    return None


async def checklist_for(fork: dict, hub: str | None, parent: str | None,
                        readme: str | None) -> dict:
    """Return {steps, source} — LLM-tailored if possible, else a rule template."""
    steps = await _llm_checklist(fork, hub, parent, readme)
    if steps:
        return {"steps": steps, "source": "llm"}
    return {"steps": _rule_checklist(fork, hub, parent), "source": "rule"}


if __name__ == "__main__":
    # ponytail: smallest self-check — the rule checklist covers the detach,
    # mentions the hub only when given one, and always ends with old-fork cleanup.
    base = _rule_checklist({"name": "winutil"}, None, "ChrisTitusTech/winutil")
    assert any("mirror" in s for s in base), base
    assert any("Leave fork network" in s for s in base), base
    assert "Archive or delete" in base[-1], base
    assert not any("baseline" in s for s in base)          # no hub -> no standardise step
    withhub = _rule_checklist({"name": "winutil"}, "homelab-core", "x/y")
    assert any("homelab-core" in s and "baseline" in s for s in withhub), withhub
    print("promote.py self-check OK")
