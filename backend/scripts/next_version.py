"""Compute the next semantic version based on git tags and commit messages.

Per SPEC 9.3: every push to main that passes is a release vX.Y.Z.
Default bump is patch; [minor] or [major] in a commit message bumps higher.
First release is v0.1.0.

Stdlib only: subprocess (git) and re.
"""

import re
import subprocess
from collections.abc import Sequence

_SEMVER_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def _git_tags() -> list[str]:
    """Return all light-weight tags sorted by creation order (oldest first)."""
    result = subprocess.run(  # noqa: S603
        ["git", "tag", "--sort=creatordate"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    )
    return [t for t in result.stdout.strip().split("\n") if t]


def _git_log_messages(since: str | None = None) -> list[str]:
    """Return the full messages of the commits after tag *since* (all commits when None)."""
    rev = f"{since}..HEAD" if since else "HEAD"
    result = subprocess.run(  # noqa: S603
        ["git", "log", rev, "--format=%B%x00"],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    )
    return [m.strip() for m in result.stdout.split("\x00") if m.strip()]


def next_version(
    tags: Sequence[str] | None = None,
    commit_messages: Sequence[str] | None = None,
) -> str:
    """Return the next version string.

    *tags* – tag names to consider (e.g. ``["v0.1.0", "v0.2.0"]``).
    *commit_messages* – subject lines to scan for ``[minor]`` / ``[major]``.

    When either is *None* the function queries git directly.
    """
    if tags is None:
        tags = _git_tags()

    # 1. Find the latest semver tag
    semver_tags: list[tuple[int, int, int, str]] = []
    for tag in tags:
        m = _SEMVER_RE.match(tag)
        if m:
            semver_tags.append((int(m.group(1)), int(m.group(2)), int(m.group(3)), tag))

    if not semver_tags:
        return "v0.1.0"

    # Sort by (major, minor, patch) and pick the highest
    semver_tags.sort()
    major, minor, patch, latest = semver_tags[-1]
    if commit_messages is None:
        # Only the commits since the latest release count; older ones were already released.
        commit_messages = _git_log_messages(since=latest)

    # 2. Determine bump level from commit messages
    bump = "patch"
    for msg in commit_messages:
        if "[major]" in msg:
            bump = "major"
            break
        if "[minor]" in msg:
            bump = "minor"

    # 3. Apply bump
    if bump == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1

    return f"v{major}.{minor}.{patch}"


def main() -> None:
    """Print the next version to stdout."""
    print(next_version())


if __name__ == "__main__":
    main()
