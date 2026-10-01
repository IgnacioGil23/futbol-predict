"""Ejecuta un paso que escribe en un registro de "solo agregar", sin que su falla afecte al resto del monitoreo.

Se usa para el modelo en evaluación: si el comando falla, o si el archivo cambió de otra
forma que agregando filas al final, se restaura el contenido anterior (o se borra si no existía), se emite un
aviso de GitHub Actions y se sale con código 0. El registro del modelo de producción NO pasa por acá: su falla
sí tiene que cortar el workflow.

Uso:
    python -m src.monitoring.guarded --file monitoring-branch/ledger/x.csv --label "tiros" -- python -m ...
"""

import argparse
import subprocess
import sys
from pathlib import Path

from src.monitoring.ledger import LedgerIntegrityError, verify_append_only


def run_guarded(path: Path, command: list[str], label: str) -> bool:
    before = path.read_text(encoding="utf-8") if path.exists() else None
    try:
        ok = subprocess.run(command).returncode == 0
    except OSError as err:              # el comando ni siquiera se pudo lanzar: también es una falla del paso
        print(f"::error::{label}: {err}")
        ok = False
    if ok and path.exists():
        try:
            verify_append_only(before or "", path.read_text(encoding="utf-8"))
        except LedgerIntegrityError as err:
            print(f"::error::{label}: {err}")
            ok = False
    if not ok:
        if before is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(before, encoding="utf-8", newline="\n")
        print(f"::warning::Falló {label}; se descartaron sus cambios de hoy y el monitoreo sigue.")
    else:
        print(f"{label}: integridad verificada.")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("falta el comando a ejecutar después de --")
    run_guarded(args.file, command, args.label)
    sys.exit(0)


if __name__ == "__main__":
    main()
