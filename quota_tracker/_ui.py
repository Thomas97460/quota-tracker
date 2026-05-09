"""Thin TTY UI helper — ANSI colors, branded banner, layout primitives."""

from __future__ import annotations

import os
import shutil
import sys
import time

# ── Brand constants ────────────────────────────────────────────────────────────
# keep in sync with install.sh (BANNER variable)
MARK = "▰▰▰▰▰▰▰▰▰▰"
MARK_EMPTY = "▱▱▱▱▱▱▱▱▱▱"
MARK_COMPACT = "▰▰▰▰"
WORDMARK = "quota-tracker"
TAGLINE = "local-first quota & token observability"
GAUGE_SEGMENTS = 10

# Brand gradient: cyan → violet
_GRAD_START: tuple[int, int, int] = (0, 215, 215)
_GRAD_END: tuple[int, int, int] = (175, 135, 255)

BANNER_LINES = [
    f"  {MARK}  {WORDMARK}",
    "  ════════════════════════════════════════",
    f"  {TAGLINE}",
]

# ── Color palette ──────────────────────────────────────────────────────────────
# Primary: cyan (#00d7d7 → 256-color 44) + violet (#af87ff → 256-color 141)
# Semantic: green=ok, amber=warn, red=err, dim-grey=hints

_R = "\033[0m"           # reset
_BOLD = "\033[1m"
_DIM = "\033[2m"
_CYAN = "\033[38;5;44m"
_VIOLET = "\033[38;5;141m"
_GREEN = "\033[38;5;76m"
_AMBER = "\033[38;5;214m"
_RED = "\033[38;5;196m"
_GREY = "\033[38;5;245m"

# Icons — degrade to ASCII in non-TTY
_ICON_OK = "✔"
_ICON_WARN = "⚠"
_ICON_ERR = "✖"
_ICON_ARROW = "⟶"


def _is_tty() -> bool:
    """Return True when stdout is an interactive terminal and NO_COLOR is unset."""
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR", "")


def _supports_truecolor() -> bool:
    """Return True when the terminal advertises 24-bit color support."""
    return os.environ.get("COLORTERM", "") in ("truecolor", "24bit")


def _c(code: str, text: str) -> str:
    """Wrap text in ANSI escape code when TTY-enabled."""
    if _is_tty():
        return f"{code}{text}{_R}"
    return text


def cyan(s: str) -> str:
    """Apply primary cyan color."""
    return _c(_CYAN, s)


def violet(s: str) -> str:
    """Apply primary violet color."""
    return _c(_VIOLET, s)


def bold(s: str) -> str:
    """Apply bold weight."""
    return _c(_BOLD, s)


def dim(s: str) -> str:
    """Apply dim/muted style."""
    return _c(_DIM, s)


def success(s: str) -> str:
    """Apply green success color."""
    return _c(_GREEN, s)


def warn(s: str) -> str:
    """Apply amber warning color."""
    return _c(_AMBER, s)


def error(s: str) -> str:
    """Apply red error color."""
    return _c(_RED, s)


def gradient(text: str, start_rgb: tuple[int, int, int] = _GRAD_START,
             end_rgb: tuple[int, int, int] = _GRAD_END) -> str:
    """Per-character gradient: 24-bit truecolor if available, else alternating 256-color.

    Returns plain text when not a TTY or NO_COLOR is set.
    """
    if not _is_tty() or not text:
        return text
    n = len(text)
    if _supports_truecolor():
        parts: list[str] = []
        for i, ch in enumerate(text):
            t = i / max(n - 1, 1)
            r = round(start_rgb[0] + t * (end_rgb[0] - start_rgb[0]))
            g = round(start_rgb[1] + t * (end_rgb[1] - start_rgb[1]))
            b = round(start_rgb[2] + t * (end_rgb[2] - start_rgb[2]))
            parts.append(f"\033[38;2;{r};{g};{b}m{ch}")
        return "".join(parts) + _R
    # Alternate 256-color cyan/violet character by character
    parts2: list[str] = []
    for i, ch in enumerate(text):
        parts2.append(f"{(_CYAN if i % 2 == 0 else _VIOLET)}{ch}")
    return "".join(parts2) + _R


def _gauge_frame(filled: int, total: int) -> str:
    """Return a gauge string with `filled` filled segments out of `total`."""
    return "▰" * filled + "▱" * (total - filled)


def _animation_disabled() -> bool:
    return not sys.stdout.isatty() or bool(os.environ.get("NO_COLOR")) or bool(os.environ.get("CI"))


