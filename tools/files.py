import os
from pathlib import Path

# safe root for all file operations
SAFE_ROOT = Path(__file__).parent.parent / "examples" / "sample_repo"


def read(path: str) -> dict:
    """read file from safe root"""
    full_path = (SAFE_ROOT / path).resolve()
    if not str(full_path).startswith(str(SAFE_ROOT)):
        raise ValueError(f"path {path} escapes safe root")
    
    if not full_path.exists():
        return {"error": f"file not found: {path}"}
    
    with open(full_path, "r") as f:
        content = f.read()
    
    return {"content": content, "path": str(path)}


def write(path: str, content: str) -> dict:
    """write file to safe root"""
    full_path = (SAFE_ROOT / path).resolve()
    if not str(full_path).startswith(str(SAFE_ROOT)):
        raise ValueError(f"path {path} escapes safe root")
    
    # ensure parent directory exists
    full_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(full_path, "w") as f:
        f.write(content)
    
    return {"ok": True, "path": str(path), "bytes": len(content)}

