#!/usr/bin/env python3
"""
SchedGen Pipeline Orchestrator
Manages development pipeline state, phases, and session handoffs.

Usage:
    python orchestrator.py status          — show current pipeline state
    python orchestrator.py start "task"    — start a new pipeline
    python orchestrator.py next            — advance to next phase (with confirmation)
    python orchestrator.py complete        — mark current task as done
    python orchestrator.py test            — run test_timewindow.py
    python orchestrator.py gen-verify      — show Codex verification prompt location
    python orchestrator.py handoff         — create SESSION_HANDOFF.md for new session
    python orchestrator.py reset           — reset pipeline state
"""

import json
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

# --- File paths ---
STATE_FILE = Path("pipeline_state.json")
HANDOFF_FILE = Path("SESSION_HANDOFF.md")
VERIFY_REPORT = Path("VERIFY_REPORT.md")
CODEX_PROMPT = Path("CODEX_VERIFY_PROMPT.md")
CODEX_RESPONSE = Path("CODEX_VERIFY_RESPONSE.md")
PROMPTS_DIR = Path("PROMPTS")
TEST_SCRIPT = Path("test_timewindow.py")
TEST_INPUT = Path("xlsx_initial/schedule_planning.xlsm")


# --- State helpers ---

def load_state():
    if not STATE_FILE.exists():
        return None
    with open(STATE_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# --- Commands ---

def cmd_status():
    state = load_state()
    if not state:
        print("\nNo active pipeline.")
        print("Start with: python orchestrator.py start \"task description\"")
        return

    total = state.get("total_phases", 1)
    current = state.get("current_phase", 1)
    pct = int((current - 1) / total * 100) if total > 0 else 0

    print(f"\n{'='*55}")
    print(f"  SchedGen Pipeline")
    print(f"{'='*55}")
    print(f"  Task     : {state['task']}")
    print(f"  Started  : {state['started_at'][:16].replace('T', ' ')}")
    print(f"  Phase    : {current}/{total}  [{pct}% complete]")
    print(f"  Status   : {state['status']}")
    print(f"  Iterations this phase: {state.get('phase_iterations', 0)}")

    phases = state.get("phases", [])
    if phases:
        print(f"\n  Phases:")
        for i, phase in enumerate(phases, 1):
            done = phase.get("done", False)
            if done:
                marker = "  ✓"
            elif i == current:
                marker = "  →"
            else:
                marker = "   "
            print(f"  {marker} {i}. {phase['name']}")

    changed = state.get("changed_files", [])
    if changed:
        print(f"\n  Changed files this session:")
        for f in changed:
            print(f"       {f}")

    print(f"{'='*55}\n")


def cmd_start(task):
    if not task.strip():
        print("Error: provide a task description.")
        print("  python orchestrator.py start \"task description\"")
        sys.exit(1)

    existing = load_state()
    if existing and existing.get("status") == "in_progress":
        confirm = input(
            f"Warning: active pipeline exists ({existing['task']!r}). "
            "Overwrite? [y/N]: "
        )
        if confirm.lower() != "y":
            print("Cancelled.")
            return

    state = {
        "task": task,
        "started_at": datetime.now().isoformat(),
        "current_phase": 1,
        "total_phases": 1,
        "status": "in_progress",
        "phase_iterations": 0,
        "phases": [{"name": "Phase 1", "done": False}],
        "changed_files": [],
        "history": [],
    }
    save_state(state)

    print(f"\nPipeline started: {task!r}")
    print(f"State file: {STATE_FILE}")
    print("\nNext steps:")
    print("  1. Run /orchestrate in Claude Code to create SPEC and prompts")
    print("  2. Apply the first generated prompt")
    print("  3. Run /verify to check the result")
    print("  4. Run: python orchestrator.py next  (to advance phase)")


def cmd_next():
    state = load_state()
    if not state:
        print("No active pipeline. Start with: python orchestrator.py start \"task\"")
        sys.exit(1)

    current = state["current_phase"]
    print(f"\nCurrent: Phase {current} | Task: {state['task']!r}")
    confirm = input(f"Mark Phase {current} complete and advance to Phase {current + 1}? [y/N]: ")
    if confirm.lower() != "y":
        print("Cancelled.")
        return

    # Archive current phase
    state["history"].append({
        "phase": current,
        "completed_at": datetime.now().isoformat(),
        "iterations": state.get("phase_iterations", 0),
    })

    # Mark phase done
    if current <= len(state["phases"]):
        state["phases"][current - 1]["done"] = True

    # Advance
    state["current_phase"] = current + 1
    state["total_phases"] = max(state.get("total_phases", 1), current + 1)
    state["phase_iterations"] = 0

    # Add new phase entry
    while len(state["phases"]) < state["current_phase"]:
        n = len(state["phases"]) + 1
        state["phases"].append({"name": f"Phase {n}", "done": False})

    save_state(state)
    print(f"Advanced to Phase {state['current_phase']}.")
    cmd_status()


def cmd_complete():
    state = load_state()
    if not state:
        print("No active pipeline.")
        sys.exit(1)

    print(f"\nTask: {state['task']!r}")
    confirm = input("Mark this task as COMPLETE? [y/N]: ")
    if confirm.lower() != "y":
        print("Cancelled.")
        return

    state["status"] = "completed"
    state["completed_at"] = datetime.now().isoformat()

    # Mark last phase done
    if state["phases"]:
        state["phases"][-1]["done"] = True

    save_state(state)
    print(f"\nTask completed: {state['task']!r}")
    print("Recommend: run /update-docs to refresh architecture documentation.")


def cmd_test():
    if not TEST_SCRIPT.exists():
        print(f"Test script not found: {TEST_SCRIPT}")
        sys.exit(1)

    if not TEST_INPUT.exists():
        print(f"Test input not found: {TEST_INPUT}")
        print("Provide path: python test_timewindow.py <excel_file> --verbose")
        sys.exit(1)

    cmd = [sys.executable, str(TEST_SCRIPT), str(TEST_INPUT), "--verbose"]
    print(f"Running: {' '.join(cmd)}\n")
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


def cmd_gen_verify():
    print()
    if CODEX_PROMPT.exists():
        print(f"Codex verification prompt: {CODEX_PROMPT.absolute()}")
        size = CODEX_PROMPT.stat().st_size
        print(f"Size: {size} bytes")
        print("\nInstructions:")
        print(f"  1. Open {CODEX_PROMPT} in VS Code")
        print(f"  2. Copy all content (Ctrl+A, Ctrl+C)")
        print(f"  3. Paste into Codex extension")
        print(f"  4. Save Codex response as: {CODEX_RESPONSE}")
        print(f"  5. Run /verify in Claude Code to consolidate results")
    else:
        print(f"No Codex prompt found at: {CODEX_PROMPT}")
        print("Run /verify in Claude Code first to generate it.")


def cmd_handoff():
    state = load_state()

    lines = [
        "# SchedGen Session Handoff",
        f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "\n---",
    ]

    # Pipeline state
    lines.append("\n## Active Pipeline")
    if state:
        lines.append(f"- **Task**: {state['task']}")
        lines.append(f"- **Started**: {state['started_at'][:16].replace('T', ' ')}")
        lines.append(f"- **Phase**: {state['current_phase']}/{state.get('total_phases', 1)}")
        lines.append(f"- **Status**: {state['status']}")
        lines.append(f"- **Iterations in current phase**: {state.get('phase_iterations', 0)}")

        phases = state.get("phases", [])
        if phases:
            lines.append("\n## Phase Progress")
            for i, phase in enumerate(phases, 1):
                if phase.get("done"):
                    icon = "✅"
                elif i == state["current_phase"]:
                    icon = "🔄"
                else:
                    icon = "⏳"
                lines.append(f"- Phase {i}: {phase['name']} — {icon}")

        history = state.get("history", [])
        if history:
            lines.append("\n## Completed Phases")
            for h in history:
                lines.append(
                    f"- Phase {h['phase']}: completed {h['completed_at'][:16].replace('T', ' ')}, "
                    f"{h['iterations']} iterations"
                )

        changed = state.get("changed_files", [])
        if changed:
            lines.append("\n## Changed Files This Session")
            for f in changed:
                lines.append(f"- `{f}`")
    else:
        lines.append("No active pipeline.")

    # SPEC files
    if PROMPTS_DIR.exists():
        specs = sorted(PROMPTS_DIR.glob("SPEC-*.md"))
        if specs:
            lines.append("\n## Active Spec Files")
            for s in specs:
                lines.append(f"- `{s}`")

    # Last verification
    if VERIFY_REPORT.exists():
        lines.append("\n## Last Verification Report (excerpt)")
        with open(VERIFY_REPORT, encoding="utf-8") as f:
            excerpt = f.readlines()[:15]
        lines.append("```")
        lines.extend(line.rstrip() for line in excerpt)
        if len(excerpt) == 15:
            lines.append("... (see VERIFY_REPORT.md for full report)")
        lines.append("```")

    # Codex status
    if CODEX_RESPONSE.exists():
        lines.append("\n⚠️ CODEX_VERIFY_RESPONSE.md exists — Codex review pending consolidation.")
        lines.append("Run /verify in new session to consolidate.")
    elif CODEX_PROMPT.exists():
        lines.append("\n⚠️ CODEX_VERIFY_PROMPT.md exists — Codex review not yet done.")
        lines.append("Paste it into Codex and save response as CODEX_VERIFY_RESPONSE.md.")

    # Next steps
    lines.append("\n## Next Steps for New Session")
    if state and state.get("status") == "in_progress":
        phase = state["current_phase"]
        lines.append(f"1. Check state: `python orchestrator.py status`")
        lines.append(f"2. Continue Phase {phase} — apply next prompt from `PROMPTS/`")
        lines.append(f"3. Run `/verify` after applying the prompt")
        lines.append(f"4. Use `python orchestrator.py next` to advance phases")
    elif state and state.get("status") == "completed":
        lines.append("1. Previous task completed. Start new: `python orchestrator.py start \"task\"`")
        lines.append("2. Run `/orchestrate \"task description\"` in Claude Code")
    else:
        lines.append("1. Start a new task: `python orchestrator.py start \"task description\"`")
        lines.append("2. Run `/orchestrate \"task description\"` in Claude Code")

    # Context reminder
    lines.append("\n## Project Context (paste into new session)")
    lines.append("- Architecture: `PROJECT_MAP.md`, `Structure-Claude.md`")
    lines.append("- Agents: `.claude/agents/` (spec-agent, prompt-generator, code-verifier, doc-updater, bug-analyzer)")
    lines.append("- Skills: `/orchestrate`, `/verify`, `/fix-cycle`, `/update-docs`")
    lines.append("- Pipeline tracker: `python orchestrator.py status`")
    lines.append("- Existing prompts: `PROMPTS/` (39+ files, see Fix-Sequence-Optimizer.md for context)")

    content = "\n".join(lines)
    with open(HANDOFF_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"\nSession handoff created: {HANDOFF_FILE.absolute()}")
    print("\nTo resume in a new session:")
    print(f"  1. Open a new Claude Code session")
    print(f"  2. Paste the contents of {HANDOFF_FILE} as your first message")
    print(f"  3. Claude Code will have full context from CLAUDE.md + your handoff")


def cmd_reset():
    if STATE_FILE.exists():
        state = load_state()
        task = state.get("task", "unknown") if state else "unknown"
        confirm = input(
            f"Reset pipeline state for {task!r}? This cannot be undone. [y/N]: "
        )
        if confirm.lower() == "y":
            STATE_FILE.unlink()
            print("Pipeline state reset.")
        else:
            print("Cancelled.")
    else:
        print("No pipeline state to reset.")


# --- Dispatch ---

COMMANDS = {
    "status":     (cmd_status,    0, "Show current pipeline state"),
    "start":      (cmd_start,     1, "Start new pipeline: start \"task\""),
    "next":       (cmd_next,      0, "Advance to next phase (with confirmation)"),
    "complete":   (cmd_complete,  0, "Mark current task as done"),
    "test":       (cmd_test,      0, "Run test_timewindow.py"),
    "gen-verify": (cmd_gen_verify, 0, "Show Codex verification prompt location"),
    "handoff":    (cmd_handoff,   0, "Create SESSION_HANDOFF.md for new session"),
    "reset":      (cmd_reset,     0, "Reset pipeline state"),
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        print("Commands:")
        for name, (_, _, desc) in COMMANDS.items():
            print(f"  {name:<14} {desc}")
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        print(f"Unknown command: {cmd!r}")
        print(f"Available: {', '.join(COMMANDS)}")
        sys.exit(1)

    func, nargs, _ = COMMANDS[cmd]
    extra_args = sys.argv[2:]

    if nargs == 1:
        func(" ".join(extra_args))
    else:
        func()


if __name__ == "__main__":
    main()
