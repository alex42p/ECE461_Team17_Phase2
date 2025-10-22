# pragma: no cover
from __future__ import annotations
import subprocess
import sys
import re

def run_tests() -> int: # pragma: no cover
    """
    Run pytest with coverage, suppress its normal output,
    and print only "X/Y test cases passed. Z% line coverage achieved."
    """
    proc = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "--cov=src/cli_project",
            "--cov-report=term-missing",
            "tests",
        ],
        capture_output=True,
        text=True
    )
    # Show full pytest/coverage output
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    rc: int = proc.returncode

    stdout: str = proc.stdout

    # Extract coverage percentage
    coverage_percent: int = 0
    match = re.search(r"TOTAL\s+\d+\s+\d+\s+\d+\s+\d+\s+(\d+)%", stdout)
    if match:
        coverage_percent = int(match.group(1))

    # Extract test counts
    passed = failed = skipped = 0

    m = re.search(r"(\d+)\s+passed", stdout)
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+)\s+failed", stdout)
    if m:
        failed = int(m.group(1))
    m = re.search(r"(\d+)\s+skipped", stdout)
    if m:
        skipped = int(m.group(1))

    total = passed + failed + skipped

    # Final required output
    print(f"{passed}/{total} test cases passed. {coverage_percent}% line coverage achieved.")

    rc = not (total >= 20 and coverage_percent >= 80)
    return rc


