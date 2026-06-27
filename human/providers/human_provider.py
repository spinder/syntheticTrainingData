import os
import sys
from datetime import datetime

VALID = {"pass", "fail", "p", "f"}

# Failure notes accumulate here during a session.
# This file is gitignored; its contents are embedded in git commit messages
# by the promptTools.sh commit helper so the history lives in git log.
_NOTES_FILE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "../logs/.session_notes.txt")
)


def _context_label(context) -> str:
    """Return the test description, e.g. 'item_001_plumbing | D2 safety_specificity'."""
    if not context:
        return "unknown"
    test = context.get("test") or {}
    desc = test.get("description", "")
    if desc:
        return desc
    # Fallback: build from vars
    vars_ = context.get("vars") or {}
    item = str(vars_.get("item", "?")).split("/")[-1].replace(".txt", "")
    q    = str(vars_.get("question", "?")).split("/")[-1].replace(".txt", "")
    return f"{item} | {q}"


def _append_note(label: str, note: str) -> None:
    """Write one failure note to the session notes file."""
    os.makedirs(os.path.dirname(_NOTES_FILE), exist_ok=True)
    ts   = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    line = f"[{ts}] [{label}] FAIL — {note}\n"
    with open(_NOTES_FILE, "a") as fh:
        fh.write(line)


def call_api(prompt, options, context):
    # All display output goes to stderr — stdout is reserved for promptfoo's JSON protocol.
    # Input is read from /dev/tty so it reaches the real terminal even when stdin is piped.
    sys.stderr.write("\n" + "=" * 70 + "\n")
    sys.stderr.write(prompt + "\n")
    sys.stderr.write("=" * 70 + "\n")
    sys.stderr.write("\nEnter your judgment — type  pass  or  fail  then press Enter:\n")
    sys.stderr.flush()

    with open("/dev/tty", "r") as tty:
        while True:
            sys.stderr.write("  > ")
            sys.stderr.flush()
            raw = tty.readline().strip().lower()

            if raw not in VALID:
                sys.stderr.write("  Invalid input. Please type  pass  or  fail\n")
                sys.stderr.flush()
                continue

            answer = "pass" if raw in ("pass", "p") else "fail"
            sys.stderr.write(f"  Recorded: {answer}\n")
            sys.stderr.flush()

            if answer == "fail":
                sys.stderr.write("  Why did it fail? (one line, or Enter to skip):\n")
                sys.stderr.write("  > ")
                sys.stderr.flush()
                note = tty.readline().strip()
                sys.stderr.write("\n")
                sys.stderr.flush()
                if note:
                    _append_note(_context_label(context), note)

            else:
                sys.stderr.write("\n")
                sys.stderr.flush()

            return {"output": answer}
