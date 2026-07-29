# MatrixWinCE Bridge — Agent Orchestration Integration

Wires batch_termux into MatrixWinCE's agent orchestration for multi-session management across devices.

## Architecture

```
batch_termux (device 1) ←→ MatrixWinCE Agent Foundry ←→ batch_termux (device N)
                              ↕
                        GGUF Server (port 5000)
                              ↕
                        LoRA Adapter Rotation
```

## Integration Points

1. **Agent routing** — batch commands are routed through MatrixWinCE's agent roster (voter_a, voter_b, coder, critic, miner, oracle)
2. **GGUF inference** — Uses MatrixWinCE's `gguf_server_v2.py` for model inference with LoRA support
3. **KG brain** — Results feed into MatrixWinCE's knowledge graph for agent specialization tracking
4. **Multi-device sync** — batch_termux instances on different devices coordinate via shared KV store

## Files

- `agent_bridge.py` — Python bridge to MatrixWinCE agent foundry
- `gguf_client.py` — Client for MatrixWinCE's GGUF server
- `sync_coordinator.py` — Multi-device session coordination

## Usage

```python
from matrixwince_bridge.agent_bridge import AgentBridge

bridge = AgentBridge()
result = bridge.route_command("cargo build --release", agent="coder")
print(result)
```
