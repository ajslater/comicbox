"""
CLI selector loop tests — `comicbox.formats.base.online.prompt`.

The interactive half: the questionary/`input` line reader, the policy and
session-option submenus, and the `cli_selector` loop that ties them
together. Every loop is driven by monkeypatching `_prompt_line` and
`_read_input` with scripted reply sequences. The pure rendering and reply
grammar are in ``test_online_prompt``.
"""

from __future__ import annotations

import sys

import pytest

from comicbox.formats.base.online import prompt
from comicbox.formats.base.online.profile import ComicProfile
from tests.util.online_prompt import (
    ScriptedPrompt,
    make_candidate,
    make_context,
    make_settings,
)


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
    monkeypatch.setattr(prompt, "_prompt_line", ScriptedPrompt(reply))
    assert prompt._ask_policy_choice() == ("set_policy", policy)


@pytest.mark.parametrize("reply", ["b", "back", "", "  "])
def test_ask_policy_choice_back_returns_none(
    monkeypatch: pytest.MonkeyPatch, reply: str
) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", ScriptedPrompt(reply))
    assert prompt._ask_policy_choice() is None


def test_ask_policy_choice_reprompts_on_garbage(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unrecognized input loops instead of escaping the submenu."""
    scripted = ScriptedPrompt("9", "zzz", "2")
    monkeypatch.setattr(prompt, "_prompt_line", scripted)
    assert prompt._ask_policy_choice() == ("set_policy", "careful")
    assert len(scripted.messages) == 3
    out = capsys.readouterr().out
    assert out.count("unrecognized") == 2


def test_ask_policy_choice_none_reply_aborts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", ScriptedPrompt(None))
    assert prompt._ask_policy_choice() == ("abort", None)


# --- _ask_session_options ---------------------------------------------------


@pytest.mark.parametrize("reply", ["u", "unattended", "U"])
def test_ask_session_options_unattended(
    monkeypatch: pytest.MonkeyPatch, reply: str
) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", ScriptedPrompt(reply))
    assert prompt._ask_session_options() == ("set_unattended", None)


@pytest.mark.parametrize("reply", ["p", "policy"])
def test_ask_session_options_descends_into_policy(
    monkeypatch: pytest.MonkeyPatch, reply: str
) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", ScriptedPrompt(reply, "4"))
    assert prompt._ask_session_options() == ("set_policy", "eager")


def test_ask_session_options_policy_back_unwinds_one_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`b` in the policy submenu returns to session options, not the top."""
    scripted = ScriptedPrompt("p", "b", "u")
    monkeypatch.setattr(prompt, "_prompt_line", scripted)
    assert prompt._ask_session_options() == ("set_unattended", None)
    assert scripted.messages == ["Option:", "Policy:", "Option:"]


@pytest.mark.parametrize("reply", ["b", "back", ""])
def test_ask_session_options_back_returns_none(
    monkeypatch: pytest.MonkeyPatch, reply: str
) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", ScriptedPrompt(reply))
    assert prompt._ask_session_options() is None


def test_ask_session_options_reprompts_on_garbage(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    scripted = ScriptedPrompt("nope", "u")
    monkeypatch.setattr(prompt, "_prompt_line", scripted)
    assert prompt._ask_session_options() == ("set_unattended", None)
    assert len(scripted.messages) == 2
    assert "unrecognized: 'nope'" in capsys.readouterr().out


def test_ask_session_options_none_reply_aborts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", ScriptedPrompt(None))
    assert prompt._ask_session_options() == ("abort", None)


def test_ask_session_options_abort_propagates_out_of_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A None reply inside the policy submenu aborts the whole run."""
    monkeypatch.setattr(prompt, "_prompt_line", ScriptedPrompt("p", None))
    assert prompt._ask_session_options() == ("abort", None)


# --- _resolve_cli_selector_input --------------------------------------------


def test_resolve_cli_selector_input_choose() -> None:
    candidates = [make_candidate(101), make_candidate(102)]
    assert prompt._resolve_cli_selector_input("2", candidates, "metron") == (
        "choose",
        1,
    )


def test_resolve_cli_selector_input_caps_index_at_the_display_limit() -> None:
    """A 12-candidate list still only accepts 1-9 — what was printed."""
    candidates = [make_candidate(100 + i) for i in range(12)]
    assert prompt._resolve_cli_selector_input("9", candidates, "metron") == (
        "choose",
        8,
    )
    assert prompt._resolve_cli_selector_input("10", candidates, "metron") is None


def test_resolve_cli_selector_input_unrecognized_reports_and_reprompts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        prompt._resolve_cli_selector_input("zzz", [make_candidate()], "metron") is None
    )
    assert "unrecognized: 'zzz'" in capsys.readouterr().out


def test_resolve_cli_selector_input_options_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", ScriptedPrompt("u"))
    result = prompt._resolve_cli_selector_input("o", [make_candidate()], "metron")
    assert result == ("set_unattended", None)


def test_resolve_cli_selector_input_options_back_reprompts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backing out of the submenu returns None so the top level re-prompts."""
    monkeypatch.setattr(prompt, "_prompt_line", ScriptedPrompt("b"))
    assert prompt._resolve_cli_selector_input("o", [make_candidate()], "metron") is None


def test_resolve_cli_selector_input_manual(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompt, "_read_input", lambda _message: "88")
    result = prompt._resolve_cli_selector_input("m", [make_candidate()], "metron")
    assert result == ("manual", "metron:88")


# --- cli_selector -----------------------------------------------------------


def test_cli_selector_choose(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", ScriptedPrompt("2"))
    candidates = [make_candidate(101), make_candidate(102)]
    result = prompt.cli_selector(ComicProfile(series="Foo"), candidates, make_context())
    assert result == ("choose", 1)


@pytest.mark.parametrize(
    ("reply", "expected"),
    [("s", ("skip", None)), ("q", ("abort", None))],
)
def test_cli_selector_terminal_replies(
    monkeypatch: pytest.MonkeyPatch, reply: str, expected: tuple
) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", ScriptedPrompt(reply))
    result = prompt.cli_selector(ComicProfile(), [make_candidate()], make_context())
    assert result == expected


def test_cli_selector_none_reply_aborts(monkeypatch: pytest.MonkeyPatch) -> None:
    """EOF / Ctrl-C at the top-level prompt aborts the run, never skips."""
    monkeypatch.setattr(prompt, "_prompt_line", ScriptedPrompt(None))
    result = prompt.cli_selector(ComicProfile(), [make_candidate()], make_context())
    assert result == ("abort", None)


def test_cli_selector_reprompts_instead_of_escaping(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Garbage never falls out of the loop as an accidental skip."""
    scripted = ScriptedPrompt("zzz", "", "0", "1")
    monkeypatch.setattr(prompt, "_prompt_line", scripted)
    result = prompt.cli_selector(ComicProfile(), [make_candidate()], make_context())
    assert result == ("choose", 0)
    assert len(scripted.messages) == 4
    out = capsys.readouterr().out
    # The menu is redrawn for every re-prompt.
    assert out.count("q. Abort entire run") == 4


def test_cli_selector_manual_backout_reprompts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty manual id returns to the menu rather than skipping the file."""
    scripted = ScriptedPrompt("m", "s")
    monkeypatch.setattr(prompt, "_prompt_line", scripted)
    monkeypatch.setattr(prompt, "_read_input", lambda _message: "")
    result = prompt.cli_selector(ComicProfile(), [make_candidate()], make_context())
    assert result == ("skip", None)
    assert len(scripted.messages) == 2


def test_cli_selector_options_back_reprompts(monkeypatch: pytest.MonkeyPatch) -> None:
    scripted = ScriptedPrompt("o", "b", "s")
    monkeypatch.setattr(prompt, "_prompt_line", scripted)
    result = prompt.cli_selector(ComicProfile(), [make_candidate()], make_context())
    assert result == ("skip", None)
    assert scripted.messages == ["Choose:", "Option:", "Choose:"]


def test_cli_selector_options_sets_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", ScriptedPrompt("o", "p", "2"))
    result = prompt.cli_selector(ComicProfile(), [make_candidate()], make_context())
    assert result == ("set_policy", "careful")


def test_cli_selector_renders_the_file_path_and_candidates(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", ScriptedPrompt("s"))
    profile = ComicProfile(series="Foo Comics", issue="5", year=2020)
    candidates = [
        make_candidate(101, url="https://example.test/1"),
        make_candidate(102),
    ]
    prompt.cli_selector(profile, candidates, make_context(file_path="/comics/foo.cbz"))
    out = capsys.readouterr().out
    assert "Ambiguous match for /comics/foo.cbz" in out
    assert "Existing: series='Foo Comics'" in out
    assert "1. Foo Comics #5 (2020)" in out
    assert "https://example.test/1" in out


def test_cli_selector_terse_trims_aux_lines(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A quieted run keeps the numbered choices and drops the chrome."""
    monkeypatch.setattr(prompt, "_prompt_line", ScriptedPrompt("s"))
    ctx = make_context(settings=make_settings("WARNING"))
    prompt.cli_selector(
        ComicProfile(), [make_candidate(url="https://example.test/1")], ctx
    )
    out = capsys.readouterr().out
    assert "1. Foo Comics #5" in out
    assert "publisher=" not in out
    assert "example.test" not in out


def test_cli_selector_verbose_by_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(prompt, "_prompt_line", ScriptedPrompt("s"))
    prompt.cli_selector(
        ComicProfile(), [make_candidate(url="https://example.test/1")], make_context()
    )
    out = capsys.readouterr().out
    assert "publisher=" in out
    assert "example.test" in out
