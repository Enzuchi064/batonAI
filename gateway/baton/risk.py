"""Clasificación de riesgo de comandos.

No pretende ser un analizador semántico: es una lista de patrones conocidos
que fuerza ceremonia extra (mantener pulsado) en el dispositivo. Cualquier
comando no reconocido es ``normal``, nunca ``low``.

Regla: ante la duda, subir de riesgo, no bajarlo. Un falso positivo cuesta
1,5 s de pulsación; un falso negativo puede costar un repositorio.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .protocol import Risk

# (patrón, riesgo, motivo)
_RULES: list[tuple[re.Pattern[str], Risk, str]] = [
    # Crítico: destrucción del sistema o de datos irrecuperables.
    (re.compile(r"\brm\s+(?:-\S+\s+)*/(?:\s|$|\*)"), Risk.CRITICAL, "borrado del sistema de ficheros"),
    (re.compile(r"mkfs(\.\w+)?\s"), Risk.CRITICAL, "formateo de disco"),
    (re.compile(r"dd\s+[^\n]*of=/dev/"), Risk.CRITICAL, "escritura directa sobre dispositivo"),
    (re.compile(r"diskpart\b", re.IGNORECASE), Risk.CRITICAL, "gestión de discos"),
    (re.compile(r"format\s+[a-zA-Z]:", re.IGNORECASE), Risk.CRITICAL, "formateo de unidad"),
    (re.compile(r"\b(shutdown|reboot|halt|poweroff)\b", re.IGNORECASE), Risk.CRITICAL, "apagado del equipo"),
    (re.compile(r":\(\)\s*\{\s*:\|:&\s*\};:"), Risk.CRITICAL, "fork bomb"),
    (re.compile(r"drop\s+database\b", re.IGNORECASE), Risk.CRITICAL, "borrado de base de datos"),

    # Alto: destrucción local, privilegios, publicación o ejecución remota.
    (re.compile(r"\brm\s+(?:-\S+\s+)*-\S*[rR]\S*"), Risk.HIGH, "borrado recursivo"),
    (re.compile(r"git\s+push\s+[^\n]*(-f\b|--force\b)"), Risk.HIGH, "force push"),
    (re.compile(r"git\s+reset\s+--hard\b"), Risk.HIGH, "descarte de cambios locales"),
    (re.compile(r"git\s+clean\s+-[a-zA-Z]*[fdx]"), Risk.HIGH, "borrado de ficheros no versionados"),
    (re.compile(r"\bsudo\b|\brunas\b|\bdoas\b"), Risk.HIGH, "ejecución con privilegios"),
    (re.compile(r"\bchmod\s+(-R\s+)?777\b"), Risk.HIGH, "permisos abiertos"),
    (re.compile(r"(curl|wget)[^\n|]*\|\s*(ba)?sh\b"), Risk.HIGH, "ejecución de script remoto"),
    (re.compile(r"\b(npm|pnpm|yarn)\s+publish\b"), Risk.HIGH, "publicación de paquete"),
    (re.compile(r"\b(pip|pip3)\s+install\s+(https?://|git\+)"), Risk.HIGH, "dependencia remota sin verificar"),
    (re.compile(r"drop\s+table\b|truncate\s+table\b", re.IGNORECASE), Risk.HIGH, "borrado de tabla"),
    (re.compile(r">\s*/dev/(sd|nvme|disk)"), Risk.HIGH, "escritura sobre dispositivo"),
    (re.compile(r"\bdel\s+/[fsq]\b", re.IGNORECASE), Risk.HIGH, "borrado en Windows"),
    (re.compile(r"\b(reg\s+delete|takeown|icacls)\b", re.IGNORECASE), Risk.HIGH, "cambio del sistema en Windows"),

    # Bajo: lectura evidente. Solo si no ha encajado nada anterior.
    (re.compile(r"^\s*(ls|cat|pwd|whoami|echo|head|tail|wc|rg|grep|find|fd|tree|git\s+(status|diff|log|show|branch))\b"), Risk.LOW, "lectura"),
]


@dataclass(slots=True)
class RiskAssessment:
    risk: Risk
    reasons: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)


_DETAILS = {
    "borrado del sistema de ficheros": "Borra el sistema de archivos.",
    "formateo de disco": "Formatea una unidad.",
    "escritura directa sobre dispositivo": "Escribe directamente sobre un disco.",
    "gestión de discos": "Modifica las particiones del disco.",
    "formateo de unidad": "Formatea una unidad del equipo.",
    "apagado del equipo": "Apaga o reinicia el equipo.",
    "fork bomb": "Bloquea el equipo.",
    "borrado de base de datos": "Borra una base de datos entera.",
    "borrado recursivo": "Borra archivos y carpetas de forma recursiva.",
    "force push": "Reescribe el historial remoto y puede afectar a otros.",
    "descarte de cambios locales": "Descarta cambios que no has guardado.",
    "borrado de ficheros no versionados": "Borra archivos que no están en Git.",
    "ejecución con privilegios": "Ejecuta con permisos de administrador.",
    "permisos abiertos": "Da permisos de escritura a cualquiera.",
    "ejecución de script remoto": "Ejecuta código descargado de internet sin revisarlo.",
    "publicación de paquete": "Publica un paquete; puede ser irreversible.",
    "dependencia remota sin verificar": "Instala una dependencia de una URL no verificada.",
    "borrado de tabla": "Borra una tabla y todos sus datos.",
    "escritura sobre dispositivo": "Escribe sobre un dispositivo de almacenamiento.",
    "borrado en Windows": "Borra archivos forzando aunque estén en uso.",
    "cambio del sistema en Windows": "Cambia permisos o claves del sistema.",
    "lectura": "Solo consulta información.",
}


def classify(command: str, kind: str = "bash") -> RiskAssessment:
    if not command.strip():
        return RiskAssessment(
            Risk.NORMAL,
            ["comando vacío"],
            ["El comando está vacío."],
        )

    matched: list[tuple[Risk, str]] = [
        (risk, reason) for pattern, risk, reason in _RULES if pattern.search(command)
    ]
    if not matched:
        return RiskAssessment(
            Risk.NORMAL,
            [],
            ["No se reconoce como peligroso, pero puede modificar cosas."],
        )

    order = {Risk.LOW: 0, Risk.NORMAL: 1, Risk.HIGH: 2, Risk.CRITICAL: 3}
    highest = max((risk for risk, _ in matched), key=lambda r: order[r])
    reasons = [reason for _, reason in matched]
    details = list(dict.fromkeys(_DETAILS.get(reason, reason) for reason in reasons))
    return RiskAssessment(highest, reasons, details)


def hold_ms_for(risk: Risk) -> int:
    """Tiempo que el usuario debe mantener [A] para confirmar."""
    return {
        Risk.LOW: 0,
        Risk.NORMAL: 0,
        Risk.HIGH: 1500,
        Risk.CRITICAL: 2500,
    }[risk]
