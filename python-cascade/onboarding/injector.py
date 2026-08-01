#!/usr/bin/env python3
"""
onboarding/injector.py — SLM ONBOARDING INJECTION for batch_termux

The missing piece for seamless SLM onboarding:
every model invocation in the batch terminals gets a boarding pass injected
(hex position, FOW visibility, TOC-TOK knowledge, continuity) so the model
knows where it is, what it can see, and what was decided before.

Works with:
  - SIMS1337 scripts/toc_tok/onboard.py  (boarding-pass generator)
  - TOC_TOK_FILE (hex-anchored knowledge tree)

Hook points:
  - pre_invoke(model, hex, role): returns prompt prefix to prepend
  - continuity(): last decisions from chain_decisions.jsonl / chain_log.jsonl
"""
import json, os, subprocess, sys, time
from pathlib import Path

DEFAULT_TOC = os.environ.get("TOC_TOK_FILE", "")
ONBOARD_SCRIPT = os.environ.get("ONBOARD_SCRIPT",
    str(Path(__file__).parent / ".." / ".." / ".." / "SIMS1337" / "scripts" / "toc_tok" / "onboard.py"))

class OnboardingInjector:
    def __init__(self, toc_file=None, continuity_paths=None):
        self.toc_file = toc_file or DEFAULT_TOC
        self.continuity_paths = continuity_paths or [
            "chain_decisions.jsonl", "chain_log.jsonl", "call_log.jsonl",
            str(Path.home() / ".batch_termux" / "logs" / "decisions.jsonl"),
        ]

    def boarding_pass(self, model, hex_str, role, mission=""):
        """Generate the pass via onboard.py (or built-in fallback)."""
        if os.path.exists(ONBOARD_SCRIPT):
            try:
                env = dict(os.environ)
                if self.toc_file:
                    env["TOC_TOK_FILE"] = self.toc_file
                cmd = [sys.executable, ONBOARD_SCRIPT, "--model", model,
                       "--hex", hex_str, "--role", role,
                       "--mission", mission or "Await instructions within visible hexes."]
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
                if r.returncode == 0 and r.stdout.strip():
                    return r.stdout.strip()
            except Exception as e:
                print(f"[onboarding] onboard.py failed ({e}) — using fallback", file=sys.stderr)
        # built-in fallback
        return self._fallback_pass(model, hex_str, role, mission)

    def _fallback_pass(self, model, hex_str, role, mission):
        cont = self.read_continuity()
        lines = [
            "═══ SLM ONBOARDING — BOARDING PASS (fallback) ═══",
            f"AGENT: {role}", f"MODEL: {model}", f"HEX: ({hex_str})",
            f"ROLE: {role}",
            "KNOWLEDGE: TOC-TOK tree not loaded — operate on explicit instructions only.",
        ]
        if cont:
            lines.append("CONTINUITY:")
            for c in cont[-3:]:
                lines.append(f"  ▸ {c.get('final', c.get('decision','?'))} "
                             f"(conf={c.get('chain_confidence', c.get('confidence','?'))})")
        lines.append(f"MISSION: {mission}")
        lines.append("═══ END BOARDING PASS ═══")
        return "\n".join(lines)

    def read_continuity(self, limit=3):
        out = []
        for path in self.continuity_paths:
            if not os.path.exists(path): continue
            try:
                with open(path) as f:
                    for line in f:
                        line = line.strip()
                        if not line: continue
                        try: out.append(json.loads(line))
                        except Exception: continue
            except Exception: continue
            if len(out) >= limit: break
        return out[-limit:]

    def pre_invoke(self, model, hex_str, role, mission=""):
        """Returns the boarding-pass prefix to prepend to a model prompt."""
        return self.boarding_pass(model, hex_str, role, mission) + "\n\n"

# CLI
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Inject SLM boarding pass into batch commands")
    p.add_argument("--model", default="qwen2.5:0.5b")
    p.add_argument("--hex", default="0,0")
    p.add_argument("--role", default="batch-worker")
    p.add_argument("--mission", default="")
    p.add_argument("--prompt", help="optional user prompt to append after the pass")
    args = p.parse_args()
    inj = OnboardingInjector()
    text = inj.pre_invoke(args.model, args.hex, args.role, args.mission)
    if args.prompt:
        text += args.prompt + "\n"
    print(text)
