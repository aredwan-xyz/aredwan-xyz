#!/usr/bin/env python3
"""Self-updating sections for the GitHub profile README.

Pulls live data from the GitHub REST API (no extra secrets — the built-in
GITHUB_TOKEN is enough) and rewrites the marker-delimited sections of
README.md in place. Each section updates independently and leaves the
existing content untouched if its fetch fails, so a transient API hiccup
can never blank out the profile.

WakaTime is optional: set the WAKATIME_API_KEY secret to enable it. Until
then, that section keeps its placeholder.
"""

import base64
import json
import os
import urllib.request
from datetime import datetime, timezone

USER = "aredwan-xyz"
PROFILE_REPO = "aredwan-xyz"   # the special profile repo — excluded from "builds"
README = "README.md"
API = "https://api.github.com"
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

LANG_EMOJI = {
    "Python": "🐍", "TypeScript": "🟦", "JavaScript": "🟨", "HTML": "🌐",
    "CSS": "🎨", "C++": "⚙️", "C": "⚙️", "Go": "🐹", "Rust": "🦀",
    "Shell": "🐚", "Jupyter Notebook": "📓", "Java": "☕", "Ruby": "💎",
    "Swift": "🕊️", "Kotlin": "🟪", "Dart": "🎯", "Vue": "💚", "Dockerfile": "🐳",
}


