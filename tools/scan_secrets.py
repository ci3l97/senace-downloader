"""Escaneo local, sin dependencias, para evitar credenciales en Git."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}
SENSITIVE_NAMES = {".env", ".npmrc", ".pypirc"}

# Los prefijos se construyen por partes para que el escáner no se detecte a sí mismo.
PATTERNS = [
    ("token clásico de GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("token de GitHub", re.compile(r"\bgithub" + r"_pat_[A-Za-z0-9_]{20,}\b")),
    ("access key de AWS", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("clave de Google", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("token de Slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("clave privada", re.compile("-----BEGIN " + r"(?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
]

ASSIGNMENT = re.compile(
    r"(?i)\b(?:api[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token|password|passwd|secret[_-]?key)"
    r"\s*[:=]\s*['\"]([^'\"]{12,})['\"]"
)
PLACEHOLDERS = {"example", "placeholder", "replace-me", "changeme", "your-key-here"}


def candidate_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]


def main() -> int:
    findings: list[str] = []
    for path in candidate_files():
        relative = path.relative_to(ROOT).as_posix()
        lower_name = path.name.lower()
        if lower_name in SENSITIVE_NAMES or path.suffix.lower() in SENSITIVE_SUFFIXES:
            findings.append(f"archivo sensible rastreable: {relative}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pattern in PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{relative}:{line}: posible {label}")
        for match in ASSIGNMENT.finditer(text):
            value = match.group(1).strip().lower()
            if value not in PLACEHOLDERS and not value.startswith(("${", "{{", "%")):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{relative}:{line}: posible credencial asignada")

    if findings:
        print("ERROR: se encontraron posibles secretos:")
        print("\n".join(f"- {finding}" for finding in findings))
        return 1
    print("OK: no se detectaron secretos ni archivos de credenciales.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
