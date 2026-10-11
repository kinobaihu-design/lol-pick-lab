"""Command line for the scoring model.

    python -m scoring --data-dir DATA            calculate and save DATA/scores/
    python -m scoring --data-dir DATA --report   also print the result tables
    python -m scoring --self-check               compare every card's Comfort with the brief
"""

import argparse
import json
import os
import sys

from . import comfort, model, report


def save(result, data_dir):
    folder = os.path.join(data_dir, "scores")
    os.makedirs(folder, exist_ok=True)
    text = json.dumps(model.round_floats(result), separators=(",", ":"), sort_keys=True)
    for name in ("%s.json" % result["patch"], "latest.json"):
        path = os.path.join(folder, name)
        with open(path + ".tmp", "w") as f:
            f.write(text)
        os.replace(path + ".tmp", path)
    return os.path.join(folder, "latest.json")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Calculate the Pick Score, Meta Score and more.")
    parser.add_argument("--data-dir", help="folder with the collector's saved data")
    parser.add_argument("--report", action="store_true", help="print the result tables")
    parser.add_argument("--self-check", action="store_true", help="compare Comfort with the brief")
    args = parser.parse_args(argv)

    if args.self_check:
        average, rows, problems = comfort.self_check(comfort.load_cards())
        print(report.self_check_text(average, rows, problems))
        return 1 if problems else 0

    if not args.data_dir:
        parser.error("--data-dir is required")
    result = model.score_all(args.data_dir)
    path = save(result, args.data_dir)
    print("Scores for patch %s saved to %s (%d ranked champions, %d with a card)" % (
        result["patch"], path, result["eligible_champions"], result["champions_with_card"]))
    if args.report:
        print(report.results_text(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
