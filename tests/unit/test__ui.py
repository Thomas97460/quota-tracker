"""Tests for the _ui TTY helper module."""

from __future__ import annotations

import shutil
import sys

import quota_tracker._ui as ui


# ── Helpers ────────────────────────────────────────────────────────────────────


def _force_tty(monkeypatch) -> None:
    """Make _is_tty() return True regardless of actual TTY state."""
    monkeypatch.setattr(ui, "_is_tty", lambda: True)


def _force_no_tty(monkeypatch) -> None:
    """Make _is_tty() return False (plain text mode)."""
    monkeypatch.setattr(ui, "_is_tty", lambda: False)


# ── Color helpers ─────────────────────────────────────────────────────────────


def test_color_helpers_plain(monkeypatch) -> None:
    _force_no_tty(monkeypatch)
    assert ui.cyan("x") == "x"
    assert ui.violet("x") == "x"
    assert ui.bold("x") == "x"
    assert ui.dim("x") == "x"
    assert ui.success("x") == "x"
    assert ui.warn("x") == "x"
    assert ui.error("x") == "x"


def test_color_helpers_tty(monkeypatch) -> None:
    _force_tty(monkeypatch)
    assert "\033[" in ui.cyan("x")
    assert "\033[" in ui.violet("x")
    assert "\033[" in ui.bold("x")
    assert "\033[" in ui.dim("x")
    assert "\033[" in ui.success("x")
    assert "\033[" in ui.warn("x")
    assert "\033[" in ui.error("x")
    # all must reset at the end
    assert ui.cyan("x").endswith("\033[0m")


# ── banner ────────────────────────────────────────────────────────────────────


def test_banner_plain(monkeypatch, capsys) -> None:
    _force_no_tty(monkeypatch)
    ui.banner()
    out = capsys.readouterr().out
    assert ui.WORDMARK in out
    assert ui.TAGLINE in out
    assert ui.MARK in out


def test_banner_tty(monkeypatch, capsys) -> None:
    _force_tty(monkeypatch)
    ui.banner()
    out = capsys.readouterr().out
    # The wordmark letters are per-char gradient-colored, so check the key
    # substring appears (in plain fallback) or ANSI is present (truecolor path)
    assert ui.TAGLINE in out
    assert "\033[" in out


# ── step / section / kv ───────────────────────────────────────────────────────


def test_step_plain(monkeypatch, capsys) -> None:
    _force_no_tty(monkeypatch)
    ui.step(2, 4, "Configure providers")
    out = capsys.readouterr().out
    assert "[2/4]" in out
    assert "Configure providers" in out


def test_section(monkeypatch, capsys) -> None:
    _force_no_tty(monkeypatch)
    ui.section("Providers")
    out = capsys.readouterr().out
    assert "Providers" in out
    assert "─" in out


def test_section_tty(monkeypatch, capsys) -> None:
    _force_tty(monkeypatch)
    ui.section("Providers")
    out = capsys.readouterr().out
    assert "Providers" in out


def test_kv_plain(monkeypatch, capsys) -> None:
    _force_no_tty(monkeypatch)
    ui.kv("host", "127.0.0.1")
    out = capsys.readouterr().out
    assert "host" in out
    assert "127.0.0.1" in out


def test_kv_tty(monkeypatch, capsys) -> None:
    _force_tty(monkeypatch)
    ui.kv("host", "127.0.0.1")
    out = capsys.readouterr().out
    assert "host" in out
    assert "127.0.0.1" in out


# ── prompt ────────────────────────────────────────────────────────────────────


def test_prompt_default_plain(monkeypatch, capsys) -> None:
    _force_no_tty(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda _: "")
    result = ui.prompt("Enter value", default="mydefault")
    assert result == "mydefault"


def test_prompt_override_plain(monkeypatch) -> None:
    monkeypatch.setattr(ui, "_is_tty", lambda: False)
    monkeypatch.setattr("builtins.input", lambda _: "custom")
    result = ui.prompt("Enter value", default="mydefault")
    assert result == "custom"


