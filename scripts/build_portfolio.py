#!/usr/bin/env python3
"""Génère l'index des projets du README à partir des dépôts GitHub et de portfolio.json."""
import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com/graphql"
QUERY = """query($cursor: String) { viewer { repositories(first: 100, after: $cursor,
ownerAffiliations: OWNER) { pageInfo { hasNextPage endCursor } nodes { name url isPrivate
description repositoryTopics(first: 30) { nodes { topic { name } } }
latestRelease { tagName } } } } }"""


def warn(msg):
    print(f"avertissement : {msg}", file=sys.stderr)


def fetch_repos(token):
    repos, cursor = [], None
    while True:
        body = json.dumps({"query": QUERY, "variables": {"cursor": cursor}}).encode()
        req = urllib.request.Request(API, body, {
            "Authorization": f"bearer {token}", "Content-Type": "application/json",
            "User-Agent": "build-portfolio"})
        with urllib.request.urlopen(req) as resp:
            data = json.load(resp)
        if data.get("errors"):
            raise RuntimeError(f"erreur API GitHub : {data['errors']}")
        page = data["data"]["viewer"]["repositories"]
        for n in page["nodes"]:
            repos.append({
                "name": n["name"], "url": n["url"], "private": n["isPrivate"],
                "description": n["description"] or "",
                "topics": [t["topic"]["name"] for t in n["repositoryTopics"]["nodes"]],
                "release": (n["latestRelease"] or {}).get("tagName")})
        if not page["pageInfo"]["hasNextPage"]:
            return repos
        cursor = page["pageInfo"]["endCursor"]


def cell(text):
    return " ".join((text or "").split()).replace("|", "\\|")


def display_name(repo, meta, lang):
    m = meta.get(repo["name"], {})
    return (m.get("name_en") if lang == "en" else None) or m.get("name") or repo["name"]


def status_label(repo, cfg, lang):
    statuses = cfg["statuses"]
    key = next((k for k in statuses if k in repo["topics"]), None)
    if key is None and repo["release"]:
        key = cfg["release_default"]
    if key is None:
        warn(f"état inconnu pour {repo['name']}")
        return cfg["unknown"][lang]
    st = statuses[key]
    label = st[lang]
    if st.get("with_version") and repo["release"]:
        label += f" · {repo['release']}"
    return label


def description(repo, meta, lang):
    m = meta.get(repo["name"], {})
    if lang == "fr":
        text = repo["description"] or m.get("fr", "")
    else:
        text = m.get("en")
        if not text:
            warn(f"description anglaise absente pour {repo['name']}")
            text = repo["description"]
    if not text:
        warn(f"description vide pour {repo['name']}")
    return text


def select_repos(repos, cfg):
    meta = cfg.get("repos", {})
    rank = {n: i for i, n in enumerate(cfg["order"])}
    kept = [r for r in repos if cfg["topic"] in r["topics"]]
    return sorted(kept, key=lambda r: (rank.get(r["name"], len(rank)),
                                       "" if r["name"] in rank
                                       else display_name(r, meta, "fr").lower()))


def render_table(repos, cfg, lang):
    meta = cfg.get("repos", {})
    h = cfg["headers"][lang]
    rows = [f"| {' | '.join(h)} |", "|" + "|".join(" --- " for _ in h) + "|"]
    for r in repos:
        name = cell(display_name(r, meta, lang))
        name = f"🔒 {name}" if r["private"] else f"[{name}]({r['url']})"
        rows.append(f"| {name} | {cell(status_label(r, cfg, lang))} "
                    f"| {cell(description(r, meta, lang))} |")
    return "\n".join(rows)


def replace_block(readme, lang, table):
    start, end = f"<!-- portfolio:{lang}:start -->", f"<!-- portfolio:{lang}:end -->"
    pat = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if not pat.search(readme):
        raise ValueError(f"marqueurs portfolio:{lang} absents du README")
    return pat.sub(lambda _: f"{start}\n\n{table}\n\n{end}", readme, count=1)


def build(readme, repos, cfg):
    selected = select_repos(repos, cfg)
    for lang in ("fr", "en"):
        readme = replace_block(readme, lang, render_table(selected, cfg, lang))
    return readme


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", help="JSON de dépôts normalisés (remplace l'API)")
    ap.add_argument("--config", default=str(ROOT / "portfolio.json"))
    ap.add_argument("--readme", default=str(ROOT / "README.md"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    try:
        cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
        if args.input:
            repos = json.loads(Path(args.input).read_text(encoding="utf-8"))
        else:
            token = os.environ.get("PORTFOLIO_TOKEN") or os.environ.get("GITHUB_TOKEN")
            if not token:
                raise RuntimeError("jeton absent : définir PORTFOLIO_TOKEN (ou GITHUB_TOKEN)")
            repos = fetch_repos(token)
        path = Path(args.readme)
        old = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
        new = build(old, repos, cfg)
    except (RuntimeError, ValueError, OSError) as e:
        print(f"erreur : {e}", file=sys.stderr)
        return 1
    if args.dry_run:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        sys.stdout.write(new)
    elif new != old:
        path.write_bytes(new.encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
