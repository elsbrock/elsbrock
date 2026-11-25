#!/usr/bin/env python3
"""Render the profile README from public GitHub data and print it to stdout.

Every query goes through user(login:) instead of viewer, so the workflow's
built-in GITHUB_TOKEN is enough -- no personal access token to create or
rotate. Private repositories are filtered out explicitly as well, so running
this locally with a broader token renders the same public page.

Usage: GH_TOKEN=... scripts/readme.py > README.md
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

LOGIN = "elsbrock"
COUNT = 5
DESCRIPTION_MAX = 110

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      commitContributionsByRepository(maxRepositories: 25) {
        repository { nameWithOwner url description isPrivate }
        contributions(first: 1, orderBy: {field: OCCURRED_AT, direction: DESC}) {
          nodes { occurredAt }
        }
      }
    }
    repositories(first: 20, privacy: PUBLIC, isFork: false,
                 ownerAffiliations: OWNER,
                 orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes { nameWithOwner url description isArchived }
    }
    repositoriesContributedTo(first: 100, privacy: PUBLIC,
                              includeUserRepositories: true,
                              contributionTypes: [COMMIT, PULL_REQUEST]) {
      nodes {
        nameWithOwner url description
        latestRelease { tagName url publishedAt }
      }
    }
    pullRequests(first: 25, orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes {
        title url createdAt
        repository { nameWithOwner url isPrivate }
      }
    }
    starredRepositories(first: 10, orderBy: {field: STARRED_AT, direction: DESC}) {
      edges { starredAt node { nameWithOwner url description isPrivate } }
    }
  }
}
"""


def graphql(query, **variables):
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GH_TOKEN or GITHUB_TOKEN must be set")
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-readme",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.load(response)
    if body.get("errors"):
        sys.exit(f"GraphQL errors: {json.dumps(body['errors'], indent=2)}")
    return body["data"]


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def ago(value, now=None):
    """Relative time in the same shape markscribe used ("2 weeks ago")."""
    now = now or datetime.now(timezone.utc)
    days = (now - parse_time(value)).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    for size, unit in ((365, "year"), (30, "month"), (7, "week"), (1, "day")):
        if days >= size:
            n = days // size
            return f"{n} {unit}{'s' if n > 1 else ''} ago"


def escape(text):
    """Keep descriptions and titles from turning into Markdown markup."""
    for char in "\\*_[]<>`":
        text = text.replace(char, "\\" + char)
    return text


def describe(description):
    if not description:
        return ""
    description = " ".join(description.split())
    if len(description) > DESCRIPTION_MAX:
        description = description[: DESCRIPTION_MAX - 1].rstrip() + "…"
    return " - " + escape(description)


def link(repo):
    return f"[{repo['nameWithOwner']}]({repo['url']})"


def is_profile_repo(repo):
    return repo["nameWithOwner"].lower() == f"{LOGIN}/{LOGIN}".lower()


def working_on(user):
    rows = []
    for entry in user["contributionsCollection"]["commitContributionsByRepository"]:
        repo = entry["repository"]
        nodes = entry["contributions"]["nodes"]
        if repo["isPrivate"] or is_profile_repo(repo) or not nodes:
            continue
        rows.append((nodes[0]["occurredAt"], repo))
    rows.sort(key=lambda row: row[0], reverse=True)
    return [
        f"- {link(repo)}{describe(repo['description'])} ({ago(when)})"
        for when, repo in rows[:COUNT]
    ]


def latest_projects(user):
    repos = [
        repo
        for repo in user["repositories"]["nodes"]
        if not repo["isArchived"] and not is_profile_repo(repo)
    ]
    return [f"- {link(repo)}{describe(repo['description'])}" for repo in repos[:COUNT]]


def latest_releases(user):
    repos = [
        repo
        for repo in user["repositoriesContributedTo"]["nodes"]
        if repo["latestRelease"] and repo["latestRelease"]["publishedAt"]
    ]
    repos.sort(key=lambda repo: repo["latestRelease"]["publishedAt"], reverse=True)
    rows = []
    for repo in repos[:COUNT]:
        release = repo["latestRelease"]
        rows.append(
            f"- {link(repo)} ([{escape(release['tagName'])}]({release['url']}),"
            f" {ago(release['publishedAt'])}){describe(repo['description'])}"
        )
    return rows


def pull_requests(user):
    prs = [
        pr
        for pr in user["pullRequests"]["nodes"]
        if not pr["repository"]["isPrivate"]
    ]
    return [
        f"- [{escape(pr['title'])}]({pr['url']}) on {link(pr['repository'])}"
        f" ({ago(pr['createdAt'])})"
        for pr in prs[:COUNT]
    ]


def stars(user):
    edges = [
        edge
        for edge in user["starredRepositories"]["edges"]
        if not edge["node"]["isPrivate"]
    ]
    return [
        f"- {link(edge['node'])}{describe(edge['node']['description'])}"
        f" ({ago(edge['starredAt'])})"
        for edge in edges[:COUNT]
    ]


def section(title, rows):
    if not rows:
        return ""
    return f"#### {title}\n\n" + "\n".join(rows) + "\n"


def main():
    user = graphql(QUERY, login=LOGIN)["user"]
    sections = [
        "### Hi there 👋\n",
        section("👷 Check out what I'm currently working on", working_on(user)),
        section("🌱 My latest projects", latest_projects(user)),
        section("🔭 Latest releases I've contributed to", latest_releases(user)),
        section("🔨 My recent Pull Requests", pull_requests(user)),
        section("⭐ Recent Stars", stars(user)),
    ]
    sys.stdout.write("\n".join(part for part in sections if part))


if __name__ == "__main__":
    main()
