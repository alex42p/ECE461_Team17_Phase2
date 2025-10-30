
from __future__ import annotations
import subprocess
import sys
import re

def run_tests() -> int: 
    """
    Run pytest with coverage, suppress its normal output,
    and print only "X/Y test cases passed. Z% line coverage achieved."
    """
    proc = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "--cov=src/",
            "--cov-report=term-missing",
            "tests/",
        ],
        capture_output=True,
        text=True
    )
    # Show full pytest/coverage output
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)

    stdout: str = proc.stdout

    # Extract coverage percentage
    coverage_percent: int = 0

    match = re.search(r"^TOTAL\b.*?(\d+)%\s*$", stdout, re.MULTILINE | re.IGNORECASE)
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
    
    # Return 0 if all tests passed, regardless of coverage warnings
    if failed == 0:
        return 0
    return 1