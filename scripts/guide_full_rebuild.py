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
    parser.add_argument("--enable-google-places", action="store_true", help="Allow paid Google Places calls. Off by default.")
    parser.add_argument("--max-google-requests", type=int, default=200)
    args = parser.parse_args()

    if not args.skip_target_refresh:
        run_step(
            "Refresh guide restaurant candidates and source addresses",
            ["scripts/guide_collect_targets.py", "--sources", "michelin,laliste,worlds50best"],
        )
    if args.enable_google_places:
        run_step(
            "Audit restaurant map pins and official websites",
            [
                "scripts/guide_audit_locations.py",
                "--max-targets",
                str(args.max_targets),
                "--enable-google-places",
                "--max-google-requests",
                str(args.max_google_requests),
            ],
        )
    else:
        print("\n== Audit restaurant map pins and official websites ==", flush=True)
        print("Skipped paid Google Places audit. Use --enable-google-places --max-google-requests N to run it.", flush=True)
    if not args.skip_wine_collection:
        run_step(
            "Recollect wine-list data from verified restaurants",
            [
                "scripts/guide_discover_wine_lists.py",
                "--max-targets",
                str(args.max_targets),
                "--refresh-websites",
                "--recheck-all",
                *(["--enable-google-places", "--max-google-requests", str(args.max_google_requests)] if args.enable_google_places else []),
            ],
        )


if __name__ == "__main__":
    main()
