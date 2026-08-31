"""
Default CLI selector tests — `comicbox.formats.base.online.prompt`.

`prompt.cli_selector` is what every interactive run gets when no
programmatic selector was registered (`box/online_lookup.py`,
`_resolve_selector`), so its formatting, its reply grammar, and its
submenu loops are user-facing surface. Most of the module is pure and
needs no mocks; the loops are driven by monkeypatching `_prompt_line`
and `_read_input` with scripted reply sequences.
"""

from __future__ import annotations

import sys
from argparse import Namespace
from typing import TYPE_CHECKING, cast

import pytest

from comicbox.config import get_config
from comicbox.formats.base.online import prompt
from comicbox.formats.base.online.profile import (
    Candidate,
    CandidateSummary,
    ComicProfile,
)
from comicbox.formats.base.online.selector import SelectorContext

if TYPE_CHECKING:
    from comicbox.config.settings import ComicboxSettings

# --- helpers ----------------------------------------------------------------


def _summary(
    *,
    series: str = "Foo Comics",
    issue: str = "5",
    year: int | None = 2020,
    publisher: str | None = "Quality Comics",
    page_count: int | None = 24,
) -> CandidateSummary:
    return CandidateSummary(
        series=series,
        issue=issue,
        year=year,
        publisher=publisher,
        page_count=page_count,
        cover_url=None,
        variant_label=None,
    )


def _candidate(
    issue_id: int = 101,
    *,
    url: str = "",
    score: float = 0.91,
    cover_score: float | None = None,
    **summary_kwargs,
) -> Candidate:
    return Candidate(
        source="metron",
        issue_id=issue_id,
        summary=_summary(**summary_kwargs),
        score=score,
        cover_score=cover_score,
        url=url,
    )


class _ScriptedPrompt:
    """Stand-in for `_prompt_line` replaying a fixed reply sequence."""

    def __init__(self, *replies: str | None) -> None:
        self.replies: list[str | None] = list(replies)
        self.messages: list[str] = []

    def __call__(self, message: str) -> str | None:
        self.messages.append(message)
        if not self.replies:
            reason = f"prompt asked past the end of the script: {message!r}"
            raise AssertionError(reason)
        return self.replies.pop(0)


def _settings(loglevel: str | int = "INFO") -> ComicboxSettings:
    """Real settings with only the loglevel pinned — terse's one input."""
    return get_config(
        Namespace(comicbox=Namespace(general=Namespace(loglevel=loglevel)))
    )


def _ctx(
    *,
    file_path: object = None,
    source: str = "metron",
    settings: object = None,
) -> SelectorContext:
    return SelectorContext(
        file_path=cast("None", file_path),
        source=source,
        settings=cast("ComicboxSettings", settings) if settings else _settings(),
        triggered_hashing=False,
    )


# --- _format_candidate_line -------------------------------------------------


def test_format_candidate_line_full() -> None:
    line = prompt._format_candidate_line(1, _candidate())
    assert line == "1. Foo Comics #5 (2020)   score=0.91 [metron:101]"


def test_format_candidate_line_without_year() -> None:
    """No year → the parenthetical is dropped, not rendered as `(None)`."""
    line = prompt._format_candidate_line(3, _candidate(year=None))
    assert "(None)" not in line
    assert line == "3. Foo Comics #5   score=0.91 [metron:101]"


def test_format_candidate_line_shows_cover_score() -> None:
    """A hashed candidate carries its cover score beside the total."""
    line = prompt._format_candidate_line(2, _candidate(cover_score=0.75))
    assert "score=0.91 (cov=0.75)" in line


def test_format_candidate_line_shows_zero_cover_score() -> None:
    """cover_score=0.0 is a measurement, not an absence — it must render."""
    line = prompt._format_candidate_line(1, _candidate(cover_score=0.0))
    assert "(cov=0.00)" in line


