"""Tests for backend/scripts/next_version.py."""

from scripts.next_version import next_version


def test_no_tags_returns_v010() -> None:
    """No semver tags → first release v0.1.0."""
    assert next_version(tags=[], commit_messages=[]) == "v0.1.0"


def test_non_semver_tags_ignored() -> None:
    """Tags that don't match vX.Y.Z are skipped."""
    assert (
        next_version(
            tags=["latest", "stable", "foo"],
            commit_messages=[],
        )
        == "v0.1.0"
    )


def test_patch_bump() -> None:
    """Default bump is patch +1."""
    assert (
        next_version(
            tags=["v0.1.0"],
            commit_messages=[],
        )
        == "v0.1.1"
    )
    assert (
        next_version(
            tags=["v1.2.3"],
            commit_messages=[],
        )
        == "v1.2.4"
    )


def test_minor_bump() -> None:
    """[minor] in any commit message bumps minor and resets patch."""
    assert (
        next_version(
            tags=["v0.1.0"],
            commit_messages=["feat: add new endpoint [minor]"],
        )
        == "v0.2.0"
    )
    assert (
        next_version(
            tags=["v1.2.3"],
            commit_messages=["some commit\n[minor] another line"],
        )
        == "v1.3.0"
    )


def test_major_bump() -> None:
    """[major] in any commit message bumps major and resets minor+patch."""
    assert (
        next_version(
            tags=["v0.9.5"],
            commit_messages=["breaking: redesign [major]"],
        )
        == "v1.0.0"
    )


def test_major_takes_precedence_over_minor() -> None:
    """When both [major] and [minor] are present, major wins."""
    result = next_version(
        tags=["v0.1.0"],
        commit_messages=[
            "small change [minor]",
            "big change [major]",
        ],
    )
    assert result == "v1.0.0"


def test_latest_semver_tag_used() -> None:
    """When multiple semver tags exist, the highest is used as base."""
    assert (
        next_version(
            tags=["v0.1.0", "v0.2.0", "v0.3.1"],
            commit_messages=[],
        )
        == "v0.3.2"
    )


def test_non_semver_tags_with_valid_semver() -> None:
    """Non-semver tags are ignored; valid semver tags are used."""
    assert (
        next_version(
            tags=["latest", "v0.5.0", "stable"],
            commit_messages=[],
        )
        == "v0.5.1"
    )


def test_major_bump_resets_minor_and_patch() -> None:
    """[major] resets minor and patch to zero."""
    assert (
        next_version(
            tags=["v2.5.9"],
            commit_messages=["major rewrite [major]"],
        )
        == "v3.0.0"
    )


def test_only_commits_since_the_latest_tag_count(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """An old commit mentioning [major] must not bump again after it was released."""
    import scripts.next_version as nv

    seen: list[str | None] = []

    def fake_log(since: str | None = None) -> list[str]:
        seen.append(since)
        return ["Fix the worker"]

    monkeypatch.setattr(nv, "_git_tags", lambda: ["v0.1.0"])
    monkeypatch.setattr(nv, "_git_log_messages", fake_log)
    assert nv.next_version() == "v0.1.1"
    assert seen == ["v0.1.0"]
