"""Plain tables for reading the results (markdown, so they also look fine in a terminal)."""

from . import config, model


def table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def pct(x, digits=1):
    return "%.*f%%" % (digits, 100 * x)


def self_check_text(average, rows, problems):
    out = ["Average trait score of all cards: %.3f (the brief prints 13.7)" % average, ""]
    out.append(table(["Champion", "Code", "Brief", "Difference"],
                     [(r["name"], "%.2f" % r["comfort"], "%.1f" % r["brief_comfort"], "%+.3f" % r["comfort_diff"])
                      for r in sorted(rows, key=lambda r: -r["comfort"])]))
    biggest = max(abs(r["comfort_diff"]) for r in rows)
    out.append("")
    out.append("Biggest difference: %.3f. Differences above 0.1: %s" % (biggest, "none" if not problems else "; ".join(problems)))
    return "\n".join(out)


def results_text(res):
    out = []
    p = res["patch"]
    out.append("# Patch %s results (model %s)" % (p, res["model_version"]))
    out.append("Diamond+ average win rate: %.2f%% (last patch %.2f%%). Ranked bot-lane champions: %d "
               "(%d with a card, %d without). Trait average: %.2f (%s)." % (
                   res["diamond_plus_average_win_rate"], res["diamond_plus_average_win_rate_previous_patch"] or 0,
                   res["eligible_champions"], res["champions_with_card"], res["champions_without_card"],
                   res["trait_average"], res["trait_average_from"]))

    ts = res["tier_stats"]
    out.append("\n## Pick Score, full list")
    out.append("Average Pick Score %.2f, one spread = %.2f points (%d champions with a card)." % (
        ts["average_pick_score"], ts["spread"], ts["champions"]))
    out.append(table(
        ["#", "Champion", "Tier", "Pick Score", "Spreads", "Meta Score", "% this patch", "Stats", "Comfort", "OTP",
         "Win rate vs avg", "Pick rate", "Games"],
        [(c["pick_rank"], c["name"], c["tier"], "%.1f" % c["pick_score"],
          "%+.2f" % c["spreads"], "%.1f" % c["meta_score"], c["data_label"].replace("Data: ", "").replace(" this patch", ""),
          "%.1f" % c["stats"], "%.1f" % c["comfort"], "%.1f" % c["otp_points"],
          "%+.2f" % c["win_rate_delta"] + (" !" if c["win_rate_warning"] else ""), pct(c["pick_rate"]), c["real_games"])
         for c in res["pick_score_list"]]))
    out.append("(! = win rate 1.5% or more below the Diamond+ average; display only, no effect on the tier)")

    out.append("\n## Ban threat, top 5 (any role)")
    out.append(table(
        ["#", "Champion", "Role (share of its games)", "Ban threat", "Win rate vs avg", "Pick rate", "Bot-lane champion?"],
        [(i, b["name"], "%s (%s)" % (b["role"], pct(b["main_role_share"], 0)), "%.2f" % b["ban_threat"],
          "%+.2f" % b["win_rate_delta"], pct(b["pick_rate"]), "yes" if b["bot_lane_champion"] else "no")
         for i, b in enumerate(res["ban_threat_list"][:5], 1)]))

    out.append("\n## Growth advisor (champions with a card)")
    if res["growth_advisor"]:
        out.append(table(
            ["Champion", "Kind", "Now", "At target", "Would rank", "Tier"],
            [(a["name"], a["kind"], "%s: %.1f" % (a["current_mastery"], a["pick_score_now"]),
              "%.1f if %s" % (a["pick_score_at_target"], a["target_mastery"]), "#%d" % a["would_rank"],
              a["tier_at_target"]) for a in res["growth_advisor"]]))
    else:
        out.append("No suggestions: nothing would beat your current #3 pick.")

    out.append("\n## Needs a card (pass the filters, no card yet, by Meta Score)")
    if res["needs_a_card"]:
        out.append(table(
            ["Champion", "Meta Score", "Meta rank", "Win rate vs avg", "Pick rate", "Games", "Data"],
            [(c["name"], "%.1f" % c["meta_score"], c["meta_rank"], "%+.2f" % c["win_rate_delta"],
              pct(c["pick_rate"]), c["real_games"], c["data_label"].replace("Data: ", ""))
             for c in res["needs_a_card"]]))
    else:
        out.append("None.")
    if res["excluded_by_pool_rule"]:
        out.append("\nPassed the filters but kept out of your pool (set in scoring/config.py): " + ", ".join(
            "%s (%+.2f%% win rate, %s pick rate)" % (e["name"], e["win_rate_delta"], pct(e["pick_rate"]))
            for e in res["excluded_by_pool_rule"]))
    if res["cards_not_ranked"]:
        out.append("\nCards that did not pass the filters this patch: " + ", ".join("%s (%s)" % (c["name"], "; ".join(c["failed"])) for c in res["cards_not_ranked"]))
    return "\n".join(out)