# --- _format_aux_lines ------------------------------------------------------


def test_format_aux_lines_details_and_url() -> None:
    aux = prompt._format_aux_lines(_candidate(url="https://example.test/1"))
    assert aux == [
        "   publisher='Quality Comics', pages=24, year=2020",
        "   https://example.test/1",
    ]


def test_format_aux_lines_empty_when_nothing_to_show() -> None:
    bare = _candidate(publisher=None, page_count=None, year=None, url="")
    assert prompt._format_aux_lines(bare) == []


def test_format_aux_lines_url_only() -> None:
    bare = _candidate(publisher=None, page_count=None, year=None, url="u")
    assert prompt._format_aux_lines(bare) == ["   u"]


def test_format_aux_lines_zero_page_count_renders() -> None:
    """`pages=0` is a real value; `is not None` must win over truthiness."""
    aux = prompt._format_aux_lines(_candidate(publisher=None, page_count=0, year=None))
    assert aux == ["   pages=0"]


# --- _build_lines -----------------------------------------------------------


def test_build_lines_header_names_the_file() -> None:
    lines = prompt._build_lines(
        ComicProfile(series="Foo"), [_candidate()], "/comics/foo.cbz", terse=False
    )
    assert lines[1] == "Ambiguous match for /comics/foo.cbz"


def test_build_lines_header_without_a_path() -> None:
    lines = prompt._build_lines(
        ComicProfile(series="Foo"), [_candidate()], None, terse=False
    )
    assert lines[1] == "Ambiguous match"


def test_build_lines_existing_row_summarizes_the_profile() -> None:
    profile = ComicProfile(series="Foo", issue="5", year=2020, publisher="Quality")
    lines = prompt._build_lines(profile, [_candidate()], None, terse=False)
    assert lines[2] == (
        "  Existing: series='Foo' issue=#5 year=2020 publisher='Quality'"
    )


def test_build_lines_omits_existing_row_for_an_empty_profile() -> None:
    """Nothing known about the comic → no misleading all-None summary line."""
    lines = prompt._build_lines(ComicProfile(), [_candidate()], None, terse=False)
    assert not any("Existing:" in line for line in lines)


def test_build_lines_includes_the_action_menu() -> None:
    lines = prompt._build_lines(ComicProfile(), [_candidate()], None, terse=False)
    assert lines[-4:] == [
        "  s. Skip this file",
        "  m. Enter ID manually",
        "  o. Session options ...",
        "  q. Abort entire run",
    ]


def test_build_lines_terse_drops_aux_lines() -> None:
    candidates = [_candidate(url="https://example.test/1")]
    verbose = prompt._build_lines(ComicProfile(), candidates, None, terse=False)
    terse = prompt._build_lines(ComicProfile(), candidates, None, terse=True)
    assert any("publisher=" in line for line in verbose)
    assert not any("publisher=" in line for line in terse)
    assert not any("example.test" in line for line in terse)
    assert any("1. Foo Comics" in line for line in terse)


def test_build_lines_caps_the_candidate_list_at_nine() -> None:
    """`_MAX_DISPLAYED` is the display contract `_interpret` also enforces."""
    candidates = [_candidate(issue_id=100 + i) for i in range(12)]
    lines = prompt._build_lines(ComicProfile(), candidates, None, terse=True)
    numbered = [line for line in lines if line.strip()[:2].rstrip(".").isdigit()]
    assert len(numbered) == prompt._MAX_DISPLAYED
    assert numbered[-1].strip().startswith("9.")
    assert not any("[metron:110]" in line for line in lines)


# --- _interpret -------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("s", ("skip", None)),
        ("skip", ("skip", None)),
        ("q", ("abort", None)),
        ("quit", ("abort", None)),
        ("abort", ("abort", None)),
        ("m", ("manual", "")),
        ("manual", ("manual", "")),
    ],
)
def test_interpret_word_aliases(raw: str, expected: tuple) -> None:
    assert prompt._interpret(raw, 3) == expected


