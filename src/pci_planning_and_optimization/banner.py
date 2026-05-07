# Copyright 2025-2026 coRAN LABS Private Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from __future__ import annotations

import os
import sys
from typing import IO

__all__ = [
    "WIDTH",
    "arrow",
    "blank",
    "box",
    "check",
    "command",
    "rule",
    "title",
]


WIDTH = 104
_LABEL = 26
_BOX_LABEL = 13

_RESET = "\x1b[0m"
_DIM = "\x1b[2m"
_BOLD = "\x1b[1m"
_CYAN = "\x1b[36m"
_GREEN = "\x1b[32m"

_LOGO = ("╔═╗╔═╗╦", "╠═╝║  ║", "╩  ╚═╝╩")
_GREEN_SECTIONS = frozenset({"READY", "STOPPED"})


def _out() -> IO[str]:
    return sys.stdout


def _colour() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    try:
        return bool(_out().isatty())
    except Exception:
        return False


def _c(text: str, *styles: str) -> str:
    return f"{''.join(styles)}{text}{_RESET}" if _colour() else text


def _echo(line: str = "") -> None:
    print(line, file=_out(), flush=True)


def blank() -> None:
    _echo()


def _heading_colour(name: str) -> str:
    return _GREEN if name in _GREEN_SECTIONS else _CYAN


def title(name: str, version: str, subtitle: str, strapline: str) -> None:
    inner = WIDTH - 2
    rows = (
        (name, f"v{version}", (_BOLD,)),
        (subtitle, "", ()),
        (strapline, "", (_DIM,)),
    )

    _echo()
    _echo(_c("╭" + "─" * inner + "╮", _DIM))
    _echo(_c("│" + " " * inner + "│", _DIM))
    for logo, (text, right, styles) in zip(_LOGO, rows, strict=True):
        gap = inner - 3 - len(logo) - 3 - len(text) - len(right) - 2
        _echo(
            _c("│", _DIM)
            + "   "
            + _c(logo, _CYAN)
            + "   "
            + _c(text, *styles)
            + " " * gap
            + _c(right, _DIM)
            + "  "
            + _c("│", _DIM)
        )
    _echo(_c("│" + " " * inner + "│", _DIM))
    _echo(_c("╰" + "─" * inner + "╯", _DIM))
    _echo()


def rule(name: str) -> None:
    dashes = WIDTH - 4 - len(name)
    _echo(
        _c("── ", _DIM)
        + _c(name, _BOLD, _heading_colour(name))
        + " "
        + _c("─" * dashes, _DIM)
    )


def box(heading: str, rows: list[tuple[str, str]], footer: str) -> None:
    colour = _heading_colour(heading)
    top = WIDTH - 5 - len(heading)
    _echo(
        _c("╭─ ", _DIM)
        + _c(heading, _BOLD, colour)
        + " "
        + _c("─" * top + "╮", _DIM)
    )
    room = WIDTH - 4 - _BOX_LABEL
    for label, raw in rows:
        value = raw if len(raw) <= room else raw[: room - 1] + "…"
        body = f"  {label:<{_BOX_LABEL}}{value}"
        _echo(
            _c("│", _DIM)
            + f"  {_c(label, _BOLD)}{' ' * (_BOX_LABEL - len(label))}{value}"
            + " " * (WIDTH - 2 - len(body))
            + _c("│", _DIM)
        )
    bottom = WIDTH - 5 - len(footer)
    _echo(
        _c("╰─ ", _DIM)
        + _c(footer, colour)
        + " "
        + _c("─" * bottom + "╯", _DIM)
    )


def check(ok: bool, label: str, detail: str) -> None:
    mark = _c("✔", _GREEN) if ok else _c("•", _DIM)
    _echo(f"   {mark}  {_c(f'{label:<{_LABEL}}', _BOLD)}{_c(detail, _DIM)}")


def arrow(label: str, detail: str) -> None:
    _echo(f"   {_c('⏵', _CYAN)}  {_c(f'{label:<{_LABEL}}', _BOLD)}{_c(detail, _DIM)}")


def command(product: str, name: str, version: str, subcommand: str) -> None:
    sep = _c("│", _DIM)
    _echo(
        f" {_c(product, _BOLD, _CYAN)} {sep} {_c(f'{name} v{version}', _DIM)} "
        f"{sep} {_c(subcommand, _BOLD)}"
    )
