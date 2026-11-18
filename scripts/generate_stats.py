"""Render the profile card with public GitHub data. Run with an authenticated gh CLI."""
from html import escape
import json
from math import tau
from pathlib import Path
import subprocess


LOGIN = "xiaohantiko"
OUTPUT = Path(__file__).resolve().parents[1] / "assets" / "github-stats.svg"

STARS = """
query($login:String!, $after:String) {
  user(login:$login) {
    repositories(first:100, after:$after, privacy:PUBLIC, isFork:false, ownerAffiliations:[OWNER]) {
      nodes { stargazerCount }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""
ACTIVITY = """
query($login:String!, $prs:String!, $issues:String!) {
  user(login:$login) {
    followers { totalCount }
    contributionsCollection {
      endedAt
      commits: commitContributionsByRepository(maxRepositories:100) {
        repository { id visibility }
        contributions { totalCount }
      }
      issues: issueContributionsByRepository(maxRepositories:100) { repository { id visibility } }
      prs: pullRequestContributionsByRepository(maxRepositories:100) { repository { id visibility } }
      reviews: pullRequestReviewContributionsByRepository(maxRepositories:100) {
        repository { id visibility }
        contributions { totalCount }
      }
    }
  }
  prs: search(query:$prs, type:ISSUE) { issueCount }
  issues: search(query:$issues, type:ISSUE) { issueCount }
}
"""


def graphql(query, **variables):
    command = ["gh", "api", "graphql", "-f", f"query={query}"]
    for name, value in variables.items():
        command.extend(["-f", f"{name}={value}"])
    response = subprocess.check_output(command, text=True)
    return json.loads(response)["data"]


def public_stars():
    variables = {"login": LOGIN}
    total = 0
    while True:
        page = graphql(STARS, **variables)["user"]["repositories"]
        total += sum(repo["stargazerCount"] for repo in page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            return total
        variables["after"] = page["pageInfo"]["endCursor"]


def public_activity():
    data = graphql(ACTIVITY, login=LOGIN, prs=f"author:{LOGIN} is:public is:pr",
                   issues=f"author:{LOGIN} is:public is:issue")
    collection = data["user"]["contributionsCollection"]
    repositories = set()
    counts = {}
    for kind in ("commits", "issues", "prs", "reviews"):
        rows = collection[kind]
        if len(rows) == 100:
            raise RuntimeError(f"GitHub's per-repository limit was reached for {kind}. "
                               "Split the activity period before replacing the current card.")
        public_rows = [row for row in rows if row["repository"]["visibility"] == "PUBLIC"]
        repositories.update(row["repository"]["id"] for row in public_rows)
        if kind in ("commits", "reviews"):
            counts[kind] = sum(row["contributions"]["totalCount"] for row in public_rows)
    return {
        **counts,
        "stars": public_stars(),
        "prs": data["prs"]["issueCount"],
        "issues": data["issues"]["issueCount"],
        "repositories": len(repositories),
        "followers": data["user"]["followers"]["totalCount"],
        "date": collection["endedAt"][:10],
    }


# Rank formula adapted from GitHub Readme Stats, src/calculateRank.js.
# https://github.com/anuraghazra/github-readme-stats
# MIT License. Copyright (c) 2020 Anurag Hazra
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
def activity_rank(stats):
    score = sum(weight * (1 - 2 ** (-stats[key] / median)) for key, median, weight in (
        ("commits", 250, 2), ("prs", 50, 3), ("issues", 25, 1), ("reviews", 2, 1)
    ))
    for key, median, weight in (("stars", 50, 4), ("followers", 10, 1)):
        score += weight * stats[key] / (median + stats[key])
    progress = 100 * score / 12
    bands = [(1, "S"), (12.5, "A+"), (25, "A"), (37.5, "A-"), (50, "B+"),
             (62.5, "B"), (75, "B-"), (87.5, "C+"), (100, "C")]
    grade = next(label for cutoff, label in bands if 100 - progress <= cutoff)
    return grade, progress


def render(stats):
    rows = (
        ("stars", "Total Stars Earned", '<path d="m12 2.2 3 6.1 6.7 1-4.85 4.7 1.15 6.7-6-3.15-6 3.15 1.15-6.7-4.85-4.7 6.7-1z"/>'),
        ("commits", "Total Commits (last year)", '<path d="M3.4 10a8.7 8.7 0 1 1 .7 6.1M3 4.8V10h5.2M12 7v5l3.2 2"/>'),
        ("prs", "Total PRs", '<circle cx="6" cy="5" r="2.2"/><circle cx="6" cy="19" r="2.2"/><circle cx="18" cy="19" r="2.2"/><path d="M6 7.2v9.6M18 16.8v-6A5.8 5.8 0 0 0 12.2 5H12m2.4-2.5L12 5l2.4 2.5"/>'),
        ("issues", "Total Issues", '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.8m0 3h.01"/>'),
        ("repositories", "Contributed to (last year)", '<path d="M5 4.3A1.8 1.8 0 0 1 6.8 2.5h12.7v16H7a2 2 0 0 1 0-4h12.5M5 4.3v12.2m3 2.2v3l2-1.2 2 1.2v-3"/>'),
    )
    grade, progress = activity_rank(stats)
    circumference = 62 * tau
    row_markup = []
    for index, (key, label, icon) in enumerate(rows):
        y = 94 + 40 * index
        row_markup.append(f'''  <g transform="translate(28 {y - 18})" class="icon">{icon}</g>
  <text x="69" y="{y}">{label}:</text>
  <text x="401" y="{y}">{stats[key]:,}</text>''')
    description = "; ".join(f"{label}: {stats[key]}" for key, label, _ in rows)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="736" height="302" viewBox="0 0 736 302" role="img" aria-labelledby="title desc">
  <title id="title">{LOGIN}'s GitHub Stats</title>
  <desc id="desc">{escape(description)}. Public activity only. Stars on owned non-fork repositories. Repositories with commit, issue, pull request or review contributions in the last year. Grade {grade} uses the unofficial GitHub Readme Stats formula. Updated {stats["date"]} UTC.</desc>
  <style>
    svg {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }}
    .panel {{ fill: #fff; stroke: #d8dee4; }}
    text {{ fill: #424d5b; font-size: 22px; font-weight: 600; }}
    .heading {{ fill: #0969da; font-size: 31px; font-weight: 650; }}
    .icon {{ fill: none; stroke: #0879e8; stroke-width: 1.9; stroke-linecap: round; stroke-linejoin: round; }}
    .track {{ stroke: #d1e1fa; }} .arc {{ stroke: #3d88e9; }}
    .grade {{ font-size: 41px; font-weight: 650; }}
    .note {{ fill: #576574; font-size: 12px; font-weight: 400; }}
    @media (prefers-color-scheme: dark) {{
      .panel {{ fill: #0d1117; stroke: #30363d; }} text {{ fill: #d7dfe9; }}
      .heading {{ fill: #62aaff; }} .icon, .arc {{ stroke: #58a6ff; }}
      .track {{ stroke: #24384e; }} .note {{ fill: #9caab9; }}
    }}
  </style>
  <rect class="panel" x=".5" y=".5" width="735" height="301" rx="12"/>
  <text class="heading" x="28" y="49">{LOGIN}'s GitHub Stats</text>
{chr(10).join(row_markup)}
  <g fill="none" stroke-width="9">
    <circle class="track" cx="611" cy="166" r="62"/>
    <circle class="arc" cx="611" cy="166" r="62" stroke-dasharray="{circumference * progress / 100:.2f} {circumference:.2f}" stroke-linecap="round" transform="rotate(-90 611 166)"/>
  </g>
  <text class="grade" x="611" y="180" text-anchor="middle">{grade}</text>
  <text class="note" x="28" y="283">Public activity · {stats["date"]} UTC</text>
  <text class="note" x="709" y="283" text-anchor="end">Unofficial GitHub Readme Stats grade</text>
</svg>
'''


if __name__ == "__main__":
    svg = render(public_activity())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(svg, encoding="utf-8")
