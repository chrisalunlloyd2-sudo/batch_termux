#!/usr/bin/env python3
"""
batch_termux — Model Pacing Hooks
v0.2 — Oomph pacing modes, agent orchestration, quorum-aware inference
"""

import os
import sys
import json
import time
import subprocess
import logging
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, Any, List

LOG_DIR = Path("/data/data/com.termux/files/home/.batch_termux/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [PACER] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "model_pacer.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("model_pacer")

# ── Oomph Modes ──────────────────────────────────────────────
OOMPH_MODES = {
    "aggressive": {
        "min_interval": 0.25,
        "max_tokens": 256,
        "temperature": 0.8,
        "description": "Fast inference, high creativity",
    },
    "normal": {
        "min_interval": 0.5,
        "max_tokens": 128,
        "temperature": 0.7,
        "description": "Balanced speed and quality",
    },
    "conservative": {
        "min_interval": 1.0,
        "max_tokens": 64,
        "temperature": 0.5,
        "description": "Slow inference, conservative output",
    },
    "stealth": {
        "min_interval": 3.0,
        "max_tokens": 32,
        "temperature": 0.3,
        "description": "Minimal inference, deterministic",
    },
}


class ModelPacer:
    """Paces model inference based on resource pressure, oomph mode, and error feedback."""
    
    def __init__(self, 
                 ollama_url: str = "http://localhost:11434",
                 gguf_url: str = "http://localhost:5000",
                 default_model: str = "qwen2.5-coder:0.5b",
                 oomph: str = "normal"):
        self.ollama_url = ollama_url
        self.gguf_url = gguf_url
        self.default_model = default_model
        self.oomph = oomph
        self.mode = OOMPH_MODES.get(oomph, OOMPH_MODES["normal"])
        self.resource_state: Dict[str, float] = {"cpu": 0.0, "mem": 0.0, "disk": 0.0}
        self.pace_factor = 1.0
        self.consecutive_errors = 0
        self.last_inference_time = 0.0
        self.inference_count = 0
    
    def set_oomph(self, mode: str):
        """Switch pacing mode mid-session."""
        if mode in OOMPH_MODES:
            self.oomph = mode
            self.mode = OOMPH_MODES[mode]
            log.info(f"Oomph set to: {mode} — {self.mode['description']}")
    
    def update_resources(self, cpu: float, mem: float, disk: float):
        """Update resource state and recalculate pace factor."""
        self.resource_state = {"cpu": cpu, "mem": mem, "disk": disk}
        max_usage = max(cpu, mem, disk)
        
        # Thresholds depend on oomph mode
        thresholds = {
            "aggressive": 95, "normal": 90, "conservative": 80, "stealth": 60
        }
        threshold = thresholds.get(self.oomph, 90)
        
        if max_usage > threshold + 5:
            self.pace_factor = 0.1
        elif max_usage > threshold:
            self.pace_factor = 0.25
        elif max_usage > threshold - 10:
            self.pace_factor = 0.5
        elif max_usage > threshold - 20:
            self.pace_factor = 0.75
        else:
            self.pace_factor = 1.0
    
    def should_infer(self) -> bool:
        """Check if we should allow inference based on pacing."""
        if self.pace_factor < 0.2:
            log.warning(f"Pacing: CRITICAL ({self.pace_factor:.1f}) — blocking inference")
            return False
        
        min_interval = self.mode["min_interval"] / self.pace_factor
        elapsed = time.time() - self.last_inference_time
        
        if elapsed < min_interval:
            return False
        
        return True
    
    def query_ollama(self, prompt: str, model: Optional[str] = None,
                     max_tokens: Optional[int] = None) -> Optional[str]:
        """Query Ollama model with pacing."""
        if not self.should_infer():
            log.info("Pacing: inference blocked")
            return None
        
        model = model or self.default_model
        max_tokens = max_tokens or self.mode["max_tokens"]
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": self.mode["temperature"],
            }
        }
        
        try:
            req = urllib.request.Request(
                f"{self.ollama_url}/api/generate",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                self.last_inference_time = time.time()
                self.inference_count += 1
                self.consecutive_errors = 0
                return data.get("response", "")
        except Exception as e:
            self.consecutive_errors += 1
            log.error(f"Ollama error: {e}")
            return None
    
    def query_gguf(self, prompt: str, max_tokens: Optional[int] = None) -> Optional[str]:
        """Query GGUF server with pacing."""
        if not self.should_infer():
            return None
        
        max_tokens = max_tokens or self.mode["max_tokens"]
        payload = {"prompt": prompt, "max_tokens": max_tokens}
        
        try:
            req = urllib.request.Request(
                f"{self.gguf_url}/api/generate",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                self.last_inference_time = time.time()
                self.inference_count += 1
                self.consecutive_errors = 0
                return data.get("response", "")
        except Exception as e:
            self.consecutive_errors += 1
            log.error(f"GGUF error: {e}")
            return None
    
    def suggest_fix(self, error_text: str, context: str = "") -> Optional[str]:
        """Ask the model to suggest a fix for an error."""
        prompt = f"""You are an autonomous repair agent. Given this error and context, suggest a fix command.

Error:
{error_text[:500]}

Context:
{context[:500]}

Suggest a single shell command to fix this issue. Be concise. Only output the command, nothing else.
Fix command:"""
        
        response = self.query_ollama(prompt, max_tokens=64)
        if response:
            return response.strip().strip('"\'`')
        
        response = self.query_gguf(prompt, max_tokens=64)
        if response:
            return response.strip().strip('"\'`')
        
        return None
    
    def get_status(self) -> dict:
        return {
            "oomph": self.oomph,
            "pace_factor": self.pace_factor,
            "resources": self.resource_state,
            "inference_count": self.inference_count,
            "consecutive_errors": self.consecutive_errors,
            "last_inference": self.last_inference_time,
            "mode": self.mode,
        }


# ── CLI ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="batch_termux Model Pacer")
    parser.add_argument("action", choices=["status", "suggest", "query", "set-oomph"],
                        help="Action to perform")
    parser.add_argument("--error", "-e", help="Error text for suggest action")
    parser.add_argument("--prompt", "-p", help="Prompt for query action")
    parser.add_argument("--oomph", "-o", default="normal",
                        choices=list(OOMPH_MODES.keys()), help="Pacing mode")
    parser.add_argument("--cpu", type=float, default=50.0, help="CPU usage %")
    parser.add_argument("--mem", type=float, default=60.0, help="Memory usage %")
    parser.add_argument("--disk", type=float, default=70.0, help="Disk usage %")
    
    args = parser.parse_args()
    pacer = ModelPacer(oomph=args.oomph)
    pacer.update_resources(args.cpu, args.mem, args.disk)
    
    if args.action == "status":
        print(json.dumps(pacer.get_status(), indent=2))
    elif args.action == "set-oomph":
        pacer.set_oomph(args.oomph)
        print(f"Oomph set to: {args.oomph}")
    elif args.action == "suggest" and args.error:
        fix = pacer.suggest_fix(args.error)
        if fix:
            print(fix)
        else:
            print("No fix suggested")
            sys.exit(1)
    elif args.action == "query" and args.prompt:
        response = pacer.query_ollama(args.prompt)
        if response:
            print(response)
        else:
            print("No response")
            sys.exit(1)
