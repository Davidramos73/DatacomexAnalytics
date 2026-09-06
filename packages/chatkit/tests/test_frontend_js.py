import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_chatkit_js_units():
    r = subprocess.run(
        ["node", "--test", "projects/footwear/web/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
