"""executeCMD streams stdout and surfaces stderr on failure."""
from __future__ import annotations

import pytest

from cats.utils import executeCMD


def test_execute_cmd_success_streams_stdout(capsys):
    executeCMD('printf "hello\\n"')
    assert 'hello' in capsys.readouterr().out


def test_execute_cmd_failure_includes_stderr():
    with pytest.raises(RuntimeError, match='non-zero exit status') as exc:
        executeCMD('printf "boom" 1>&2; exit 7')
    msg = str(exc.value)
    assert 'exit status 7' in msg
    assert 'boom' in msg
