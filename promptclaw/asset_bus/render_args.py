"""Argv construction for render commands.

Render commands dispatched to the box (image, music, sfx) take operator
parameters that come from an untrusted JSON request: prompts, scene names,
mood text, etc. Those values must reach the render CLI as discrete argv
elements, never interpolated into a shell command line, so that shell
metacharacters in a request field (``;``, ``$(...)``, backticks, ``&&``,
``|``, redirections, newlines) are passed through literally instead of being
interpreted by ``/bin/sh``.

This module exposes the primitive every renderer goes through:
:func:`to_render_arg` validates and stringifies a single field, and
:func:`build_render_argv` composes a full argv list. The contract is
deliberately narrow — bytes, ``None``, containers, and NUL bytes are
rejected so a caller cannot smuggle in a value that some downstream
``str()`` or shell wrapper would mangle.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = [
    "RenderArgError",
    "build_render_argv",
    "to_render_arg",
]


class RenderArgError(ValueError):
    """Raised when a request-field value cannot be safely used as an argv element."""


def to_render_arg(value: Any) -> str:
    """Return a single argv element built from ``value``.

    Accepts ``str``, ``bool``, ``int``, and ``float``. Rejects ``None``,
    ``bytes``, containers, and any string containing a NUL byte (which would
    truncate the argv element when handed to ``execve``).

    No quoting or escaping is applied: the returned string is meant to be
    placed verbatim into an argv list, where the OS hands it to the child
    process as one ``argv[i]`` without shell interpretation.
    """
    if value is None:
        raise RenderArgError("render arg must not be None")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value) if isinstance(value, float) else str(value)
    if isinstance(value, str):
        if "\x00" in value:
            raise RenderArgError("render arg contains NUL byte")
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise RenderArgError(
            f"render arg must be str/int/float/bool, got bytes-like {type(value).__name__}"
        )
    if isinstance(value, (list, tuple, set, frozenset, Mapping)):
        raise RenderArgError(
            f"render arg must be a scalar, got container {type(value).__name__}"
        )
    raise RenderArgError(
        f"render arg must be str/int/float/bool, got {type(value).__name__}"
    )


def build_render_argv(
    executable: str,
    *positional: Any,
    **options: Any,
) -> list[str]:
    """Build an argv list for a render CLI invocation.

    ``executable`` is the program path or name (already chosen by the
    producer; not derived from request input). ``positional`` and
    ``options`` are request-derived values that go through
    :func:`to_render_arg`. ``options`` keys are emitted as ``--key`` flags
    (underscores become hyphens) followed by their value; an option whose
    value is ``True`` becomes a bare ``--key`` flag, and an option whose
    value is ``False`` or ``None`` is omitted.

    The result is a plain ``list[str]`` suitable for
    ``subprocess.run(argv, shell=False)`` or for a ``BoxRunner`` that
    passes argv across an ssh boundary without a remote shell.
    """
    if not isinstance(executable, str) or not executable:
        raise RenderArgError("executable must be a non-empty string")
    if "\x00" in executable:
        raise RenderArgError("executable contains NUL byte")

    argv: list[str] = [executable]
    for value in positional:
        argv.append(to_render_arg(value))
    for key, value in options.items():
        if value is None or value is False:
            continue
        flag = "--" + key.replace("_", "-")
        if value is True:
            argv.append(flag)
            continue
        argv.append(flag)
        argv.append(to_render_arg(value))
    return argv