def banner(*, animate: bool = True) -> None:
    """Print the branded wordmark banner with optional gauge-fill animation."""
    tty = _is_tty()
    cols = shutil.get_terminal_size((80, 20)).columns
    compact = cols < 50

    # Build the gradient wordmark (bold + gradient)
    if tty:
        wordmark_rendered = f"{_BOLD}{gradient(WORDMARK)}{_R}"
    else:
        wordmark_rendered = WORDMARK

    should_animate = animate and tty and not _animation_disabled()

    print()

    if compact:
        # Single-line compact form — no animation, no tagline
        if tty:
            gauge = gradient(MARK_COMPACT)
            print(f"  {gauge}  {wordmark_rendered}")
        else:
            print(f"  {MARK_COMPACT}  {WORDMARK}")
        print()
        return

    # Full 3-line banner
    if should_animate:
        # Animate gauge fill: start empty, fill one segment at a time
        for filled in range(GAUGE_SEGMENTS + 1):
            gauge_str = _gauge_frame(filled, GAUGE_SEGMENTS)
            gauge_colored = gradient(gauge_str)  # tty is always True in animated path
            line = f"  {gauge_colored}  {wordmark_rendered}"
            sys.stdout.write(f"\r\033[K{line}")
            sys.stdout.flush()
            if filled < GAUGE_SEGMENTS:
                time.sleep(0.025)
        sys.stdout.write("\n")
        sys.stdout.flush()
    else:
        # Static final frame
        if tty:
            gauge_colored = gradient(MARK)
            print(f"  {gauge_colored}  {wordmark_rendered}")
        else:
            print(f"  {MARK}  {WORDMARK}")

    # Separator + tagline
    if tty:
        print(f"  {_CYAN}{'═' * 40}{_R}")
        print(f"  {_DIM}{TAGLINE}{_R}")
    else:
        print(f"  {'═' * 40}")
        print(f"  {TAGLINE}")

    print()


def step(n: int, total: int, label: str) -> None:
    """Print a numbered step header."""
    arrow = _ICON_ARROW
    counter = f"[{n}/{total}]"
    print(f"\n{cyan(arrow)} {bold(counter)} {label}")


def section(title: str) -> None:
    """Print an underlined section header."""
    print(f"\n  {bold(title)}")
    print(f"  {'─' * len(title)}")


def kv(label: str, value: str, width: int = 12) -> None:
    """Print a key-value pair with aligned columns."""
    padded = label.ljust(width)
    print(f"    {dim(padded)}  {value}")


def prompt(question: str, default: str | None = None, placeholder: str | None = None) -> str:
    """Display a colored prompt and return the stripped input."""
    hint = ""
    if default is not None:
        hint = f" {dim('[' + default + ']')}" if _is_tty() else f" [{default}]"
    elif placeholder is not None:
        hint = f" {dim('(' + placeholder + ')')}" if _is_tty() else f" ({placeholder})"

    display_q = cyan(question) if _is_tty() else question
    raw = input(f"    {display_q}{hint}: ").strip()
    return raw if raw else (default or "")


def confirm(question: str, default: bool = True) -> bool:
    """Display a y/n prompt and return bool."""
    choices = "Y/n" if default else "y/N"
    display_q = cyan(question) if _is_tty() else question
    hint = f" {dim('[' + choices + ']')}" if _is_tty() else f" [{choices}]"
    raw = input(f"    {display_q}{hint}: ").strip().lower()
    if raw == "":
        return default
    if raw not in ("y", "n"):
        return default
    return raw == "y"


def box(lines: list[str], title: str | None = None) -> None:
    """Print a rounded unicode box around the given lines."""
    width = max((len(line) for line in lines), default=0) + 4
    if title:
        width = max(width, len(title) + 6)

    top_label = f"─ {title} " if title else ""
    top = f"╭{top_label}{'─' * (width - 2 - len(top_label))}╮"
    bot = f"╰{'─' * (width - 2)}╯"

    print(cyan(top) if _is_tty() else top)
    for line in lines:
        padded = f"│  {line:<{width - 4}}  │"
        print(cyan("│") + f"  {line:<{width - 4}}  " + cyan("│") if _is_tty() else padded)
    print(cyan(bot) if _is_tty() else bot)


def success_check(msg: str) -> None:
    """Print a success line with icon."""
    icon = success(_ICON_OK) if _is_tty() else "[ok]"
    print(f"    {icon}  {msg}")


def warn_mark(msg: str) -> None:
    """Print a warning line with icon."""
    icon = warn(_ICON_WARN) if _is_tty() else "[!]"
    print(f"    {icon}  {msg}")


def error_mark(msg: str) -> None:
    """Print an error line with icon."""
    icon = error(_ICON_ERR) if _is_tty() else "[x]"
    print(f"    {icon}  {msg}")
