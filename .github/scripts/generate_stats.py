#!/usr/bin/env python3
"""Generate GitHub profile stats cards as SVG files.

Queries the GitHub REST API v3 (works with the workflow's GITHUB_TOKEN,
which only needs read access to public data) and renders two cards,
each in a light and a dark variant:

  dist/github-stats.svg / github-stats-dark.svg
  dist/github-top-langs.svg / github-top-langs-dark.svg

Usage: python3 generate_stats.py [--dry]
  --dry renders sample data without any network access (for local preview).
"""
import datetime
import json
import os
import re
import sys
import time
import urllib.request

API = "https://api.github.com"
LOGIN = os.environ.get("GITHUB_USER", "hexne")
OUT_DIR = os.environ.get("OUT_DIR", "dist")
DRY = "--dry" in sys.argv

FONT = "Segoe UI, Ubuntu, Sans-Serif"
THEMES = {
    "light": {
        "bg": "#fefefe", "stroke": "#e4e2e2", "title": "#2f80ed",
        "label": "#333333", "value": "#333333", "icon": "#2f80ed",
    },
    "dark": {
        "bg": "#0d1117", "stroke": "#30363d", "title": "#ffffff",
        "label": "#8b949e", "value": "#ffffff", "icon": "#79c0ff",
    },
}

# fallback palette for languages without a known official color
PALETTE = ["#56d364", "#79c0ff", "#a371f7", "#ffa657", "#39c5cf", "#f778ba"]

LANG_COLORS = {
    "Python": "#3572A5", "JavaScript": "#f1e05a", "TypeScript": "#3178c6",
    "Go": "#00ADD8", "C": "#555555", "C++": "#f34b7d", "C#": "#178600",
    "Java": "#b07219", "Rust": "#dea584", "Shell": "#89e051",
    "HTML": "#e34c26", "CSS": "#563d7c", "Vue": "#41b883",
    "PHP": "#4F5D95", "Ruby": "#701516", "Kotlin": "#A97BFF",
    "Swift": "#F05138", "Dart": "#00B4AB", "Lua": "#000080",
    "PowerShell": "#012456", "Dockerfile": "#384d54", "Makefile": "#427819",
    "Jupyter Notebook": "#DA5B0B", "Assembly": "#6E4C13",
    "Batchfile": "#C1F12E", "R": "#198CE7", "MATLAB": "#e16737",
    "Nix": "#7e7eff", "Zig": "#ec915c", "Scala": "#c22d40",
    "Vim Script": "#199f4b", "Vim script": "#199f4b",
}

# feather-style 24x24 stroke icons (https://feathericons.com, MIT)
ICONS = {
    "star": ['<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 '
             '18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>'],
    "commit": ['<circle cx="12" cy="12" r="4"/>',
               '<line x1="1.05" y1="12" x2="7" y2="12"/>',
               '<line x1="17.01" y1="12" x2="22.96" y2="12"/>'],
    "pr": ['<circle cx="18" cy="18" r="3"/>',
           '<circle cx="6" cy="6" r="3"/>',
           '<path d="M13 6h3a2 2 0 0 1 2 2v7"/>',
           '<line x1="6" y1="9" x2="6" y2="21"/>'],
    "issue": ['<circle cx="12" cy="12" r="10"/>',
              '<circle cx="12" cy="12" r="3" fill="currentColor" '
              'stroke="none"/>'],
    "users": ['<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>',
              '<circle cx="9" cy="7" r="4"/>',
              '<path d="M23 21v-2a4 4 0 0 0-3-3.87"/>',
              '<path d="M16 3.13a4 4 0 0 1 0 7.75"/>'],
}


def esc(text):
    return (str(text).replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def fmt(n):
    return f"{n:,}"


def icon(name, color, size=16):
    body = "".join(ICONS[name]).replace("currentColor", color)
    s = size / 24
    return (f'<g transform="scale({s:.4f})" fill="none" stroke="{color}" '
            f'stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round">{body}</g>')


def api(path):
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {"User-Agent": "profile-stats-action"}
    if token:
        headers["Authorization"] = f"bearer {token}"
    url = path if path.startswith("http") else API + path
    for attempt in range(3):
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(url, headers=headers),
                    timeout=30) as resp:
                return json.load(resp), resp.headers
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and attempt < 2:
                wait = int(e.headers.get("X-RateLimit-Reset",
                                         time.time() + 5))
                time.sleep(max(2, min(wait - time.time(), 30)))
                continue
            sys.exit(f"error: GET {url} -> HTTP {e.code}: {e.read()[:200]}")
        except urllib.error.URLError as e:
            if attempt < 2:
                time.sleep(3)
                continue
            sys.exit(f"error: GET {url} failed: {e}")
    sys.exit(f"error: GET {url} failed after retries")


