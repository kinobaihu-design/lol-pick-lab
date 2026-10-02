"""The collector: one run of a few hours that gathers new Diamond+ games.

Threads:
- one per server, loading that server's Diamond+ player list (server allowance)
- one per routing region, looking up players and downloading games (region allowance)
"""

import argparse
import heapq
import os
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone

from . import config
from .riot import KeyRejected, NotFound, RequestFailed, RiotClient
from .store import DataDamaged, Store, compact_match, scramble, win_rate

APEX_TIERS = ("challengerleagues", "grandmasterleagues", "masterleagues")
DIAMOND_DIVISIONS = ("I", "II", "III", "IV")
BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "41898282+github-actions[bot]@users.noreply.github.com"


def log(message):
    print(time.strftime("%H:%M:%S ") + message, flush=True)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Stopped(Exception):
    pass


class Run:
    def __init__(self, args, client, store):
        self.args = args
        self.client = client
        self.store = store
        self.lock = threading.RLock()
        self.started = time.time()
        self.started_iso = now_iso()
        total = args.max_minutes * 60
        reserve = min(config.FINAL_SAVE_RESERVE_MINUTES * 60, total * 0.2)
        self.deadline = self.started + total - reserve
        self.stop = threading.Event()
        self.key_problem = None
        self.lists = {s: {"state": "loading", "codes": set(), "queue": []} for s in config.ALL_SERVERS}
        self.buffer = {s: [] for s in config.ALL_SERVERS}
        self.pending = {s: deque(store.pending.get(s, [])) for s in config.ALL_SERVERS}
        self.queued = {m for ids in self.pending.values() for m in ids}
        self.stats = defaultdict(Counter)
        self.region_done = {r: False for r in config.REGIONS}
        self.saved_once = False

    def over(self):
        return self.stop.is_set() or time.time() > self.deadline

    def key_rejected(self, error):
        with self.lock:
            if not self.key_problem:
                self.key_problem = str(error)
                log("STOPPING: %s. The Riot key may be expired or invalid." % error)
        self.stop.set()

    # ---- player lists (server allowance) ----

    def load_list(self, server):
        info = self.lists[server]
        order = 0
        try:
            for tier in APEX_TIERS:
                if self.over():
                    raise Stopped()
                data = self.client.get(server, "/lol/league/v4/%s/by-queue/%s" % (tier, config.QUEUE_NAME),
                                       "league-" + tier)
                order = self.add_players(server, data.get("entries", []), order)
            for division in DIAMOND_DIVISIONS:
                page = 1
                while True:
                    if self.over():
                        raise Stopped()
                    data = self.client.get(
                        server, "/lol/league/v4/entries/%s/DIAMOND/%s" % (config.QUEUE_NAME, division),
                        "league-entries", {"page": page})
                    if not data:
                        break
                    order = self.add_players(server, data, order)
                    page += 1
            with self.lock:
                info["state"] = "complete"
                for rec in self.buffer[server]:
                    self.process(rec)
                self.buffer[server] = []
            log("%s: Diamond+ list loaded (%d players)" % (config.SERVER_NAMES[server], len(info["codes"])))
        except Stopped:
            info["state"] = "incomplete"
        except KeyRejected as error:
            info["state"] = "incomplete"
            self.key_rejected(error)
        except (RequestFailed, NotFound) as error:
            info["state"] = "incomplete"
            log("%s: Diamond+ list stopped early (%s)" % (config.SERVER_NAMES[server], error))
        except Exception as error:
            info["state"] = "incomplete"
            log("%s: list loader crashed (%s)" % (config.SERVER_NAMES[server], type(error).__name__))

    def add_players(self, server, entries, order):
        with self.lock:
            info = self.lists[server]
            known = self.store.player_state[server]
            for entry in entries:
                puuid = entry.get("puuid")
                if not puuid:
                    self.stats[server]["missing_player_id"] += 1
                    continue
                code = scramble(puuid)
                if code in info["codes"]:
                    continue
                info["codes"].add(code)
                state = known.get(code)
                # Never-checked players are due from the start of this run; known
                # players are due when their waiting time is over. Active players
                # wait 5 hours, inactive ones wait longer and longer.
                due = state[0] + state[1] * 3600 if state else self.started
                heapq.heappush(info["queue"], (due, order, code, puuid))
                order += 1
        return order

    # ---- games (region allowance) ----

    def has_work(self, server, now):
        queue = self.lists[server]["queue"]
        return bool(self.pending[server]) or bool(queue and queue[0][0] <= now)

    def run_region(self, region):
        servers = config.REGIONS[region]
        shares = config.server_shares(region)
        used = {s: 0 for s in servers}
        downloads = 0
        limit = self.args.max_matches_per_region
        try:
            while not self.over():
                if limit and downloads >= limit:
                    log("%s: reached the test limit of %d games" % (region, limit))
                    break
                now = time.time()
                with self.lock:
                    choices = [s for s in servers if self.has_work(s, now)]
                    loading = any(self.lists[s]["state"] == "loading" for s in servers)
                if not choices:
                    if not loading:
                        log("%s: no more players due and no games waiting" % region)
                        break
                    time.sleep(1)
                    continue
                # The server furthest behind its target share goes next.
                server = min(choices, key=lambda s: used[s] / shares[s])
                used[server] += 1
                with self.lock:
                    match_id = self.pending[server].popleft() if self.pending[server] else None
                if match_id:
                    if self.download(region, server, match_id):
                        downloads += 1
                else:
                    self.lookup(region, server)
        except KeyRejected as error:
            self.key_rejected(error)
        except Exception as error:
            log("%s: worker crashed (%s)" % (region, type(error).__name__))
        self.region_done[region] = True

    def lookup(self, region, server):
        with self.lock:
            queue = self.lists[server]["queue"]
            if not queue or queue[0][0] > time.time():
                return
            _, _, code, puuid = heapq.heappop(queue)
            state = self.store.player_state[server].get(code)
        now = time.time()
        if state:
            start = max(state[0] - config.OVERLAP_HOURS * 3600, now - config.MAX_LOOKBACK_DAYS * 86400)
        else:
            start = now - config.NEW_PLAYER_LOOKBACK_DAYS * 86400
        try:
            ids = self.client.get(region, "/lol/match/v5/matches/by-puuid/%s/ids" % puuid, "match-ids", {
                "queue": config.QUEUE_ID, "type": "ranked", "startTime": int(start), "count": 100})
        except (RequestFailed, NotFound):
            self.stats[server]["lookup_failed"] += 1
            return
        with self.lock:
            self.stats[server]["players_checked"] += 1
            for match_id in ids:
                target = config.server_of_match(match_id)
                if target is None or match_id in self.queued or self.store.is_processed(match_id):
                    continue
                if len(self.pending[target]) >= config.MAX_PENDING_PER_SERVER:
                    continue
                self.pending[target].append(match_id)
                self.queued.add(match_id)
                self.stats[target]["games_found"] += 1
            if ids:
                wait = config.ACTIVE_RECHECK_HOURS
                self.stats[server]["players_active"] += 1
            elif state:
                wait = min(max(state[1], config.FIRST_INACTIVE_RECHECK_HOURS / 2) * 2, config.MAX_RECHECK_HOURS)
            else:
                wait = config.FIRST_INACTIVE_RECHECK_HOURS
            self.store.player_state[server][code] = [int(now), wait]

    def download(self, region, server, match_id):
        try:
            match = self.client.get(region, "/lol/match/v5/matches/%s" % match_id, "match")
            rec = compact_match(match, match_id, server)
        except NotFound:
            with self.lock:
                self.store.mark_processed(match_id, int(time.time() // 86400))
                self.queued.discard(match_id)
                self.stats[server]["not_found"] += 1
            return False
        except (RequestFailed, KeyError, TypeError):
            with self.lock:
                self.queued.discard(match_id)
                self.stats[server]["download_failed"] += 1
            return False
        with self.lock:
            self.stats[server]["downloaded"] += 1
            if self.lists[server]["state"] == "complete":
                self.process(rec)
            else:
                self.buffer[server].append(rec)  # counted once the player list is loaded
        return True

    def process(self, rec):
        """Add a downloaded game to the totals (caller holds the lock)."""
        server = rec["server"]
        outcome, counted = self.store.add_match(rec, self.lists[server]["codes"])
        self.stats[server][outcome] += 1
        for p in counted:
            self.stats[server]["role_" + p["pos"]] += 1
            state = self.store.player_state[server].get(p["h"])
            if state:
                state[1] = config.ACTIVE_RECHECK_HOURS  # just played: check again soon
        self.store.mark_processed(rec["id"], rec["day"])
        self.queued.discard(rec["id"])

    # ---- reporting and saving ----

    def run_info(self, final):
        servers = {}
        for s in config.ALL_SERVERS:
            st = self.stats[s]
            servers[config.SERVER_NAMES[s]] = {
                "diamond_plus_players": len(self.lists[s]["codes"]),
                "player_list": self.lists[s]["state"],
                "players_checked": st["players_checked"],
                "players_with_new_games": st["players_active"],
                "games_downloaded": st["downloaded"],
                "games_counted": st["counted"],
                "adc_players_counted": st["role_BOTTOM"],
                "support_players_counted": st["role_UTILITY"],
                "jungle_players_counted": st["role_JUNGLE"],
                "skipped_remake": st["remake"],
                "skipped_not_ranked": st["not_ranked"],
                "skipped_no_diamond_player": st["no_diamond"],
                "games_waiting": len(self.pending[s]),
                "failed_requests": st["lookup_failed"] + st["download_failed"],
            }
        routing = {name: dict(c) for name, c in sorted(self.client.stats.items())}
        return {
            "started": self.started_iso,
            "saved": now_iso(),
            "finished": final,
            "minutes": round((time.time() - self.started) / 60, 1),
            "settings": {
                "max_minutes": self.args.max_minutes,
                "max_matches_per_region": self.args.max_matches_per_region,
                "priority_share": config.PRIORITY_SHARE,
            },
            "key_problem": self.key_problem,
            "servers": servers,
            "requests_by_routing": routing,
            "patches": {
                name: {"games_counted": sum(p["games"]),
                       "diamond_plus_average_win_rate": win_rate(p["participants"])}
                for name, p in sorted(self.store.patches.items())},
            "seasons": {
                name: {"players": len(s["players"]), "bot_and_support_champions": len(s["champions"])}
                for name, s in sorted(self.store.seasons.items())},
        }

    def save(self, final):
        with self.lock:
            for s in config.ALL_SERVERS:
                waiting = list(self.pending[s])[:config.MAX_PENDING_PER_SERVER]
                waiting += [rec["id"] for rec in self.buffer[s]]
                self.store.pending[s] = waiting
                if self.lists[s]["state"] == "complete":
                    codes = self.lists[s]["codes"]
                    state = self.store.player_state[s]
                    for code in [c for c in state if c not in codes]:
                        del state[code]  # no longer Diamond+
            info = self.run_info(final)
            self.store.save(self.args.data_dir, info)
        log("Saved data (%s)" % ("final" if final else "checkpoint"))
        if self.args.push:
            self.push(final)
        return info

    def push(self, final):
        """Replace the `data` branch with one fresh commit. The first save of a run
        first copies the previous `data` commit to `data-backup`."""
        repo = os.path.abspath(self.args.repo_dir)
        env = dict(os.environ, GIT_DIR=os.path.join(repo, ".git"),
                   GIT_AUTHOR_NAME=BOT_NAME, GIT_AUTHOR_EMAIL=BOT_EMAIL,
                   GIT_COMMITTER_NAME=BOT_NAME, GIT_COMMITTER_EMAIL=BOT_EMAIL)
        try:
            if not self.saved_once and self.args.previous:
                git(["push", "--force", "origin", "%s:refs/heads/data-backup" % self.args.previous], env, repo)
            index = os.path.join(tempfile.gettempdir(), "lol-pick-lab-data-index")
            if os.path.exists(index):
                os.remove(index)
            tree_env = dict(env, GIT_WORK_TREE=os.path.abspath(self.args.data_dir), GIT_INDEX_FILE=index)
            git(["add", "-A"], tree_env, self.args.data_dir)
            tree = git(["write-tree"], tree_env, self.args.data_dir)
            message = "Data %s (%s)" % (now_iso(), "run finished" if final else "checkpoint")
            commit = git(["commit-tree", tree, "-m", message], env, repo)
            git(["push", "--force", "origin", "%s:refs/heads/data" % commit], env, repo)
            self.saved_once = True
            log("Uploaded data to GitHub")
        except subprocess.CalledProcessError as error:
            log("Upload to GitHub failed: %s" % (error.stderr or "").strip()[:300])
            if final:
                raise


def git(arguments, env, cwd):
    result = subprocess.run(["git"] + arguments, env=env, cwd=cwd, check=True,
                            capture_output=True, text=True)
    return result.stdout.strip()


def progress(run):
    with run.lock:
        parts = []
        for region, servers in config.REGIONS.items():
            downloaded = sum(run.stats[s]["downloaded"] for s in servers)
            waiting = sum(len(run.pending[s]) for s in servers)
            limited = run.client.stats[region]["rate_limited"]
            parts.append("%s %d games (%d waiting, %d slow-downs)" % (region, downloaded, waiting, limited))
    log("Progress: " + "; ".join(parts))


def write_step_summary(info):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = ["## Collector run", "",
             "Ran %.0f minutes. Key problem: %s" % (info["minutes"], info["key_problem"] or "none"), "",
             "| Server | Diamond+ players | Players checked | Games counted | ADC | Support |",
             "|---|---|---|---|---|---|"]
    for name, s in info["servers"].items():
        lines.append("| %s | %d | %d | %d | %d | %d |" % (
            name, s["diamond_plus_players"], s["players_checked"], s["games_counted"],
            s["adc_players_counted"], s["support_players_counted"]))
    lines += ["", "| Patch | Games counted | Diamond+ average win rate |", "|---|---|---|"]
    for name, p in info["patches"].items():
        lines.append("| %s | %d | %s%% |" % (name, p["games_counted"], p["diamond_plus_average_win_rate"]))
    lines += ["", "| Routing | Requests | Slow-downs (429) | Errors |", "|---|---|---|---|"]
    for name, c in info["requests_by_routing"].items():
        lines.append("| %s | %d | %d | %d |" % (name, c.get("requests", 0), c.get("rate_limited", 0),
                                               c.get("errors", 0)))
    with open(path, "a") as f:
        f.write("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Collect Diamond+ ranked games from the Riot API.")
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--backup-dir")
    parser.add_argument("--repo-dir", default=".")
    parser.add_argument("--previous", default="", help="commit of the current data branch")
    parser.add_argument("--max-minutes", type=float, default=config.DEFAULT_MAX_MINUTES)
    parser.add_argument("--max-matches-per-region", type=int, default=0, help="0 = no limit")
    parser.add_argument("--push", action="store_true", help="upload the data to the data branch")
    args = parser.parse_args()

    key = os.environ.get("RIOT_API_KEY", "").strip()
    if not key:
        log("RIOT_API_KEY is missing. Add it as a GitHub secret.")
        sys.exit(1)

    try:
        store = Store.load(args.data_dir)
    except DataDamaged as error:
        log("Saved data is damaged (%s). Using the backup copy." % error)
        args.previous = ""  # don't overwrite the good backup with damaged data
        try:
            store = Store.load(args.backup_dir) if args.backup_dir else Store()
        except DataDamaged as error:
            log("Backup is damaged too (%s). Starting fresh." % error)
            store = Store()

    run = Run(args, RiotClient(key), store)
    log("Starting: up to %.0f minutes, test limit per region: %s" % (
        args.max_minutes, args.max_matches_per_region or "none"))
    threads = [threading.Thread(target=run.load_list, args=(s,), daemon=True) for s in config.ALL_SERVERS]
    threads += [threading.Thread(target=run.run_region, args=(r,), daemon=True) for r in config.REGIONS]
    for t in threads:
        t.start()

    next_checkpoint = time.time() + config.CHECKPOINT_MINUTES * 60
    next_progress = time.time() + 300
    while any(t.is_alive() for t in threads):
        time.sleep(5)
        if time.time() >= next_progress:
            progress(run)
            next_progress += 300
        if time.time() >= next_checkpoint:
            run.save(final=False)
            next_checkpoint += config.CHECKPOINT_MINUTES * 60
        if all(run.region_done.values()) and not any(
                run.lists[s]["state"] == "loading" for s in config.ALL_SERVERS):
            break

    progress(run)
    info = run.save(final=True)
    write_step_summary(info)
    total = sum(s["games_counted"] for s in info["servers"].values())
    log("Done: %d new games counted." % total)
    if run.key_problem:
        sys.exit(1)
