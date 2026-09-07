"""The configured process writes closed JSON to both sinks without handler leaks."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.platform


def test_logging_reconfiguration_closes_old_file_and_redacts_both_sinks(tmp_path: Path) -> None:
    script = """
import logging, sys
from pathlib import Path
from ai_stp_platform.logging import configure_logging, get_logger
root = logging.getLogger()
configure_logging(Path(sys.argv[1]))
old = [h for h in root.handlers if isinstance(h, logging.FileHandler)][0]
configure_logging(Path(sys.argv[1]))
assert old.stream is None
assert len([h for h in root.handlers if h.get_name() == 'ai_stp']) == 2
get_logger('probe').info(
    'catalog_probe', catalog_indexed=7, token='sensitive-value',
    email='private@example.test', passport={'password': 'not-for-logs'},
    reason='https://private.test/?token=sensitive-value',
)
logging.getLogger('httpx').warning('request https://private.test/?token=sensitive-value')
try:
    raise ValueError('private@example.test sensitive-value')
except ValueError:
    get_logger('probe').exception('probe_failed', error='ValueError: sensitive-value')
"""
    run = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)], capture_output=True, text=True, check=True
    )
    file_text = (tmp_path / "ai_stp.log").read_text()
    output = [json.loads(line) for line in run.stdout.splitlines()]
    stored = [json.loads(line) for line in file_text.splitlines()]
    assert output == stored
    assert len(stored) == 3
    assert stored[0]["catalog_indexed"] == 7
    assert stored[1]["event"] == "external_log"
    assert stored[2]["error_type"] == "ValueError"
    for text in [run.stdout, run.stderr, file_text]:
        assert "sensitive-value" not in text
        assert "private@example.test" not in text
        assert "private.test" not in text
        assert "passport" not in text
