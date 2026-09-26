"""computer.launch: resolving what a model asked for ("Google Chrome") to an installed executable.

Regression: many real requests to launch Chrome or Edge failed outright. The tool only accepted the exact
shortcut words "chrome"/"edge" or a name that matched a Windows registry entry byte-for-byte; a model
naturally writes "Google Chrome" or "Microsoft Edge", which matched neither, so every such launch failed
with a generic, unhelpful error. This is pure name-resolution logic and needs no real Windows APIs."""
from pathlib import Path

import pytest

from stonic.tools.windows import resolve_application


def choices(tmp_path):
    exe = tmp_path / "chrome.exe"
    exe.write_bytes(b"")
    edge = tmp_path / "msedge.exe"
    edge.write_bytes(b"")
    return {"chrome": [exe, tmp_path / "missing-chrome.exe"], "edge": [edge], "notepad": [tmp_path / "no-notepad.exe"],
            "calculator": [tmp_path / "no-calc.exe"], "explorer": [tmp_path / "no-explorer.exe"]}


@pytest.mark.parametrize("asked", ["chrome", "Chrome", "CHROME.EXE", "Google Chrome", "google chrome", "chrome browser", "GoogleChrome"])
def test_common_ways_of_asking_for_chrome_all_resolve(tmp_path, asked):
    assert resolve_application(asked, [], choices(tmp_path)) == choices(tmp_path)["chrome"][0]


@pytest.mark.parametrize("asked", ["edge", "Edge", "msedge", "Microsoft Edge", "microsoft edge", "edge browser"])
def test_common_ways_of_asking_for_edge_all_resolve(tmp_path, asked):
    assert resolve_application(asked, [], choices(tmp_path)) == choices(tmp_path)["edge"][0]


def test_a_registered_app_matching_the_alias_is_preferred_over_the_hardcoded_path(tmp_path):
    registered = tmp_path / "actual-chrome-install" / "chrome.exe"
    registered.parent.mkdir()
    registered.write_bytes(b"")
    result = resolve_application("Google Chrome", [{"name": "chrome.exe", "path": str(registered)}], choices(tmp_path))
    assert result == registered


def test_an_alias_with_nothing_installed_anywhere_gives_a_clear_reason(tmp_path):
    empty = {"chrome": [tmp_path / "nope1.exe", tmp_path / "nope2.exe"]}
    with pytest.raises(ValueError, match="not installed at a known Windows location"):
        resolve_application("chrome", [], empty)


def test_an_exact_registered_name_still_matches_as_before(tmp_path):
    exe = tmp_path / "Code.exe"
    exe.write_bytes(b"")
    assert resolve_application("Code.exe", [{"name": "Code.exe", "path": str(exe)}], {}) == exe
    assert resolve_application("code", [{"name": "Code.exe", "path": str(exe)}], {}) == exe


def test_a_natural_product_name_matches_a_registered_app_by_meaning_not_by_string_equality(tmp_path):
    exe = tmp_path / "Code.exe"
    exe.write_bytes(b"")
    candidates = [{"name": "Code.exe", "path": str(exe)}]
    assert resolve_application("Visual Studio Code", candidates, {}) == exe
    assert resolve_application("Microsoft Visual Studio Code", candidates, {}) == exe


def test_two_installed_apps_with_the_same_meaningful_words_stay_ambiguous(tmp_path):
    a, b = tmp_path / "a.exe", tmp_path / "b.exe"
    a.write_bytes(b""); b.write_bytes(b"")
    candidates = [{"name": "Studio One", "path": str(a)}, {"name": "One Studio", "path": str(b)}]
    with pytest.raises(ValueError):
        resolve_application("Studio One Pro", candidates, {})


def test_a_descriptive_request_still_resolves_to_the_one_app_it_names(tmp_path):
    exe = tmp_path / "Slack.exe"
    exe.write_bytes(b"")
    assert resolve_application("Slack Messenger", [{"name": "Slack.exe", "path": str(exe)}], {}) == exe


def test_an_unknown_app_error_suggests_close_registered_names(tmp_path):
    # "Slack Enterprise" shares a word with the request but is not fully described by it, so it is a HINT, not a match.
    exe = tmp_path / "Slack Enterprise.exe"
    exe.write_bytes(b"")
    with pytest.raises(ValueError, match="Slack Enterprise.exe"):
        resolve_application("slack messenger", [{"name": "Slack Enterprise.exe", "path": str(exe)}], {})


def test_a_completely_unrelated_request_gives_a_recovery_hint_not_a_dead_end():
    with pytest.raises(ValueError, match="computer.applications"):
        resolve_application("some random program", [{"name": "Notepad.exe", "path": "/x"}], {})
