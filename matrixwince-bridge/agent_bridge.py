#!/usr/bin/env python3
"""
MatrixWinCE Agent Bridge — routes batch commands through agent foundry.
Uses GGUF server for inference, KG for agent specialization.
"""

import json
import os
import subprocess
import time
import urllib.request
import urllib.error
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

LOG_DIR = Path("/data/data/com.termux/files/home/.batch_termux/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [AGENT] %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "agent_bridge.log"), logging.StreamHandler()],
)
log = logging.getLogger("agent_bridge")


class AgentBridge:
    """Routes batch commands through MatrixWinCE's agent foundry."""
    
    AGENTS = {
        "voter_a": {"specialty": "vote", "bias": "approve"},
        "voter_b": {"specialty": "vote", "bias": "reject"},
        "voter_c": {"specialty": "vote", "bias": "swing"},
        "coder": {"specialty": "code", "bias": "generate"},
        "critic": {"specialty": "review", "bias": "strict"},
        "miner": {"specialty": "mine", "bias": "explore"},
        "oracle": {"specialty": "tiebreak", "bias": "final"},
    }
    
    def __init__(self, gguf_url: str = "http://localhost:5000",
                 sov_dir: str = "/root/sov"):
        self.gguf_url = gguf_url
        self.sov_dir = Path(sov_dir)
        self.kg_file = self.sov_dir / "kg" / "entities.json"
    
    def route_command(self, command: str, agent: str = "coder",
                      context: str = "") -> Optional[str]:
        """
        Route a command through a specific agent.
        Returns agent's response or None on failure.
        """
        if agent not in self.AGENTS:
            log.error(f"Unknown agent: {agent}")
            return None
        
        agent_info = self.AGENTS[agent]
        prompt = self._build_prompt(command, agent_info, context)
        
        # Try GGUF server
        response = self._query_gguf(prompt)
        if response:
            log.info(f"Agent [{agent}]: {response[:100]}")
            self._record_usage(agent, command)
            return response
        
        return None
    
    def _build_prompt(self, command: str, agent: dict, context: str) -> str:
        """Build a prompt for the agent based on its specialty."""
        templates = {
            "vote": f"Vote on this command: {command}\nContext: {context}\nBias: {agent['bias']}\nDecision (approve/reject):",
            "code": f"Generate code for: {command}\nContext: {context}\nOutput only the code, no explanation:",
            "review": f"Review this command: {command}\nContext: {context}\nIssues found (list each):",
            "mine": f"Explore and find: {command}\nContext: {context}\nFindings:",
            "tiebreak": f"Tiebreaker vote on: {command}\nContext: {context}\nFinal decision:",
        }
        return templates.get(agent["specialty"], f"Process: {command}\nContext: {context}\nResult:")
    
    def _query_gguf(self, prompt: str, max_tokens: int = 128) -> Optional[str]:
        """Query the GGUF inference server."""
        payload = {"prompt": prompt, "max_tokens": max_tokens}
        try:
            req = urllib.request.Request(
                f"{self.gguf_url}/api/generate",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                return data.get("response", "")
        except Exception as e:
            log.error(f"GGUF query failed: {e}")
            return None
    
    def _record_usage(self, agent: str, command: str):
        """Record agent usage in KG."""
        try:
            if self.kg_file.exists():
                kg = json.loads(self.kg_file.read_text())
            else:
                kg = {}
            
            key = f"agent_usage.{agent}"
            if key not in kg:
                kg[key] = {"count": 0, "commands": []}
            kg[key]["count"] += 1
            kg[key]["commands"].append({
                "command": command[:100],
                "timestamp": time.time(),
            })
            kg[key]["commands"] = kg[key]["commands"][-50:]  # Keep last 50
            
            self.kg_file.parent.mkdir(parents=True, exist_ok=True)
            self.kg_file.write_text(json.dumps(kg, indent=2))
        except Exception as e:
            log.error(f"Failed to record usage: {e}")
    
    def get_agent_stats(self) -> dict:
        """Get agent usage statistics."""
        try:
            if self.kg_file.exists():
                kg = json.loads(self.kg_file.read_text())
                stats = {}
                for k, v in kg.items():
                    if k.startswith("agent_usage."):
                        agent = k.replace("agent_usage.", "")
                        stats[agent] = v["count"]
                return stats
        except Exception:
            pass
        return {}


# ── CLI ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MatrixWinCE Agent Bridge")
    parser.add_argument("command", help="Command to route")
    parser.add_argument("--agent", "-a", default="coder",
                        choices=list(AgentBridge.AGENTS.keys()),
                        help="Agent to use")
    parser.add_argument("--context", "-c", default="", help="Additional context")
    parser.add_argument("--stats", "-s", action="store_true", help="Show agent stats")
    
    args = parser.parse_args()
    bridge = AgentBridge()
    
    if args.stats:
        for agent, count in bridge.get_agent_stats().items():
            print(f"{agent}: {count} uses")
    else:
        response = bridge.route_command(args.command, args.agent, args.context)
        if response:
            print(response)
        else:
            print("No response from agent")
            exit(1)
