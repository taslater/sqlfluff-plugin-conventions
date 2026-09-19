"""Fail when the mutation score drops below a floor.

Reads mutmut's own results (run ``mutmut run`` first) and reports the score,
with the surviving mutants listed so a failure is actionable. The floor is a
ratchet: raise it as tests improve; never lower it to make a run pass.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--floor", type=float, default=80.0)
    args = parser.parse_args()

    process = subprocess.run(
        [sys.executable, "-m", "mutmut", "results", "--all", "true"],
        capture_output=True,
        text=True,
        check=False,
    )
    output = process.stdout + process.stderr
    killed = len(re.findall(r": killed$", output, re.MULTILINE))
    survived = len(re.findall(r": survived$", output, re.MULTILINE))
    timeouts = len(re.findall(r": timeout$", output, re.MULTILINE))
    total = killed + survived + timeouts
    if total == 0:
        print("No mutation results found; run `mutmut run` first.", file=sys.stderr)
        return 2
    score = 100.0 * killed / total
    print(
        f"mutation score: {score:.1f}% ({killed}/{total} killed, "
        f"{survived} survived, {timeouts} timed out)"
    )

    if survived:
        print("\nSurvivors:")
        for line in output.splitlines():
            if line.endswith(": survived"):
                print(f"  {line.rsplit(':', 1)[0]}")

    if score < args.floor:
        print(
            f"\nFAIL: mutation score {score:.1f}% is below the floor of "
            f"{args.floor:.1f}%",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