def test_prompt_placeholder(monkeypatch, capsys) -> None:
    _force_no_tty(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda p: "")
    result = ui.prompt("Enter value", placeholder="e.g. foo")
    # No default means empty string fallback
    assert result == ""
    out = capsys.readouterr()  # just ensure no crash


def test_prompt_placeholder_tty(monkeypatch, capsys) -> None:
    _force_tty(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda p: "typed")
    result = ui.prompt("Enter value", placeholder="e.g. foo")
    assert result == "typed"


def test_prompt_tty_with_default(monkeypatch) -> None:
    _force_tty(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda _: "")
    result = ui.prompt("Question", default="val")
    assert result == "val"


# ── confirm ───────────────────────────────────────────────────────────────────


def test_confirm_default_yes(monkeypatch) -> None:
    _force_no_tty(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert ui.confirm("OK?", default=True) is True


def test_confirm_default_no(monkeypatch) -> None:
    _force_no_tty(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert ui.confirm("OK?", default=False) is False


def test_confirm_explicit_n(monkeypatch) -> None:
    _force_no_tty(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert ui.confirm("OK?", default=True) is False


def test_confirm_invalid_falls_back(monkeypatch) -> None:
    _force_no_tty(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda _: "blah")
    assert ui.confirm("OK?", default=True) is True


def test_confirm_tty(monkeypatch) -> None:
    _force_tty(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda _: "y")
    assert ui.confirm("OK?", default=False) is True


def test_confirm_tty_empty(monkeypatch) -> None:
    _force_tty(monkeypatch)
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert ui.confirm("OK?", default=True) is True


# ── box ───────────────────────────────────────────────────────────────────────


def test_box_plain(monkeypatch, capsys) -> None:
    _force_no_tty(monkeypatch)
    ui.box(["line one", "line two"], title="Summary")
    out = capsys.readouterr().out
    assert "Summary" in out
    assert "line one" in out
    assert "╭" in out
    assert "╰" in out


def test_box_tty(monkeypatch, capsys) -> None:
    _force_tty(monkeypatch)
    ui.box(["alpha", "beta"])
    out = capsys.readouterr().out
    assert "alpha" in out
    assert "\033[" in out


def test_box_empty(monkeypatch, capsys) -> None:
    _force_no_tty(monkeypatch)
    ui.box([])
    out = capsys.readouterr().out
    assert "╭" in out


# ── status marks ─────────────────────────────────────────────────────────────


def test_success_check_plain(monkeypatch, capsys) -> None:
    _force_no_tty(monkeypatch)
    ui.success_check("all good")
    out = capsys.readouterr().out
    assert "[ok]" in out
    assert "all good" in out


def test_warn_mark_plain(monkeypatch, capsys) -> None:
    _force_no_tty(monkeypatch)
    ui.warn_mark("watch out")
    out = capsys.readouterr().out
    assert "[!]" in out
    assert "watch out" in out


def test_error_mark_plain(monkeypatch, capsys) -> None:
    _force_no_tty(monkeypatch)
    ui.error_mark("failed")
    out = capsys.readouterr().out
    assert "[x]" in out
    assert "failed" in out


def test_success_check_tty(monkeypatch, capsys) -> None:
    _force_tty(monkeypatch)
    ui.success_check("done")
    out = capsys.readouterr().out
    assert "done" in out
    assert "\033[" in out


def test_warn_mark_tty(monkeypatch, capsys) -> None:
    _force_tty(monkeypatch)
    ui.warn_mark("caution")
    out = capsys.readouterr().out
    assert "caution" in out
    assert "\033[" in out


def test_error_mark_tty(monkeypatch, capsys) -> None:
    _force_tty(monkeypatch)
    ui.error_mark("oops")
    out = capsys.readouterr().out
    assert "oops" in out
    assert "\033[" in out


# ── NO_COLOR env var ──────────────────────────────────────────────────────────


def test_no_color_env_strips_ansi(monkeypatch) -> None:
    # Patch isatty to True but set NO_COLOR — should still strip color
    monkeypatch.setattr(ui.sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("NO_COLOR", "1")
    assert not ui._is_tty()
    assert ui.cyan("hello") == "hello"


# ── gradient ──────────────────────────────────────────────────────────────────


def test_gradient_plain_when_no_color(monkeypatch) -> None:
    """gradient() returns plain text when NO_COLOR is set."""
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(ui.sys.stdout, "isatty", lambda: True)
    result = ui.gradient("hello")
    assert result == "hello"
    assert "\033[" not in result


def test_gradient_plain_when_no_tty(monkeypatch) -> None:
    """gradient() returns plain text when stdout is not a TTY."""
    monkeypatch.setattr(ui.sys.stdout, "isatty", lambda: False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    result = ui.gradient("hello")
    assert result == "hello"


def test_gradient_truecolor(monkeypatch) -> None:
    """gradient() emits 24-bit ANSI escapes when COLORTERM=truecolor."""
    monkeypatch.setenv("COLORTERM", "truecolor")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(ui, "_is_tty", lambda: True)
    result = ui.gradient("hello")
    assert "\033[38;2;" in result
    assert result.endswith("\033[0m")


def test_gradient_truecolor_24bit(monkeypatch) -> None:
    """gradient() also accepts COLORTERM=24bit."""
    monkeypatch.setenv("COLORTERM", "24bit")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(ui, "_is_tty", lambda: True)
    result = ui.gradient("hi")
    assert "\033[38;2;" in result


def test_gradient_256color_fallback(monkeypatch) -> None:
    """gradient() falls back to alternating 256-color when no truecolor."""
    monkeypatch.delenv("COLORTERM", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(ui, "_is_tty", lambda: True)
    result = ui.gradient("ab")
    assert "\033[38;5;" in result
    assert "\033[38;2;" not in result


def test_gradient_empty_string(monkeypatch) -> None:
    """gradient() with empty text returns empty string without crash."""
    monkeypatch.setattr(ui, "_is_tty", lambda: True)
    assert ui.gradient("") == ""


def test_gradient_single_char(monkeypatch) -> None:
    """gradient() handles single-character text (avoids division by zero)."""
    monkeypatch.setenv("COLORTERM", "truecolor")
    monkeypatch.setattr(ui, "_is_tty", lambda: True)
    result = ui.gradient("x")
    assert "x" in result


# ── banner animate=False ──────────────────────────────────────────────────────


def test_banner_animate_false_no_cursor_escapes(monkeypatch, capsys) -> None:
    """banner(animate=False) produces deterministic output with no cursor movement."""
    _force_no_tty(monkeypatch)
    ui.banner(animate=False)
    out = capsys.readouterr().out
    assert ui.WORDMARK in out
    assert ui.TAGLINE in out
    # No carriage return / clear-line escape
    assert "\r" not in out
    assert "\033[K" not in out


def test_banner_animate_false_tty_no_cursor_escapes(monkeypatch, capsys) -> None:
    """banner(animate=False) with TTY still skips animation escape sequences."""
    _force_tty(monkeypatch)
    monkeypatch.setattr(ui, "_animation_disabled", lambda: False)
    ui.banner(animate=False)
    out = capsys.readouterr().out
    # Wordmark chars are gradient-wrapped; TAGLINE is plain
    assert ui.TAGLINE in out
    assert "\r" not in out
    assert "\033[K" not in out


# ── banner non-TTY no ANSI ────────────────────────────────────────────────────


def test_banner_non_tty_no_ansi(monkeypatch, capsys) -> None:
    """Banner with non-TTY stdout produces no ANSI color codes."""
    monkeypatch.setattr(ui.sys.stdout, "isatty", lambda: False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    ui.banner(animate=False)
    out = capsys.readouterr().out
    assert "\033[" not in out
    assert ui.WORDMARK in out
    assert ui.TAGLINE in out


# ── banner width fallback ─────────────────────────────────────────────────────


def test_banner_compact_small_width(monkeypatch, capsys) -> None:
    """When terminal width < 50, only the compact single-line form is printed."""
    _force_no_tty(monkeypatch)
    monkeypatch.setattr(shutil, "get_terminal_size", lambda _: shutil.os.terminal_size((40, 20)))
    ui.banner(animate=False)
    out = capsys.readouterr().out
    assert ui.WORDMARK in out
    assert ui.MARK_COMPACT in out
    # Tagline and separator must NOT appear in compact mode
    assert ui.TAGLINE not in out
    assert "═" not in out


def test_banner_full_wide_width(monkeypatch, capsys) -> None:
    """When terminal width >= 50, the full 3-line banner is printed."""
    _force_no_tty(monkeypatch)
    monkeypatch.setattr(shutil, "get_terminal_size", lambda _: shutil.os.terminal_size((80, 20)))
    ui.banner(animate=False)
    out = capsys.readouterr().out
    assert ui.WORDMARK in out
    assert ui.TAGLINE in out
    assert "═" in out


def test_banner_compact_tty(monkeypatch, capsys) -> None:
    """Compact form with TTY emits gradient colors and no tagline."""
    _force_tty(monkeypatch)
    monkeypatch.setattr(shutil, "get_terminal_size", lambda _: shutil.os.terminal_size((40, 20)))
    ui.banner(animate=False)
    out = capsys.readouterr().out
    # Should contain ANSI escapes (gradient applied to MARK_COMPACT)
    assert "\033[" in out
    # Tagline must not appear
    assert ui.TAGLINE not in out


# ── banner animation sequence ─────────────────────────────────────────────────


def test_banner_animation_frames(monkeypatch) -> None:
    """Animation writes GAUGE_SEGMENTS+1 frames via carriage-return + clear-line."""
    import io

    # Force a TTY-like context but suppress actual sleep
    monkeypatch.setattr(ui, "_is_tty", lambda: True)
    monkeypatch.setattr(ui, "_animation_disabled", lambda: False)
    monkeypatch.setattr(shutil, "get_terminal_size", lambda _: shutil.os.terminal_size((80, 20)))

    sleep_calls: list[float] = []
    monkeypatch.setattr(ui.time, "sleep", lambda s: sleep_calls.append(s))

    buf = io.StringIO()
    monkeypatch.setattr(ui.sys, "stdout", buf)

    ui.banner(animate=True)

    content = buf.getvalue()
    # Each intermediate frame starts with \r\033[K
    frame_count = content.count("\r\033[K")
    assert frame_count == ui.GAUGE_SEGMENTS + 1

    # sleep called GAUGE_SEGMENTS times (not after last frame)
    assert len(sleep_calls) == ui.GAUGE_SEGMENTS
    assert all(s == 0.025 for s in sleep_calls)


# ── _gauge_frame ──────────────────────────────────────────────────────────────


def test_gauge_frame_empty() -> None:
    assert ui._gauge_frame(0, 5) == "▱▱▱▱▱"


def test_gauge_frame_full() -> None:
    assert ui._gauge_frame(5, 5) == "▰▰▰▰▰"


def test_gauge_frame_partial() -> None:
    assert ui._gauge_frame(3, 5) == "▰▰▰▱▱"


# ── _supports_truecolor ───────────────────────────────────────────────────────


def test_supports_truecolor_true(monkeypatch) -> None:
    monkeypatch.setenv("COLORTERM", "truecolor")
    assert ui._supports_truecolor() is True


def test_supports_truecolor_24bit(monkeypatch) -> None:
    monkeypatch.setenv("COLORTERM", "24bit")
    assert ui._supports_truecolor() is True


def test_supports_truecolor_false(monkeypatch) -> None:
    monkeypatch.delenv("COLORTERM", raising=False)
    assert ui._supports_truecolor() is False


# ── _animation_disabled ───────────────────────────────────────────────────────


def test_animation_disabled_ci(monkeypatch) -> None:
    monkeypatch.setenv("CI", "true")
    monkeypatch.setattr(ui.sys.stdout, "isatty", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert ui._animation_disabled() is True


def test_animation_disabled_no_color(monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setattr(ui.sys.stdout, "isatty", lambda: True)
    monkeypatch.delenv("CI", raising=False)
    assert ui._animation_disabled() is True


def test_animation_enabled(monkeypatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(ui.sys.stdout, "isatty", lambda: True)
    assert ui._animation_disabled() is False
