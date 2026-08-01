# 🧭 Onboarding Injection — the missing piece for SLM success

When an SLM spawns into the hex FOW matrix, it needs ORIENTATION and
CONTINUITY. This module injects a **boarding pass** into every model
invocation in the batch terminals.

## Why this exists
The batch terminals had: hooks, error feedback, pacing, quorum bridges.
**Missing:** the model had no idea *where* it was, *what it could see*,
or *what was decided before*. Every spawn was amnesiac. This fixes that.

## The boarding pass
```
═══ SLM ONBOARDING — BOARDING PASS ═══
AGENT:      phase4-agents
MODEL:      qwen2.5:0.5b
HEX:        (2,1)
VISIBLE:    (2,1) (3,1) ... (2,2)   [FOW 1-hop]
KNOWLEDGE:  ◉ /projects/SIMS1337/phases/phase4-agents
            ○ 1-hop: /projects/SIMS1337, markov-voting, ...
TASKS:      ▸ /tasks/deploy-tonight
CONTINUITY: ▸ YES (conf=0.85) — Should we deploy phase 4?
MISSION:    <explicit directive>
═══ END BOARDING PASS ═══
```

## Integration points
| Layer | What gets the pass |
|-------|--------------------|
| `injector.py` | Standalone CLI + Python API for any batch call |
| batch daemon | Prepend `injector.pre_invoke(model, hex, role, mission)` to each model prompt |
| quorum_bridge | Pass through to voters so they vote with context |
| agent_bridge  | Pass through so agents act with orientation |

## Env vars
- `TOC_TOK_FILE` — path to the hex-anchored knowledge tree (toc_tok.json)
- `ONBOARD_SCRIPT` — path to SIMS1337 scripts/toc_tok/onboard.py
  (defaults to ../../SIMS1337/scripts/toc_tok/onboard.py)

## Usage
```bash
# Inject a pass + append a prompt
python3 python-cascade/onboarding/injector.py \
  --model qwen2.5:0.5b --hex 2,1 --role coder \
  --mission "Write the deploy script" --prompt "Task: ..."

# Python API inside the daemon
from onboarding.injector import OnboardingInjector
inj = OnboardingInjector()
full_prompt = inj.pre_invoke("qwen2.5:0.5b", "2,1", "coder", mission) + user_prompt
```

## The TOC-TOK tree (what lives in the map)
```
python3 SIMS1337/scripts/toc_tok/toc_tok.py tree
python3 SIMS1337/scripts/toc_tok/toc_tok.py at 2,1
python3 SIMS1337/scripts/toc_tok/toc_tok.py search markov
```
Every project/phase/task is a node anchored to a hex. Models navigate by
tree path AND by space. Onboarding = tree + map + continuity = orientation.
