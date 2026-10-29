#!/usr/bin/env python3
"""Self-updating sections for the GitHub profile README.

Pulls live data from the GitHub REST API (no extra secrets — the built-in
GITHUB_TOKEN is enough) and rewrites the marker-delimited sections of
README.md in place. Each section updates independently and leaves the
existing statistics untouched if their fetch fails. Publication status is
different: unavailable verification is shown explicitly rather than
preserving an apparently current success claim.
"""

import base64
import json
import os
import re
import urllib.request
from datetime import datetime, timezone

USER = "aredwan-xyz"
PROFILE_REPO = "aredwan-xyz"   # the special profile repo — excluded from "builds"
README = "README.md"
API = "https://api.github.com"
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

# Keep the profile's status wording independent of older repository taglines.
PROJECT_SUMMARIES = {
    "codebeez-ai-phone-agent": "Voice-agent prototype; latency target pending benchmarks.",
    "codebeez-ai-autopilot": "Business-agent framework; integrations require configuration and validation.",
    "video-autopilot": "Video-generation pipeline with opt-in publishing; see run outputs for results.",
    "remote-jobs-ai-curator": "Remote tech roles collected from selected sources.",
    "evergreen-stats": "Generates static GitHub profile SVGs in a scheduled Action.",
    "codebeez-innovation-resources": "Tools and research directory maintained by CodeBeez.",
    "ai-mastery-ultimate-resources": "AI learning roadmaps, references and project exercises.",
    "agenttrust-os": "Local agent-manifest scanner with Markdown risk reports.",
}

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
        desc = trunc(PROJECT_SUMMARIES.get(r["name"], r.get("description")))
        desc_part = f" — {desc}" if desc else ""
        stars = r["stargazers_count"]
        star_txt = f" &nbsp;·&nbsp; ⭐ {stars}" if stars else ""
        lines.append(
            f"{emoji} **[{r['name']}]({r['html_url']})**{desc_part}{star_txt} &nbsp;·&nbsp; _{ago(r['pushed_at'])}_"
        )
    return "<br>".join(lines), repos


def section_techpulse():
    """Verify the manifest and archive against a single immutable commit."""
    url = f"https://github.com/{USER}/techpulse-daily"
    try:
        prefix = f"/repos/{USER}/techpulse-daily"
        sha = gh(f"{prefix}/commits/main")["sha"]
        tree = gh(f"{prefix}/git/trees/{sha}?recursive=1")
        if tree.get("truncated"):
            raise ValueError("publication tree is incomplete")
        files = {item["path"]: item for item in tree["tree"] if item["type"] == "blob"}
        if "STATUS.json" not in files:
            return f"Publication unverified: no validated publication manifest is available. [Inspect archives]({url}/tree/main/archive)."
        manifest = gh(f"{prefix}/contents/STATUS.json?ref={sha}")
        status = json.loads(base64.b64decode(manifest["content"]).decode("utf-8"))
        date = status.get("published_date", "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            raise ValueError("invalid publication date")
        day = datetime.strptime(date, "%Y-%m-%d").date()
        if day > datetime.now(timezone.utc).date():
            raise ValueError("publication is dated in the future")
        archive = f"archive/{day:%Y/%m}/{date}.md"
        feeds = ("news", "trending", "research", "challenges", "tools", "prompts", "security", "market", "learning")
        expected = [f"feeds/{feed}/{date}.md" for feed in feeds] + [archive]
        if (status.get("status") != "complete" or status.get("feeds_published") != 9
                or status.get("feeds_expected") != 9 or status.get("archive") != archive
                or not all(path in files and files[path].get("size", 0) > 0 for path in expected)):
            raise ValueError("manifest and expected files do not agree")
        data = gh(f"{prefix}/contents/{archive}?ref={sha}")
        body = base64.b64decode(data["content"]).decode("utf-8")
        if (not re.search(r"\*\*Feeds:\*\*\s*9/9 published", body)
                or "Not yet published" in body or "Could not read" in body):
            raise ValueError("archive is incomplete")
        return (f"Last verified complete digest: **[{date}]({url}/blob/{sha}/{archive})** · **9/9 feeds**.\n\n"
                "This is the last complete publication, not a claim that today's scheduled run succeeded.")
    except Exception:
        return f"Publication status unavailable: the manifest and feed files could not be verified. [Inspect TechPulse]({url})."


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


def section_languages(repos):
    """Aggregate language usage (by bytes) across owned repos.

    Self-hosted alternative to third-party stat cards: pulls /languages for
    each repo, sums the byte counts, and renders a themed bar chart. Fully
    generated from the GitHub API without an external image-rendering service.
    """
    totals = {}
    for r in repos:
        try:
            data = gh(f"/repos/{r['full_name']}/languages")
        except Exception:
            continue
        for lang, byts in data.items():
            totals[lang] = totals.get(lang, 0) + byts
    if not totals:
        return "```text\nLanguage data warming up…\n```"
    grand = sum(totals.values())
    top = sorted(totals.items(), key=lambda kv: -kv[1])[:6]
    width = 24
    rows = []
    for name, byts in top:
        pct = byts / grand * 100
        filled = round(pct / 100 * width)
        bar = "█" * filled + "░" * (width - filled)
        emoji = LANG_EMOJI.get(name, "•")
        rows.append(f"{emoji} {name:<13}{bar} {pct:>5.1f}%")
    return "```text\n" + "\n".join(rows) + "\n```"


def main():
    with open(README, encoding="utf-8") as f:
        text = f.read()

    try:
        builds, repos = section_builds()
        text = splice(text, "LATEST_BUILDS", builds)
        text = splice(text, "SNAPSHOT", section_snapshot(repos))
        text = splice(text, "LANGS", section_languages(repos))
    except Exception as ex:
        print("  ! builds/snapshot/langs failed:", ex)

    try:
        text = splice(text, "TECHPULSE", section_techpulse())
    except Exception as ex:
        print("  ! techpulse failed:", ex)

    try:
        text = splice(text, "ACTIVITY", section_activity())
    except Exception as ex:
        print("  ! activity failed:", ex)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = splice(text, "UPDATED",
                  f"<sub>Last data-check attempt: {stamp}. Scheduled every 6h; publication verification status is shown above.</sub>")

    with open(README, "w", encoding="utf-8") as f:
        f.write(text)
    print("README updated.")


if __name__ == "__main__":
    main()
