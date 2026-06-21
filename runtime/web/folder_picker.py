from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FolderPickResult:
    ok: bool
    path: str | None = None
    message: str = ""


def _pickers() -> tuple[tuple[str, list[str]], ...]:
    return (
        ("zenity", ["zenity", "--file-selection", "--directory", "--title=Seleccionar carpeta del proyecto"]),
        ("kdialog", ["kdialog", "--getexistingdirectory", str(Path.home())]),
        ("yad", ["yad", "--file", "--directory", "--title=Seleccionar carpeta del proyecto"]),
    )


def pick_folder_native(*, initial_dir: Path | None = None) -> FolderPickResult:
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return FolderPickResult(
            ok=False,
            message="No hay entorno gráfico disponible. Escribe la ruta manualmente.",
        )

    start_dir = (initial_dir or Path.home()).expanduser().resolve()
    if not start_dir.is_dir():
        start_dir = Path.home()

    last_error = "No se encontró zenity, kdialog ni yad."
    for name, base_cmd in _pickers():
        if shutil.which(base_cmd[0]) is None:
            continue
        cmd = list(base_cmd)
        if name == "zenity":
            cmd.extend(["--filename", f"{start_dir}/"])
        elif name == "kdialog":
            cmd[-1] = str(start_dir)
        elif name == "yad":
            cmd.extend(["--filename", str(start_dir)])
        try:
            completed = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            last_error = str(exc)
            continue

        if completed.returncode != 0:
            if completed.returncode in {1, 255}:
                return FolderPickResult(ok=False, message="Selección cancelada.")
            stderr = (completed.stderr or "").strip()
            last_error = stderr or f"{name} falló con código {completed.returncode}"
            continue

        selected = (completed.stdout or "").strip()
        if not selected:
            return FolderPickResult(ok=False, message="No se seleccionó ninguna carpeta.")
        folder = Path(selected).expanduser().resolve()
        if not folder.is_dir():
            return FolderPickResult(ok=False, message="La selección no es una carpeta válida.")
        return FolderPickResult(ok=True, path=str(folder), message=str(folder))

    return FolderPickResult(ok=False, message=last_error)
