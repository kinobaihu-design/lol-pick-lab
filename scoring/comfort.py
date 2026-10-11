"""Comfort from a champion card (the brief's "Comfort in detail").

Comfort = 40% type points + 60% mastery points + kit adjustment + difficulty adjustment
          + range adjustment (+ flexibility bonus, flexible builds only), capped at 100.
"""

import json
import os

from . import config

CARDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cards.json")


def load_cards(path=CARDS_FILE):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["cards"]


def type_points(card):
    """Main type points, plus 20% of the gap when a secondary type is worth more.
    Returns (main points, secondary bonus, type points)."""
    main = config.TYPE_POINTS[card["main_type"]] * config.STRENGTH[card["main_strength"]]
    # With two secondary types (Vayne) the best one counts.
    best = max((config.TYPE_POINTS[s["type"]] * config.STRENGTH[s["strength"]]
                for s in card.get("secondary_types", [])), default=0)
    bonus = config.SECONDARY_SHARE * (best - main) if best > main else 0.0
    return main, bonus, main + bonus


def trait_score(card):
    """Sum of priority x level over the traits the champion has."""
    return sum(config.TRAIT_PRIORITY[t] * config.TRAIT_LEVEL[level]
               for t, level in card["traits"].items())


def difficulty(card):
    """80% the owner's base rating + 20% Riot's."""
    d = card["difficulty"]
    return config.DIFFICULTY_MINE_SHARE * d["mine"] + config.DIFFICULTY_RIOT_SHARE * d["riot"]


def comfort(card, trait_average, mastery=None):
    """Full Comfort breakdown. `mastery` overrides the card's mastery (used by the
    Growth advisor to ask "what if I were Good?")."""
    mastery = mastery or card["mastery"]
    main, bonus, type_pts = type_points(card)
    mastery_pts = config.MASTERY_POINTS[mastery]
    base = config.COMFORT_TYPE_SHARE * type_pts + config.COMFORT_MASTERY_SHARE * mastery_pts

    score = trait_score(card)
    kit_raw = config.KIT_WEIGHT * (score - trait_average)
    kit_adj = max(-config.KIT_CAP, min(config.KIT_CAP, kit_raw))

    diff = difficulty(card)
    diff_raw = -config.DIFFICULTY_WEIGHT * (diff - config.DIFFICULTY_MIDDLE) * config.MASTERY_DIFFICULTY_FACTOR[mastery]
    diff_adj = max(-config.DIFFICULTY_CAP, min(config.DIFFICULTY_CAP, diff_raw))

    range_adj = config.RANGE_ADJUSTMENT[card["range"]]
    flex = config.FLEXIBILITY_BONUS * config.MASTERY_FLEXIBILITY_FACTOR[mastery] if card.get("flexible_build") else 0.0

    total = min(config.COMFORT_CAP, base + kit_adj + diff_adj + range_adj + flex)
    return {
        "mastery": mastery,
        "main_points": main,
        "secondary_bonus": bonus,
        "type_points": type_pts,
        "mastery_points": mastery_pts,
        "base": base,
        "trait_score": score,
        "kit_adjustment": kit_adj,
        "difficulty": diff,
        "difficulty_adjustment": diff_adj,
        "range_adjustment": range_adj,
        "flexibility_bonus": flex,
        "comfort": total,
    }


def average_trait_score(cards):
    return sum(trait_score(c) for c in cards) / len(cards)


def self_check(cards, tolerance=0.1):
    """Recalculate every card and compare with the numbers printed in the brief.
    Returns (rows, problems). Nothing is adjusted to make the numbers match."""
    average = average_trait_score(cards)   # all cards, as in the brief (13.656, printed 13.7)
    rows, problems = [], []
    for card in cards:
        result = comfort(card, average)
        brief = card.get("brief", {})
        row = {
            "name": card["name"],
            "comfort": result["comfort"],
            "brief_comfort": brief.get("comfort"),
            "comfort_diff": None,
            "trait_score": result["trait_score"],
            "brief_trait_score": brief.get("trait_score"),
        }
        if row["brief_comfort"] is not None:
            row["comfort_diff"] = result["comfort"] - row["brief_comfort"]
            if abs(row["comfort_diff"]) > tolerance:
                problems.append("%s: Comfort %.2f, brief %.1f" % (card["name"], result["comfort"], row["brief_comfort"]))
        if row["brief_trait_score"] is not None and abs(result["trait_score"] - row["brief_trait_score"]) > 1e-9:
            problems.append("%s: trait score %.2f, brief %.2f" % (card["name"], result["trait_score"], row["brief_trait_score"]))
        rows.append(row)
    return average, rows, problems