def gh(path):
    """GET a GitHub API path (or full URL) and return parsed JSON."""
    url = path if path.startswith("http") else API + path
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USER}-profile-bot",
    })
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def ago(iso):
    """Human relative time from an ISO-8601 UTC timestamp."""
    then = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    secs = (datetime.now(timezone.utc) - then).total_seconds()
    for unit, n in (("y", 31536000), ("mo", 2592000), ("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= n:
            return f"{int(secs // n)}{unit} ago"
    return "just now"


def trunc(s, n=95):
    s = (s or "").strip().replace("\r", " ").replace("\n", " ")
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def splice(text, key, content):
    """Replace everything between <!-- KEY:START --> and <!-- KEY:END -->."""
    start, end = f"<!-- {key}:START -->", f"<!-- {key}:END -->"
    i, j = text.find(start), text.find(end)
    if i == -1 or j == -1:
        print(f"  ! markers for {key} not found — skipped")
        return text
    return text[: i + len(start)] + "\n\n" + content + "\n\n" + text[j:]


def section_builds():
    """Most recently pushed owned repos (returns lines + the repo list)."""
    repos = gh(f"/users/{USER}/repos?per_page=100&sort=pushed&type=owner")
    repos = [r for r in repos if not r["fork"] and not r["archived"]
             and r["name"] != PROFILE_REPO]
    lines = []
    for r in repos[:6]:
        emoji = LANG_EMOJI.get(r.get("language") or "", "📦")
        desc = trunc(r.get("description"))
        desc_part = f" — {desc}" if desc else ""
        stars = r["stargazers_count"]
        star_txt = f" &nbsp;·&nbsp; ⭐ {stars}" if stars else ""
        lines.append(
            f"{emoji} **[{r['name']}]({r['html_url']})**{desc_part}{star_txt} &nbsp;·&nbsp; _{ago(r['pushed_at'])}_"
        )
    return "<br>".join(lines), repos


def section_techpulse():
    commits = gh(f"/repos/{USER}/techpulse-daily/commits?per_page=6")
    lines = []
    for c in commits:
        msg = trunc(c["commit"]["message"].splitlines()[0], 78)
        if msg:
            lines.append(f"- {msg}")
        if len(lines) >= 4:
            break
    body = "\n".join(lines) if lines else "_Feed warming up…_"
    return (body + "\n\n> 🔄 Pulled live from "
            f"[`techpulse-daily`](https://github.com/{USER}/techpulse-daily) — "
            "my AI intelligence feed, regenerated every day.")


def section_activity():
    events = gh(f"/users/{USER}/events/public?per_page=100")
    lines = []
    i = 0
    while i < len(events) and len(lines) < 5:
        e = events[i]
        et = e["type"]
        full = e["repo"]["name"]
        name = full.split("/")[-1]
        url = f"https://github.com/{full}"
        when = ago(e["created_at"])
        if et == "PushEvent":
            n = e["payload"].get("size", 1)
            j = i + 1
            while (j < len(events) and events[j]["type"] == "PushEvent"
                   and events[j]["repo"]["name"] == full):
                n += events[j]["payload"].get("size", 1)
                j += 1
            plural = "s" if n != 1 else ""
            lines.append(f"- 📦 Pushed `{n}` commit{plural} to **[{name}]({url})** &nbsp;·&nbsp; _{when}_")
            i = j
            continue
        elif et == "PullRequestEvent":
            act = e["payload"].get("action", "updated")
            lines.append(f"- 🔀 {act.capitalize()} a pull request in **[{name}]({url})** &nbsp;·&nbsp; _{when}_")
        elif et == "CreateEvent":
            rt = e["payload"].get("ref_type", "")
            if rt == "repository":
                lines.append(f"- 🆕 Created repository **[{name}]({url})** &nbsp;·&nbsp; _{when}_")
            else:
                lines.append(f"- ✨ Created {rt} in **[{name}]({url})** &nbsp;·&nbsp; _{when}_")
        elif et == "ReleaseEvent":
            tag = e["payload"].get("release", {}).get("tag_name", "")
            lines.append(f"- 🎉 Released `{tag}` in **[{name}]({url})** &nbsp;·&nbsp; _{when}_")
        elif et == "WatchEvent":
            lines.append(f"- ⭐ Starred **[{name}]({url})** &nbsp;·&nbsp; _{when}_")
        elif et == "PublicEvent":
            lines.append(f"- 🌍 Open-sourced **[{name}]({url})** &nbsp;·&nbsp; _{when}_")
        elif et == "ForkEvent":
            lines.append(f"- 🍴 Forked **[{name}]({url})** &nbsp;·&nbsp; _{when}_")
        i += 1
    return "\n".join(lines) if lines else "_No recent public activity._"


def section_snapshot(repos):
    user = gh(f"/users/{USER}")
    total_stars = sum(r["stargazers_count"] for r in repos)
    return (f"<b>{user['public_repos']}</b> public repos &nbsp;·&nbsp; "
            f"<b>⭐ {total_stars}</b> stars earned &nbsp;·&nbsp; "
            f"<b>{user['followers']}</b> followers")


def section_wakatime():
    """WakaTime last-7-days language breakdown.

    Returns None when WAKATIME_API_KEY isn't set, so the section keeps its
    placeholder until the user wires up the secret — no failures, no blanks.
    """
    key = os.environ.get("WAKATIME_API_KEY")
    if not key:
        return None
    auth = base64.b64encode(key.encode()).decode()
    req = urllib.request.Request(
        "https://wakatime.com/api/v1/users/current/stats/last_7_days",
        headers={"Authorization": f"Basic {auth}", "User-Agent": f"{USER}-profile-bot"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)["data"]
    langs = data.get("languages", [])[:6]
    if not langs:
        return "```text\nNo coding activity tracked in the last 7 days yet.\n```"
    width = 25
    rows = []
    for lang in langs:
        name = lang["name"][:12]
        text = lang.get("text", "0 secs")
        pct = float(lang.get("percent", 0.0))
        filled = round(pct / 100 * width)
        bar = "█" * filled + "░" * (width - filled)
        rows.append(f"{name:<13}{text:<16}{bar} {pct:>5.1f}%")
    total = data.get("human_readable_total", "")
    header = f"**🗓️ Last 7 days — {total} of tracked coding**\n\n" if total else ""
    return header + "```text\n" + "\n".join(rows) + "\n```"


def main():
    with open(README, encoding="utf-8") as f:
        text = f.read()

    try:
        builds, repos = section_builds()
        text = splice(text, "LATEST_BUILDS", builds)
        text = splice(text, "SNAPSHOT", section_snapshot(repos))
    except Exception as ex:
        print("  ! builds/snapshot failed:", ex)

    try:
        text = splice(text, "TECHPULSE", section_techpulse())
    except Exception as ex:
        print("  ! techpulse failed:", ex)

    try:
        text = splice(text, "ACTIVITY", section_activity())
    except Exception as ex:
        print("  ! activity failed:", ex)

    try:
        waka = section_wakatime()
        if waka is not None:
            text = splice(text, "WAKA", waka)
    except Exception as ex:
        print("  ! wakatime failed:", ex)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = splice(text, "UPDATED",
                  f"<sub>🔄 Last refreshed {stamp} · auto-updates every 6h via GitHub Actions</sub>")

    with open(README, "w", encoding="utf-8") as f:
        f.write(text)
    print("README updated.")


if __name__ == "__main__":
    main()
