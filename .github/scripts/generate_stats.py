#!/usr/bin/env python3
"""Generate GitHub profile stats cards as SVG files.

Queries the GitHub GraphQL API (works with the workflow's GITHUB_TOKEN,
which only needs read access to public data) and renders two cards,
each in a light and a dark variant:

  dist/github-stats.svg / github-stats-dark.svg
  dist/github-top-langs.svg / github-top-langs-dark.svg

Usage: python3 generate_stats.py [--dry]
  --dry renders sample data without any network access (for local preview).
"""
import json
import os
import sys
import urllib.request

LOGIN = os.environ.get("GITHUB_USER", "hexne")
OUT_DIR = os.environ.get("OUT_DIR", "dist")
DRY = "--dry" in sys.argv

QUERY = """
query($login: String!) {
  user(login: $login) {
    login
    name
    followers { totalCount }
    repositories(ownerAffiliations: [OWNER], first: 100, isFork: false) {
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    repositoriesContributedTo(first: 1, contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, REPOSITORY]) {
      totalCount
    }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
    }
  }
}
"""

FONT = "Segoe UI, Ubuntu, Sans-Serif"
THEMES = {
    "light": {
        "bg": "#fefefe", "stroke": "#e4e2e2", "title": "#2f80ed",
        "label": "#333333", "value": "#333333",
    },
    "dark": {
        "bg": "#0d1117", "stroke": "#30363d", "title": "#ffffff",
        "label": "#8b949e", "value": "#ffffff",
    },
}


def esc(text):
    return (str(text).replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def fmt(n):
    return f"{n:,}"


def fetch_stats():
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        sys.exit("error: GITHUB_TOKEN is not set (or use --dry)")
    body = json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode()
    req = urllib.request.Request(
        GRAPHQL_URL, data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-stats-action",
        })
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if payload.get("errors"):
        sys.exit(f"error: GraphQL query failed: {payload['errors']}")
    u = payload["data"]["user"]
    stars = sum(r["stargazerCount"] for r in u["repositories"]["nodes"])
    langs = {}
    for repo in u["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            size, color = edge["size"], edge["node"]["color"]
            entry = langs.setdefault(name, [0, color or "#8b949e"])
            entry[0] += size
    cc = u["contributionsCollection"]
    return {
        "login": u["login"],
        "name": u["name"] or u["login"],
        "followers": u["followers"]["totalCount"],
        "stars": stars,
        "commits": cc["totalCommitContributions"],
        "prs": cc["totalPullRequestContributions"],
        "issues": cc["totalIssueContributions"],
        "contributed": u["repositoriesContributedTo"]["totalCount"],
        "langs": sorted(langs.items(), key=lambda kv: -kv[1][0]),
    }


def dry_stats():
    return {
        "login": LOGIN,
        "name": "永恒之蓝。",
        "followers": 3, "stars": 128, "commits": 486,
        "prs": 23, "issues": 11, "contributed": 6,
        "langs": [("Python", [45000, "#3572A5"]),
                  ("JavaScript", [25000, "#f1e05a"]),
                  ("Go", [12000, "#00ADD8"]),
                  ("C", [8000, "#555555"]),
                  ("Shell", [6000, "#89e051"]),
                  ("HTML", [4000, "#e34c26"])],
    }


def svg_open(w, h, t):
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'xmlns="http://www.w3.org/2000/svg" role="img">'
            f'<title>{esc(t)}</title>')


def stats_svg(data, theme):
    t = THEMES[theme]
    rows = [
        ("⭐", "Total Stars", data["stars"]),
        ("📕", "Total Commits (1y)", data["commits"]),
        ("🔀", "Total PRs", data["prs"]),
        ("📦", "Total Issues", data["issues"]),
        ("📊", "Contributed to", data["contributed"]),
        ("👥", "Followers", data["followers"]),
    ]
    w, row_h, top = 500, 30, 78
    h = top + len(rows) * row_h + 12
    title = f"{data['login']}'s GitHub Stats"
    parts = [svg_open(w, h, title)]
    parts.append(
        f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="6" '
        f'fill="{t["bg"]}" stroke="{t["stroke"]}"/>')
    parts.append(
        f'<text x="30" y="45" font-family="{FONT}" font-size="17" '
        f'font-weight="700" fill="{t["title"]}">{esc(title)}</text>')
    y = top + 10
    for icon, label, value in rows:
        parts.append(
            f'<text x="30" y="{y}" font-family="{FONT}" font-size="14" '
            f'fill="{t["label"]}">{icon} {esc(label)}</text>')
        parts.append(
            f'<text x="{w - 30}" y="{y}" text-anchor="end" '
            f'font-family="{FONT}" font-size="14" font-weight="700" '
            f'fill="{t["value"]}">{fmt(value)}</text>')
        y += row_h
    parts.append("</svg>")
    return "".join(parts)


def langs_svg(data, theme):
    t = THEMES[theme]
    total = sum(size for _, (size, _) in data["langs"])
    entries = [(name, size / total * 100, color)
               for name, (size, color) in data["langs"]
               if size / total >= 0.01][:6]
    w, row_h, top = 400, 30, 70
    h = top + len(entries) * row_h + 8
    parts = [svg_open(w, h, "Most Used Languages")]
    parts.append(
        f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="6" '
        f'fill="{t["bg"]}" stroke="{t["stroke"]}"/>')
    parts.append(
        f'<text x="30" y="42" font-family="{FONT}" font-size="16" '
        f'font-weight="700" fill="{t["title"]}">Most Used Languages</text>')
    y = top + 10
    for name, pct, color in entries:
        parts.append(f'<circle cx="34" cy="{y - 5}" r="6" fill="{color}"/>')
        parts.append(
            f'<text x="48" y="{y}" font-family="{FONT}" font-size="14" '
            f'fill="{t["label"]}">{esc(name)}</text>')
        parts.append(
            f'<text x="{w - 30}" y="{y}" text-anchor="end" '
            f'font-family="{FONT}" font-size="14" fill="{t["value"]}">'
            f'{pct:.2f}%</text>')
        y += row_h
    parts.append("</svg>")
    return "".join(parts)


def main():
    data = dry_stats() if DRY else fetch_stats()
    os.makedirs(OUT_DIR, exist_ok=True)
    cards = {
        "github-stats": stats_svg(data, "light"),
        "github-stats-dark": stats_svg(data, "dark"),
        "github-top-langs": langs_svg(data, "light"),
        "github-top-langs-dark": langs_svg(data, "dark"),
    }
    for name, svg in cards.items():
        path = os.path.join(OUT_DIR, f"{name}.svg")
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"wrote {path} ({len(svg)} bytes)")


if __name__ == "__main__":
    main()
