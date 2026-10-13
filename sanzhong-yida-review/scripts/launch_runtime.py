"""Locate the configured local runtime without embedding machine paths in the Skill."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument('--runtime-config')
    options, command = parser.parse_known_args()
    codex_root = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
    config_path = Path(options.runtime_config) if options.runtime_config else codex_root / 'skill-runtimes' / 'sanzhong-yida-review.json'
    python_path = os.environ.get('SANZHONG_REVIEW_PYTHON')
    if not python_path and config_path.is_file():
        config = json.loads(config_path.read_text(encoding='utf-8-sig'))
        python_path = config.get('python_path')
    python_path = python_path or sys.executable
    try:
        probe = subprocess.run([python_path, '-B', '-c', 'import langgraph; from langgraph.checkpoint.sqlite import SqliteSaver'], capture_output=True, text=True, encoding='utf-8')
    except OSError as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        return 2
    if probe.returncode:
        print(json.dumps({'ok': False, 'error': 'Configured Python cannot import LangGraph and SQLite checkpoint. Install scripts/requirements-langgraph.txt in a dedicated environment and set SANZHONG_REVIEW_PYTHON or the local runtime registry.', 'diagnostic': probe.stderr.strip()}, ensure_ascii=False))
        return 2
    entry = Path(__file__).with_name('run_langgraph.py')
    return subprocess.run([python_path, '-B', '-X', 'utf8', str(entry), *command]).returncode


if __name__ == '__main__':
    raise SystemExit(main())
