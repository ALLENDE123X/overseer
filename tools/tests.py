import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent / "examples" / "sample_repo"


def run() -> dict:
    """run pytest in sample repo and return summary"""
    # install deps if requirements.txt exists
    req_file = REPO_ROOT / "requirements.txt"
    if req_file.exists():
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-q", "-r", str(req_file)],
                check=True,
                capture_output=True,
                cwd=REPO_ROOT
            )
        except subprocess.CalledProcessError:
            pass  # continue anyway
    
    # run pytest
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-v", "--tb=short"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT
        )
        output = result.stdout + result.stderr
        passed = result.returncode == 0
        
        # limit output to last 2000 chars
        if len(output) > 2000:
            output = "..." + output[-2000:]
        
        return {"passed": passed, "output": output}
    except Exception as e:
        return {"passed": False, "output": f"error running pytest: {str(e)}"}

