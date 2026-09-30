"""Pasos protegidos del monitoreo: una falla no deja cambios a medias en un registro."""

import sys

from src.monitoring.guarded import run_guarded


def py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_successful_append_is_kept(tmp_path):
    f = tmp_path / "r.csv"
    f.write_text("a\n1\n", encoding="utf-8")
    assert run_guarded(f, py(f"open(r'{f}', 'a').write('2\\n')"), "x")
    assert f.read_text(encoding="utf-8") == "a\n1\n2\n"


def test_failure_restores_previous_content(tmp_path):
    f = tmp_path / "r.csv"
    f.write_text("a\n1\n", encoding="utf-8")
    assert not run_guarded(f, py(f"open(r'{f}', 'a').write('2\\n'); raise SystemExit(1)"), "x")
    assert f.read_text(encoding="utf-8") == "a\n1\n"


def test_rewriting_old_rows_is_rejected_even_if_the_command_succeeds(tmp_path):
    f = tmp_path / "r.csv"
    f.write_text("a\n1\n", encoding="utf-8")
    assert not run_guarded(f, py(f"open(r'{f}', 'w').write('a\\n9\\n2\\n')"), "x")
    assert f.read_text(encoding="utf-8") == "a\n1\n"


def test_a_command_that_cannot_start_is_a_failure_not_a_crash(tmp_path):
    f = tmp_path / "r.csv"
    f.write_text("a\n1\n", encoding="utf-8")
    assert not run_guarded(f, [str(tmp_path / "no-existe.exe")], "x")
    assert f.read_text(encoding="utf-8") == "a\n1\n"


def test_failed_first_run_leaves_no_file(tmp_path):
    f = tmp_path / "nuevo.csv"
    assert not run_guarded(f, py(f"open(r'{f}', 'w').write('a\\n'); raise SystemExit(2)"), "x")
    assert not f.exists()
