"""Recompute the submitted model, source checks and regression tests."""
from pathlib import Path
import subprocess
import sys

def main():
    if sys.version_info < (3, 12):
        raise SystemExit("Python 3.12 or newer is required by the pinned environment.")
    root = Path(__file__).resolve().parent
    (root / "data/results").mkdir(parents=True, exist_ok=True)
    for module in ("model", "verify_routes", "verify_policy", "verify_baselines", "verify_sources"):
        subprocess.run([sys.executable, "-m", "analysis." + module], cwd=root, check=True)
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=root, check=True)
    print("Analysis, route comparisons, source checks and tests completed.")

if __name__ == "__main__":
    main()