@pytest.mark.parametrize("raw", ["o", "options", "  OPTIONS  "])
def test_interpret_options_sentinel(raw: str) -> None:
    assert prompt._interpret(raw, 3) == prompt._OPTIONS_SENTINEL


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("S", ("skip", None)), (" s ", ("skip", None)), ("\tQ\n", ("abort", None))],
)
def test_interpret_strips_and_lowercases(raw: str, expected: tuple) -> None:
    assert prompt._interpret(raw, 3) == expected


@pytest.mark.parametrize(("raw", "index"), [("1", 0), ("2", 1), ("3", 2)])
def test_interpret_digits_in_range(raw: str, index: int) -> None:
    assert prompt._interpret(raw, 3) == ("choose", index)


@pytest.mark.parametrize("raw", ["0", "4", "10", "99"])
def test_interpret_digits_out_of_range(raw: str) -> None:
    """An out-of-range index is a typo, not a from-the-end lookup."""
    assert prompt._interpret(raw, 3) is None


@pytest.mark.parametrize("raw", ["", "   ", "\t\n"])
def test_interpret_empty_input(raw: str) -> None:
    assert prompt._interpret(raw, 3) is None


@pytest.mark.parametrize("raw", ["x", "yes", "-1", "1.5", "1a", "sq"])
def test_interpret_unrecognized_input(raw: str) -> None:
    assert prompt._interpret(raw, 3) is None


# --- _read_input / _ask_manual_id -------------------------------------------


def test_read_input_returns_the_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _message: "  typed  ")
    assert prompt._read_input("> ") == "  typed  "


def test_read_input_treats_eof_as_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """A closed stdin must not blow up a batch run."""

    def _raise(_message: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", _raise)
    assert prompt._read_input("> ") == ""


def test_ask_manual_id_qualifies_a_bare_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompt, "_read_input", lambda _message: " 4242 ")
    assert prompt._ask_manual_id("metron") == "metron:4242"


def test_ask_manual_id_keeps_an_explicit_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prompt, "_read_input", lambda _message: "comicvine:9")
    assert prompt._ask_manual_id("metron") == "comicvine:9"


def test_ask_manual_id_empty_backs_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompt, "_read_input", lambda _message: "   ")
    assert prompt._ask_manual_id("metron") is None


# --- _resolve_policy_input --------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1", "ask"), ("2", "careful"), ("3", "auto"), ("4", "eager")],
)
def test_resolve_policy_input_by_key(raw: str, expected: str) -> None:
    key_to_name = dict(prompt._POLICY_CHOICES)
    assert prompt._resolve_policy_input(raw, key_to_name=key_to_name) == expected


@pytest.mark.parametrize("name", ["ask", "careful", "auto", "eager"])
def test_resolve_policy_input_by_name(name: str) -> None:
    key_to_name = dict(prompt._POLICY_CHOICES)
    assert prompt._resolve_policy_input(name, key_to_name=key_to_name) == name


@pytest.mark.parametrize("raw", ["", "5", "0", "nonsense", "Ask"])
def test_resolve_policy_input_unrecognized(raw: str) -> None:
    """Inputs arrive pre-lowercased; anything else is unrecognized."""
    key_to_name = dict(prompt._POLICY_CHOICES)
    assert prompt._resolve_policy_input(raw, key_to_name=key_to_name) is None


def test_policy_menu_lists_every_choice_and_back() -> None:
    lines = prompt._build_policy_lines()
    for key, name in prompt._POLICY_CHOICES:
        assert f"    {key}. {name}" in lines
    assert lines[-1] == "    b. Back"


def test_options_menu_lists_unattended_policy_and_back() -> None:
    text = "\n".join(prompt._build_options_lines())
    assert "u. Unattended" in text
    assert "p. Change match policy" in text
    assert "b. Back" in text


