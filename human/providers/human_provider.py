import sys

VALID = {"pass", "fail", "p", "f"}

def call_api(prompt, options, context):
    print("\n" + "=" * 70)
    print(prompt)
    print("=" * 70)
    print("\nEnter your judgment — type  pass  or  fail  then press Enter:")

    while True:
        try:
            raw = input("  > ").strip().lower()
        except EOFError:
            raw = "fail"

        if raw in VALID:
            answer = "pass" if raw in ("pass", "p") else "fail"
            print(f"  Recorded: {answer}\n")
            return {"output": answer}

        print("  Invalid input. Please type  pass  or  fail")
