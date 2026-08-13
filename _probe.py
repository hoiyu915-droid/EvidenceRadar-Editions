from pathlib import Path

def save(path: Path, text: str) -> None:
    path.write_text(text)
