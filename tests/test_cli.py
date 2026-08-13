from __future__ import annotations

from pathlib import Path

from evidenceradar_editions.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_cli_build_and_validate(tmp_path: Path, capsys) -> None:
    output = tmp_path / "edition"
    result = main(
        [
            "build",
            "--collection",
            str(ROOT / "config/collections/jama-network-open.yml"),
            "--start",
            "2026-08-01",
            "--end",
            "2026-08-31",
            "--output",
            str(output),
            "--fixture-dir",
            str(ROOT / "tests/fixtures"),
            "--strict-sources",
        ]
    )
    assert result == 0
    assert '"article_count": 2' in capsys.readouterr().out
    assert main(["validate", str(output)]) == 0
