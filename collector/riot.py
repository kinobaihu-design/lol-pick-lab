"""Talks to the Riot API while staying under the rate limits.

The API key is only ever sent in a request header. It is never logged, and
URLs (which contain player IDs) are never logged either.
"""

import gzip
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict, deque

from . import config


class KeyRejected(Exception):
    """Riot refused the key (expired, wrong, or not allowed)."""


class NotFound(Exception):
    """The thing asked for doesn't exist (for example a deleted game)."""


class RequestFailed(Exception):
    """Riot kept failing after several slow retries."""


def parse_limits(header):
    """'20:1,100:120' -> [(19, 1), (97, 120)] (with the safety margin)."""
    limits = []
    for part in header.split(","):
        count, seconds = part.strip().split(":")
        limits.append((max(1, int(int(count) * config.RATE_LIMIT_SAFETY)), int(seconds)))
    return limits


class Limiter:
    """Sliding-window limiter: never more than `count` requests in any `seconds`."""

    def __init__(self, limits):
        self.lock = threading.Lock()
        self.limits = list(limits)
        self.stamps = deque()
        self.blocked_until = 0.0

    def block(self, seconds):
        with self.lock:
            self.blocked_until = max(self.blocked_until, time.monotonic() + seconds)

    def wait_turn(self):
        while True:
            with self.lock:
                now = time.monotonic()
                wait = self.blocked_until - now
                if wait <= 0:
                    longest = max((s for _, s in self.limits), default=0)
                    while self.stamps and self.stamps[0] <= now - longest:
                        self.stamps.popleft()
                    for count, seconds in self.limits:
                        recent = [t for t in self.stamps if t > now - seconds]
                        if len(recent) >= count:
                            wait = max(wait, recent[-count] + seconds - now)
                    if wait <= 0:
                        self.stamps.append(now)
                        return
            time.sleep(wait + 0.02)


class RiotClient:
    def __init__(self, key):
        self._key = key
        self._lock = threading.Lock()
        self._app = {}
        self._method = {}
        self._app_header = {}
        self._method_header = {}
        self.stats = defaultdict(Counter)

    def _app_limiter(self, routing):
        with self._lock:
            if routing not in self._app:
                self._app[routing] = Limiter(config.APP_RATE_LIMITS)
            return self._app[routing]

    def _method_limiter(self, routing, method):
        with self._lock:
            key = (routing, method)
            if key not in self._method:
                self._method[key] = Limiter([])  # learned from the first response
            return self._method[key]

    def _learn_limits(self, routing, method, headers):
        if headers is None:
            return
        app = headers.get("X-App-Rate-Limit")
        if app and self._app_header.get(routing) != app:
            self._app_header[routing] = app
            self._app_limiter(routing).limits = parse_limits(app)
        meth = headers.get("X-Method-Rate-Limit")
        if meth and self._method_header.get((routing, method)) != meth:
            self._method_header[(routing, method)] = meth
            self._method_limiter(routing, method).limits = parse_limits(meth)

    def get(self, routing, path, method, params=None):
        url = "https://%s.api.riotgames.com%s" % (routing.lower(), path)
        if params:
            url += "?" + urllib.parse.urlencode(params)
        app = self._app_limiter(routing)
        meth = self._method_limiter(routing, method)
        stats = self.stats[routing]
        failures = 0
        rate_limited = 0
        while True:
            app.wait_turn()
            meth.wait_turn()
            request = urllib.request.Request(url, headers={
                "X-Riot-Token": self._key,
                "Accept-Encoding": "gzip",
                "User-Agent": "lol-pick-lab-collector",
            })
            stats["requests"] += 1
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    self._learn_limits(routing, method, response.headers)
                    body = response.read()
                    if response.headers.get("Content-Encoding") == "gzip":
                        body = gzip.decompress(body)
                    return json.loads(body)
            except urllib.error.HTTPError as error:
                self._learn_limits(routing, method, error.headers)
                code = error.code
                if code == 429:
                    # Too many requests: wait as long as Riot asks, never retry fast.
                    stats["rate_limited"] += 1
                    rate_limited += 1
                    retry_after = error.headers.get("Retry-After") if error.headers else None
                    wait = float(retry_after) + 1 if retry_after else 15.0
                    limit_type = (error.headers.get("X-Rate-Limit-Type") or "") if error.headers else ""
                    (meth if limit_type == "method" else app).block(wait)
                    if rate_limited >= 10:
                        stats["errors"] += 1
                        raise RequestFailed("still rate limited after 10 waits")
                    continue
                if code in (401, 403):
                    raise KeyRejected("Riot answered %d" % code)
                if code in (400, 404):
                    raise NotFound("Riot answered %d" % code)
                problem = "Riot answered %d" % code
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError) as error:
                problem = type(error).__name__
            failures += 1
            stats["errors"] += 1
            if failures >= 4:
                raise RequestFailed(problem)
            time.sleep(5 * 2 ** failures)
