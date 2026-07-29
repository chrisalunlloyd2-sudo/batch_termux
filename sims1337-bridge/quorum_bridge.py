#!/usr/bin/env python3
"""
SIMS1337 Quorum Bridge — submits batch commands to quorum voting before execution.
Reuses SIMS1337's WeightedQuorumVote and FOW coordination.
"""

import json
import os
import subprocess
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any

LOG_DIR = Path("/data/data/com.termux/files/home/.batch_termux/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [QUORUM] %(levelname)s %(message)s",
    handlers=[logging.FileHandler(LOG_DIR / "quorum.log"), logging.StreamHandler()],
)
log = logging.getLogger("quorum")


class QuorumBridge:
    """Bridges batch_termux commands to SIMS1337 quorum voting."""
    
    def __init__(self, sov_dir: str = "/root/sov"):
        self.sov_dir = Path(sov_dir)
        self.kg_file = self.sov_dir / "kg" / "entities.json"
        self.kv_file = self.sov_dir / "kv" / "data.json"
        self.fow_file = self.sov_dir / "fow" / "locks.json"
    
    def vote_command(self, command: str, priority: int = 0) -> bool:
        """
        Submit a command to quorum voting.
        Returns True if approved, False if rejected.
        """
        # 1. Check FOW lock
        if not self._check_fow_lock(command):
            log.warning(f"FOW lock held for: {command[:60]}")
            return False
        
        # 2. Calculate vote weight based on command type
        weight = self._calculate_weight(command, priority)
        
        # 3. Record vote in KV store
        vote_id = f"vote_{int(time.time())}"
        vote_record = {
            "id": vote_id,
            "command": command,
            "priority": priority,
            "weight": weight,
            "timestamp": time.time(),
            "approved": weight > 0.5,  # Simple threshold
            "voter": "batch_termux",
        }
        
        self._store_vote(vote_id, vote_record)
        
        if vote_record["approved"]:
            log.info(f"VOTE APPROVED ({weight:.2f}): {command[:60]}")
        else:
            log.warning(f"VOTE REJECTED ({weight:.2f}): {command[:60]}")
        
        return vote_record["approved"]
    
    def _check_fow_lock(self, command: str) -> bool:
        """Check if FOW lock is available for this command."""
        try:
            if self.fow_file.exists():
                locks = json.loads(self.fow_file.read_text())
                cmd_hash = str(hash(command) % 1000)
                if cmd_hash in locks:
                    lock = locks[cmd_hash]
                    if time.time() - lock.get("timestamp", 0) < 1800:  # 30 min
                        return False
            return True
        except Exception:
            return True
    
    def _calculate_weight(self, command: str, priority: int) -> float:
        """Calculate vote weight based on command characteristics."""
        weight = 0.5  # Base weight
        
        # Higher priority = more weight
        weight += priority * 0.1
        
        # Dangerous commands get lower weight
        dangerous = ["rm -rf", "dd if=", "mkfs", "format", "> /dev/"]
        for d in dangerous:
            if d in command:
                weight -= 0.3
        
        # Read-only commands get higher weight
        readonly = ["cat", "ls", "echo", "grep", "find", "head", "tail"]
        for r in readonly:
            if command.startswith(r):
                weight += 0.2
        
        # Build/test commands get moderate weight
        build = ["cargo", "make", "python3", "pytest", "npm"]
        for b in build:
            if command.startswith(b):
                weight += 0.1
        
        return max(0.0, min(1.0, weight))
    
    def _store_vote(self, vote_id: str, record: dict):
        """Store vote record in KV store."""
        try:
            if self.kv_file.exists():
                data = json.loads(self.kv_file.read_text())
            else:
                data = {}
            data[f"quorum.{vote_id}"] = {
                "value": record,
                "timestamp": time.time(),
            }
            self.kv_file.parent.mkdir(parents=True, exist_ok=True)
            self.kv_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            log.error(f"Failed to store vote: {e}")
    
    def get_vote_history(self, limit: int = 10) -> list:
        """Get recent vote history."""
        try:
            if self.kv_file.exists():
                data = json.loads(self.kv_file.read_text())
                votes = []
                for k, v in data.items():
                    if k.startswith("quorum."):
                        votes.append(v["value"])
                votes.sort(key=lambda x: x["timestamp"], reverse=True)
                return votes[:limit]
        except Exception:
            pass
        return []


# ── CLI ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SIMS1337 Quorum Bridge")
    parser.add_argument("command", help="Command to vote on")
    parser.add_argument("--priority", "-p", type=int, default=0, help="Priority (0-10)")
    parser.add_argument("--history", "-H", action="store_true", help="Show vote history")
    
    args = parser.parse_args()
    bridge = QuorumBridge()
    
    if args.history:
        for v in bridge.get_vote_history():
            status = "✓" if v["approved"] else "✗"
            print(f"{status} [{v['weight']:.2f}] {v['command'][:60]}")
    else:
        approved = bridge.vote_command(args.command, args.priority)
        print("APPROVED" if approved else "REJECTED")
        exit(0 if approved else 1)
