import sys

VALID = {"pass", "fail", "p", "f"}

def call_api(prompt, options, context):
    # All display output goes to stderr — stdout is reserved for promptfoo's JSON protocol.
    # Input is read from /dev/tty so it reaches the real terminal even though stdin is piped.
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
            if raw in VALID:
                answer = "pass" if raw in ("pass", "p") else "fail"
                sys.stderr.write(f"  Recorded: {answer}\n\n")
                sys.stderr.flush()
                return {"output": answer}
            sys.stderr.write("  Invalid input. Please type  pass  or  fail\n")
            sys.stderr.flush()
