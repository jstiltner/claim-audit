"""URL checking. Opt-in, off by default, and deliberately not Tier A.

Amendment A1 split this off from `ref-resolves`. The reason is that a URL check does not
establish the fact people assume it does. An unauthenticated fetch of a private repository
returns 404, which is indistinguishable from deleted. Rate limits return 429, which is
indistinguishable from nothing at all. The only honest thing to report is the status the
fetcher saw, labelled as such.

So: findings from here are never counted as Tier A, the status code is always shown, and a
404 is phrased as a question about visibility rather than existence.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from claim_audit.docs import (
    DEFAULT_DOC_EXCLUDE,
    DEFAULT_DOCS,
    collect_docs,
    read_lines,
)
from claim_audit.finding import TIER_ONLINE, CheckResult, Finding

RULE = "link-resolves"

_URL = re.compile(r"https?://[^\s)\]<>\"'`]+")
_TRAILING = ".,;:!?"

USER_AGENT = "claim-audit (+https://github.com/jstiltner/claim-audit)"
TIMEOUT = 10


def _status(url: str) -> int | str:
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 405, 501):
            # Plenty of hosts refuse HEAD. Retry properly before reporting anything.
            try:
                get = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(get, timeout=TIMEOUT) as response:
                    return response.status
            except urllib.error.HTTPError as inner:
                return inner.code
            except Exception as inner:  # noqa: BLE001 - reported verbatim, not handled
                return type(inner).__name__
        return exc.code
    except Exception as exc:  # noqa: BLE001 - reported verbatim, not handled
        return type(exc).__name__


def run(
    repo: Path,
    docs: list[str] | None = None,
    exclude: list[str] | None = None,
    workers: int = 8,
) -> CheckResult:
    repo = repo.resolve()
    paths = collect_docs(repo, list(docs or DEFAULT_DOCS), list(exclude or DEFAULT_DOC_EXCLUDE))
    result = CheckResult(rule=RULE, examined=len(paths), tier=TIER_ONLINE)

    sites: dict[str, tuple[str, int]] = {}
    for doc in paths:
        rel = doc.relative_to(repo).as_posix()
        for line in read_lines(doc):
            if line.in_fence:
                continue
            for match in _URL.finditer(line.text):
                url = match.group(0).rstrip(_TRAILING)
                sites.setdefault(url, (rel, line.number))

    if not sites:
        result.note = "no URLs found"
        return result

    urls = list(sites)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        statuses = list(pool.map(_status, urls))

    for url, status in zip(urls, statuses):
        if isinstance(status, int) and 200 <= status < 400:
            continue
        rel, lineno = sites[url]
        if status == 404:
            question = "Is this resource deleted, or private and therefore invisible to an unauthenticated fetch?"
        elif status == 429:
            question = "Rate limited — this says nothing about the link. Re-run to determine its status."
        else:
            question = "Does this link still point where the surrounding text says it does?"
        result.findings.append(
            Finding(
                rule=RULE,
                path=rel,
                line=lineno,
                evidence=(f"{url}", f"Unauthenticated fetch returned: {status}"),
                question=question,
                tier=TIER_ONLINE,
            )
        )
    return result
