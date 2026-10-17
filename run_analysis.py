"""Recompute the current model and its checks using staged local source data."""
from pathlib import Path
import subprocess
import sys

def main():
    if sys.version_info < (3,12):
        raise SystemExit("Python 3.12 or newer is required by the pinned environment.")
    root=Path(__file__).resolve().parent
    commands=[
      ["data_13/recompute_expanded.py"],
      ["data_13/verify_review.py"],
      ["-m","unittest","discover","-s","data_10","-p","test_walk_analysis.py","-v"],
      ["-m","unittest","discover","-s","data_11","-p","test_policy_models.py","-v"],
      ["-m","unittest","discover","-s","data_13","-p","test_review_models.py","-v"],
    ]
    for args in commands:
        subprocess.run([sys.executable,*args],cwd=root,check=True)
    print("Current analysis and all computational checks completed. Geographic validity remains unverified.")

if __name__=="__main__":main()