def paginate(path):
    url, items = API + path, []
    while url:
        page, headers = api(url)
        items.extend(page)
        m = re.search(r'<([^>]+)>; rel="next"', headers.get("Link", ""))
        url = m.group(1) if m else None
    return items


def commit_count(repo_full_name, since):
    """Commit count since `since` via the Link header of a 1-item page."""
    url = (f"{API}/repos/{repo_full_name}/commits"
           f"?per_page=1&since={since}")
    _, headers = api(url)
    m = re.search(r'page=(\d+)>; rel="last"', headers.get("Link", ""))
    if m:
        return int(m.group(1))
    items, _ = api(url)
    return len(items)


def fetch_stats():
    user, _ = api(f"/users/{LOGIN}")

    since = (datetime.datetime.now(
        datetime.timezone.utc) - datetime.timedelta(days=365)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    repos = paginate(f"/users/{LOGIN}/repos?per_page=100")

    stars, langs = 0, {}
    for i, repo in enumerate(repos):
        stars += repo["stargazers_count"]
        by_lang, _ = api(repo["languages_url"])
        for name, size in by_lang.items():
            color = LANG_COLORS.get(name, PALETTE[i % len(PALETTE)])
            entry = langs.setdefault(name, [0, color])
            entry[0] += size

    commits = sum(commit_count(r["full_name"], since) for r in repos)
    prs, _ = api(f"/search/issues?q=author:{LOGIN}+type:pr&per_page=1")
    issues, _ = api(f"/search/issues?q=author:{LOGIN}+type:issue&per_page=1")

    return {
        "login": user["login"],
        "name": user["name"] or user["login"],
        "followers": user["followers"],
        "stars": stars,
        "commits": commits,
        "prs": prs["total_count"],
        "issues": issues["total_count"],
        "langs": sorted(langs.items(), key=lambda kv: -kv[1][0]),
    }


def dry_stats():
    return {
        "login": LOGIN,
        "name": "永恒之蓝。",
        "followers": 3, "stars": 128, "commits": 486,
        "prs": 23, "issues": 11,
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
        ("star", "Total Stars", data["stars"]),
        ("commit", "Total Commits (1y)", data["commits"]),
        ("pr", "Total PRs", data["prs"]),
        ("issue", "Total Issues", data["issues"]),
        ("users", "Followers", data["followers"]),
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
    for name, label, value in rows:
        parts.append(
            f'<g transform="translate(30, {y - 13})">'
            f'{icon(name, t["icon"])}</g>')
        parts.append(
            f'<text x="52" y="{y}" font-family="{FONT}" font-size="14" '
            f'fill="{t["label"]}">{esc(label)}</text>')
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
               if size / total >= 0.005][:8]
    w, bar_x, bar_w, bar_h = 440, 30, 380, 10
    legend_top, item_h = 92, 28
    cols = 2
    n_rows = (len(entries) + cols - 1) // cols
    h = legend_top + n_rows * item_h + 10
    parts = [svg_open(w, h, "Most Used Languages")]
    parts.append(
        f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="6" '
        f'fill="{t["bg"]}" stroke="{t["stroke"]}"/>')
    parts.append(
        f'<text x="30" y="42" font-family="{FONT}" font-size="16" '
        f'font-weight="700" fill="{t["title"]}">Most Used Languages</text>')
    # stacked horizontal bar, rounded ends via clip
    parts.append(
        f'<clipPath id="bar-clip"><rect x="{bar_x}" y="60" '
        f'width="{bar_w}" height="{bar_h}" rx="5"/></clipPath>')
    parts.append(f'<g clip-path="url(#bar-clip)">')
    x = bar_x
    for i, (name, pct, color) in enumerate(entries):
        seg_w = bar_w * pct / 100
        if i == len(entries) - 1:  # absorb rounding into the last segment
            seg_w = bar_x + bar_w - x
        parts.append(
            f'<rect x="{x:.2f}" y="60" width="{seg_w:.2f}" '
            f'height="{bar_h}" fill="{color}"/>')
        x += seg_w
    parts.append("</g>")
    # two-column legend: "69.40% Python"
    for i, (name, pct, color) in enumerate(entries):
        col, row = i % cols, i // cols
        lx = bar_x + col * (bar_w / cols)
        ly = legend_top + row * item_h
        parts.append(f'<circle cx="{lx + 6}" cy="{ly - 5}" r="6" '
                     f'fill="{color}"/>')
        parts.append(
            f'<text x="{lx + 20}" y="{ly}" font-family="{FONT}" '
            f'font-size="14" font-weight="700" fill="{t["value"]}">'
            f'{pct:.2f}%</text>')
        parts.append(
            f'<text x="{lx + 82}" y="{ly}" font-family="{FONT}" '
            f'font-size="14" fill="{t["label"]}">{esc(name)}</text>')
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