# --- _handle_manual_result --------------------------------------------------


def test_handle_manual_result_passes_other_actions_through() -> None:
    assert prompt._handle_manual_result(("skip", None), "metron") == ("skip", None)


def test_handle_manual_result_passes_a_filled_manual_through() -> None:
    result = ("manual", "metron:5")
    assert prompt._handle_manual_result(result, "metron") == result


def test_handle_manual_result_prompts_for_an_empty_manual(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prompt, "_read_input", lambda _message: "7")
    assert prompt._handle_manual_result(("manual", ""), "metron") == (
        "manual",
        "metron:7",
    )


def test_handle_manual_result_none_when_the_user_backs_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty id means "never mind" — the caller re-prompts, not skips."""
    monkeypatch.setattr(prompt, "_read_input", lambda _message: "")
    assert prompt._handle_manual_result(("manual", ""), "metron") is None


# --- _prompt_line -----------------------------------------------------------


class _FakeQuestionary:
    """Minimal `questionary` stand-in: `.text(msg).ask()`."""

    def __init__(
        self, result: str | None = None, exc: BaseException | None = None
    ) -> None:
        self.result = result
        self.exc = exc
        self.messages: list[str] = []

    def text(self, message: str) -> _FakeQuestionary:
        self.messages.append(message)
        return self

    def ask(self) -> str | None:
        if self.exc is not None:
            raise self.exc
        return self.result


def _use_tty(monkeypatch: pytest.MonkeyPatch, fake: object) -> None:
    monkeypatch.setattr(prompt, "_is_tty", lambda: True)
    monkeypatch.setitem(sys.modules, "questionary", fake)


def test_prompt_line_falls_back_to_input_off_tty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []
    monkeypatch.setattr(prompt, "_is_tty", lambda: False)
    monkeypatch.setattr(
        prompt, "_read_input", lambda message: seen.append(message) or "s"
    )
    assert prompt._prompt_line("Choose:") == "s"
    assert seen == ["Choose: "]


def test_prompt_line_uses_questionary_on_a_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeQuestionary(result="2")
    _use_tty(monkeypatch, fake)
    assert prompt._prompt_line("Choose:") == "2"
    assert fake.messages == ["Choose:"]


def test_prompt_line_missing_questionary_aborts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`None` in sys.modules makes `import questionary` raise ImportError."""
    _use_tty(monkeypatch, None)
    assert prompt._prompt_line("Choose:") is None


