import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_step(label, args):
    print(f"\n== {label} ==", flush=True)
    result = subprocess.run([sys.executable, *args], cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-target-refresh", action="store_true")
    parser.add_argument("--skip-wine-collection", action="store_true")
    parser.add_argument("--max-targets", type=int, default=0)
    args = parser.parse_args()

    if not args.skip_target_refresh:
        run_step(
            "Refresh guide restaurant candidates and source addresses",
            ["scripts/guide_collect_targets.py", "--sources", "michelin,laliste,worlds50best"],
        )
    run_step(
        "Audit restaurant map pins and official websites",
        ["scripts/guide_audit_locations.py", "--max-targets", str(args.max_targets)],
    )
    if not args.skip_wine_collection:
        run_step(
            "Recollect wine-list data from verified restaurants",
            [
                "scripts/guide_discover_wine_lists.py",
                "--max-targets",
                str(args.max_targets),
                "--refresh-websites",
                "--recheck-all",
            ],
        )


if __name__ == "__main__":
    main()
