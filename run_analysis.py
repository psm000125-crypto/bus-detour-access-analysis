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
      ["data_14/analyze_decisions.py"],
      ["data_14/verify_decisions.py"],
      ["data_17/analyze_access.py"],
      ["data_28/analyze_accessibility.py"],
      ["data_28/build_review_drafts.py"],
      ["data_29/reanalyze_platforms.py"],
      ["data_29/peer_verify_policy.py"],
      ["data_31/verify_revision_evidence.py"],
      ["data_33/verify_policy_choice.py"],
      ["data_34/verify_baselines.py"],
      ["-m","unittest","discover","-s","data_10","-p","test_walk_analysis.py","-v"],
      ["-m","unittest","discover","-s","data_11","-p","test_policy_models.py","-v"],
      ["-m","unittest","discover","-s","data_13","-p","test_review_models.py","-v"],
      ["-m","unittest","discover","-s","data_14","-p","test_decisions.py","-v"],
      ["-m","unittest","discover","-s","data_17","-p","test_access.py","-v"],
      ["-m","unittest","discover","-s","data_28","-p","test_revision.py","-v"],
      ["-m","unittest","discover","-s","data_29","-p","test_platforms.py","-v"],
    ]
    for args in commands:
        subprocess.run([sys.executable,*args],cwd=root,check=True)
    print("Current analysis and all computational checks completed. Geographic validity remains unverified.")

if __name__=="__main__":main()
