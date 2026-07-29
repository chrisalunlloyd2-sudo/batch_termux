# SIMS1337 Bridge — Quorum Voting Integration

Wires batch_termux into SIMS1337's quorum voting engine for autonomous command approval.

## Architecture

```
batch_termux command → SIMS1337 Quorum Vote → approved? → execute
                                        ↓
                                   rejected? → log + notify
```

## Integration Points

1. **Pre-execution vote** — Every batch command is submitted to SIMS1337's `WeightedQuorumVote` before execution
2. **FOW coordination** — Uses SIMS1337's hex-based FOW locks to prevent duplicate execution
3. **Time pulse sync** — Syncs with SIMS1337's `TimePulse` for coordinated execution timing
4. **Result feedback** — Execution results feed back into SIMS1337's win/loss tracking

## Files

- `quorum_bridge.py` — Python bridge to SIMS1337's Java voting engine
- `fow_coordinator.py` — FOW lock coordination (reuses `/root/sov/fow_patch.py`)
- `vote_submitter.py` — Submits commands as vote proposals

## Usage

```python
from sims1337_bridge.quorum_bridge import QuorumBridge

bridge = QuorumBridge()
approved = bridge.vote_command("cargo build --release")
if approved:
    subprocess.run("cargo build --release", shell=True)
```
