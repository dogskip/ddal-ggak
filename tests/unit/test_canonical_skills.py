"""Skill commands must exist in the actual CLI, including every declared option."""

from __future__ import annotations

import re
import shlex

from typer.main import get_command

from ddk.cli import app
from ddk.installer import skills


def test_exactly_three_canonical_skills() -> None:
    assert {path.parent.name for path in skills()} == {"ddk-verify", "ddk-evidence", "ddk-design"}


def test_all_skill_command_examples_match_typer_metadata() -> None:
    commands = 0
    for path in skills():
        for text in [
            path.read_text(),
            *(p.read_text() for p in path.parent.glob("references/*.md")),
        ]:
            for line in re.findall(r"(?m)^ddk .+$", text):
                tokens = shlex.split(line)
                command = get_command(app)
                index = 1
                while getattr(command, "commands", None):
                    assert index < len(tokens), line
                    assert tokens[index] in command.commands, line
                    command = command.commands[tokens[index]]
                    index += 1
                options = {
                    opt
                    for parameter in command.params
                    for opt in [
                        *getattr(parameter, "opts", []),
                        *getattr(parameter, "secondary_opts", []),
                    ]
                }
                for token in tokens[index:]:
                    if token.startswith("-"):
                        assert token.partition("=")[0] in options, line
                commands += 1
    assert commands >= 5