def test_prompt_line_ctrl_c_aborts(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_tty(monkeypatch, _FakeQuestionary(exc=KeyboardInterrupt()))
    assert prompt._prompt_line("Choose:") is None


def test_prompt_line_questionary_ask_returning_none_aborts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Questionary returns None on its own Ctrl-C handling; that's an abort."""
    _use_tty(monkeypatch, _FakeQuestionary(result=None))
    assert prompt._prompt_line("Choose:") is None


def test_prompt_line_other_questionary_errors_propagate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Documents the current (narrow) except clause.

    `_prompt_line` catches only ImportError and KeyboardInterrupt. Any
    other questionary failure — a terminal that can't be put into raw
    mode, for instance — escapes the selector and, because nothing
    between here and `Runner._run_one` catches it, ends the run with a
    traceback instead of degrading to the plain `input()` fallback.
    """
    _use_tty(monkeypatch, _FakeQuestionary(exc=RuntimeError("no tty control")))
    with pytest.raises(RuntimeError):
        prompt._prompt_line("Choose:")


def test_is_tty_reflects_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Stdin:
        def __init__(self, tty: bool) -> None:
            self._tty = tty

        def isatty(self) -> bool:
            return self._tty

    monkeypatch.setattr(sys, "stdin", _Stdin(tty=True))
    assert prompt._is_tty() is True
    monkeypatch.setattr(sys, "stdin", _Stdin(tty=False))
    assert prompt._is_tty() is False
    monkeypatch.setattr(sys, "stdin", None)
    assert prompt._is_tty() is False


# --- _ask_policy_choice -----------------------------------------------------


@pytest.mark.parametrize(
    ("reply", "policy"),
    [("1", "ask"), ("2", "careful"), ("3", "auto"), ("4", "eager"), ("eager", "eager")],
)
def test_ask_policy_choice_returns_set_policy(
    monkeypatch: pytest.MonkeyPatch, reply: str, policy: str
) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", _ScriptedPrompt(reply))
    assert prompt._ask_policy_choice() == ("set_policy", policy)


@pytest.mark.parametrize("reply", ["b", "back", "", "  "])
def test_ask_policy_choice_back_returns_none(
    monkeypatch: pytest.MonkeyPatch, reply: str
) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", _ScriptedPrompt(reply))
    assert prompt._ask_policy_choice() is None


def test_ask_policy_choice_reprompts_on_garbage(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unrecognized input loops instead of escaping the submenu."""
    scripted = _ScriptedPrompt("9", "zzz", "2")
    monkeypatch.setattr(prompt, "_prompt_line", scripted)
    assert prompt._ask_policy_choice() == ("set_policy", "careful")
    assert len(scripted.messages) == 3
    out = capsys.readouterr().out
    assert out.count("unrecognized") == 2


def test_ask_policy_choice_none_reply_aborts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", _ScriptedPrompt(None))
    assert prompt._ask_policy_choice() == ("abort", None)


# --- _ask_session_options ---------------------------------------------------


@pytest.mark.parametrize("reply", ["u", "unattended", "U"])
def test_ask_session_options_unattended(
    monkeypatch: pytest.MonkeyPatch, reply: str
) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", _ScriptedPrompt(reply))
    assert prompt._ask_session_options() == ("set_unattended", None)


@pytest.mark.parametrize("reply", ["p", "policy"])
def test_ask_session_options_descends_into_policy(
    monkeypatch: pytest.MonkeyPatch, reply: str
) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", _ScriptedPrompt(reply, "4"))
    assert prompt._ask_session_options() == ("set_policy", "eager")


def test_ask_session_options_policy_back_unwinds_one_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`b` in the policy submenu returns to session options, not the top."""
    scripted = _ScriptedPrompt("p", "b", "u")
    monkeypatch.setattr(prompt, "_prompt_line", scripted)
    assert prompt._ask_session_options() == ("set_unattended", None)
    assert scripted.messages == ["Option:", "Policy:", "Option:"]


@pytest.mark.parametrize("reply", ["b", "back", ""])
def test_ask_session_options_back_returns_none(
    monkeypatch: pytest.MonkeyPatch, reply: str
) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", _ScriptedPrompt(reply))
    assert prompt._ask_session_options() is None


def test_ask_session_options_reprompts_on_garbage(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scripted = _ScriptedPrompt("nope", "u")
    monkeypatch.setattr(prompt, "_prompt_line", scripted)
    assert prompt._ask_session_options() == ("set_unattended", None)
    assert len(scripted.messages) == 2
    assert "unrecognized: 'nope'" in capsys.readouterr().out


def test_ask_session_options_none_reply_aborts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", _ScriptedPrompt(None))
    assert prompt._ask_session_options() == ("abort", None)


def test_ask_session_options_abort_propagates_out_of_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A None reply inside the policy submenu aborts the whole run."""
    monkeypatch.setattr(prompt, "_prompt_line", _ScriptedPrompt("p", None))
    assert prompt._ask_session_options() == ("abort", None)


# --- _resolve_cli_selector_input --------------------------------------------


def test_resolve_cli_selector_input_choose() -> None:
    candidates = [_candidate(101), _candidate(102)]
    assert prompt._resolve_cli_selector_input("2", candidates, "metron") == (
        "choose",
        1,
    )


def test_resolve_cli_selector_input_caps_index_at_the_display_limit() -> None:
    """A 12-candidate list still only accepts 1-9 — what was printed."""
    candidates = [_candidate(100 + i) for i in range(12)]
    assert prompt._resolve_cli_selector_input("9", candidates, "metron") == (
        "choose",
        8,
    )
    assert prompt._resolve_cli_selector_input("10", candidates, "metron") is None


def test_resolve_cli_selector_input_unrecognized_reports_and_reprompts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert prompt._resolve_cli_selector_input("zzz", [_candidate()], "metron") is None
    assert "unrecognized: 'zzz'" in capsys.readouterr().out


def test_resolve_cli_selector_input_options_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", _ScriptedPrompt("u"))
    result = prompt._resolve_cli_selector_input("o", [_candidate()], "metron")
    assert result == ("set_unattended", None)


def test_resolve_cli_selector_input_options_back_reprompts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backing out of the submenu returns None so the top level re-prompts."""
    monkeypatch.setattr(prompt, "_prompt_line", _ScriptedPrompt("b"))
    assert prompt._resolve_cli_selector_input("o", [_candidate()], "metron") is None


def test_resolve_cli_selector_input_manual(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompt, "_read_input", lambda _message: "88")
    result = prompt._resolve_cli_selector_input("m", [_candidate()], "metron")
    assert result == ("manual", "metron:88")


# --- cli_selector -----------------------------------------------------------


def test_cli_selector_choose(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", _ScriptedPrompt("2"))
    candidates = [_candidate(101), _candidate(102)]
    result = prompt.cli_selector(ComicProfile(series="Foo"), candidates, _ctx())
    assert result == ("choose", 1)


@pytest.mark.parametrize(
    ("reply", "expected"),
    [("s", ("skip", None)), ("q", ("abort", None))],
)
def test_cli_selector_terminal_replies(
    monkeypatch: pytest.MonkeyPatch, reply: str, expected: tuple
) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", _ScriptedPrompt(reply))
    result = prompt.cli_selector(ComicProfile(), [_candidate()], _ctx())
    assert result == expected


def test_cli_selector_none_reply_aborts(monkeypatch: pytest.MonkeyPatch) -> None:
    """EOF / Ctrl-C at the top-level prompt aborts the run, never skips."""
    monkeypatch.setattr(prompt, "_prompt_line", _ScriptedPrompt(None))
    result = prompt.cli_selector(ComicProfile(), [_candidate()], _ctx())
    assert result == ("abort", None)


def test_cli_selector_reprompts_instead_of_escaping(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Garbage never falls out of the loop as an accidental skip."""
    scripted = _ScriptedPrompt("zzz", "", "0", "1")
    monkeypatch.setattr(prompt, "_prompt_line", scripted)
    result = prompt.cli_selector(ComicProfile(), [_candidate()], _ctx())
    assert result == ("choose", 0)
    assert len(scripted.messages) == 4
    out = capsys.readouterr().out
    # The menu is redrawn for every re-prompt.
    assert out.count("q. Abort entire run") == 4


def test_cli_selector_manual_backout_reprompts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty manual id returns to the menu rather than skipping the file."""
    scripted = _ScriptedPrompt("m", "s")
    monkeypatch.setattr(prompt, "_prompt_line", scripted)
    monkeypatch.setattr(prompt, "_read_input", lambda _message: "")
    result = prompt.cli_selector(ComicProfile(), [_candidate()], _ctx())
    assert result == ("skip", None)
    assert len(scripted.messages) == 2


def test_cli_selector_options_back_reprompts(monkeypatch: pytest.MonkeyPatch) -> None:
    scripted = _ScriptedPrompt("o", "b", "s")
    monkeypatch.setattr(prompt, "_prompt_line", scripted)
    result = prompt.cli_selector(ComicProfile(), [_candidate()], _ctx())
    assert result == ("skip", None)
    assert scripted.messages == ["Choose:", "Option:", "Choose:"]


def test_cli_selector_options_sets_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", _ScriptedPrompt("o", "p", "2"))
    result = prompt.cli_selector(ComicProfile(), [_candidate()], _ctx())
    assert result == ("set_policy", "careful")


def test_cli_selector_renders_the_file_path_and_candidates(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", _ScriptedPrompt("s"))
    profile = ComicProfile(series="Foo Comics", issue="5", year=2020)
    candidates = [_candidate(101, url="https://example.test/1"), _candidate(102)]
    prompt.cli_selector(profile, candidates, _ctx(file_path="/comics/foo.cbz"))
    out = capsys.readouterr().out
    assert "Ambiguous match for /comics/foo.cbz" in out
    assert "Existing: series='Foo Comics'" in out
    assert "1. Foo Comics #5 (2020)" in out
    assert "https://example.test/1" in out


def test_cli_selector_terse_trims_aux_lines(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A quieted run keeps the numbered choices and drops the chrome."""
    monkeypatch.setattr(prompt, "_prompt_line", _ScriptedPrompt("s"))
    ctx = _ctx(settings=_settings("WARNING"))
    prompt.cli_selector(ComicProfile(), [_candidate(url="https://example.test/1")], ctx)
    out = capsys.readouterr().out
    assert "1. Foo Comics #5" in out
    assert "publisher=" not in out
    assert "example.test" not in out


def test_cli_selector_verbose_by_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", _ScriptedPrompt("s"))
    prompt.cli_selector(
        ComicProfile(), [_candidate(url="https://example.test/1")], _ctx()
    )
    out = capsys.readouterr().out
    assert "publisher=" in out
    assert "example.test" in out


# --- _resolve_terse ---------------------------------------------------------


@pytest.mark.parametrize("loglevel", ["SUCCESS", "WARNING", "ERROR", "CRITICAL", 30])
def test_resolve_terse_engages_above_info(loglevel: str | int) -> None:
    assert prompt._resolve_terse(_settings(loglevel)) is True


@pytest.mark.parametrize("loglevel", ["INFO", "DEBUG", "TRACE", "info", 10])
def test_resolve_terse_stays_off_at_or_below_info(loglevel: str | int) -> None:
    assert prompt._resolve_terse(_settings(loglevel)) is False


def test_resolve_terse_ignores_an_unknown_level() -> None:
    """A bad `--loglevel` is the logger's problem to report, not ours."""
    assert prompt._resolve_terse(_settings("NONSENSE")) is False


# --- terse against the real config ------------------------------------------


def _settings_for(*argv: str) -> ComicboxSettings:
    """Resolve settings the way the CLI does, `-Q` folding included."""
    from comicbox.cli import get_args

    return get_config(Namespace(comicbox=get_args(("comicbox", *argv))))


def test_real_config_default_is_verbose() -> None:
    assert prompt._resolve_terse(_settings_for("x.cbz")) is False


def test_real_config_double_quiet_is_terse() -> None:
    """`-QQ` resolves to SUCCESS, the first level that means "less"."""
    assert prompt._resolve_terse(_settings_for("-QQ", "x.cbz")) is True


def test_real_config_single_quiet_changes_nothing() -> None:
    """
    Documents `-Q`'s no-op first level.

    `comicbox.cli._QUIET_LOGLEVEL` maps one `-Q` to INFO, which is
    already `config_default.yaml`'s level, so a single `-Q` neither
    quiets the log nor trims the prompt. Two Qs is where it starts.
    """
    assert prompt._resolve_terse(_settings_for("-Q", "x.cbz")) is False


def test_real_config_yaml_loglevel_is_terse() -> None:
    """`loglevel` is a config-file key; `-Q` is just its CLI shorthand."""
    assert prompt._resolve_terse(_settings("WARNING")) is True


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
