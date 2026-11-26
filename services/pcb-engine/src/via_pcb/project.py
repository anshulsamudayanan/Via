"""KiCad project archives: a ``.zip`` holding a board plus its project and rule files.

KiCad 6+ keeps design rules and net classes in ``<name>.kicad_pro`` (JSON) and custom
rules in ``<name>.kicad_dru`` (S-expressions), not in the ``.kicad_pcb``. Without them,
rule checks fall back to KiCad's defaults and report false violations (measured in the
Stage 2 audit). This module reads such an archive *safely* and folds the project rules
into :class:`~via_pcb.models.DesignConstraints`.

Safety: the archive is never extracted to disk. Entry count, declared and actual sizes
and compression ratio are bounded (zip bombs), encrypted entries and unsafe member
paths are refused, nested archives are ignored. Only the selected board, project and
rule files are read.
"""

from __future__ import annotations

import fnmatch
import io
import json
import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any, BinaryIO

from via_pcb.adapters.base import UnsupportedFormatError
from via_pcb.adapters.kicad import KiCadAdapter
from via_pcb.models import CustomRule, DesignRules, NetClass, ParseWarning, PCBDesign, RuleConstraint
from via_pcb.parser import SExpr, SExprParseError, parse_sexpr

ARCHIVE_EXTENSIONS = (".zip",)
_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06")


class ProjectArchiveError(UnsupportedFormatError):
    """The archive is unsafe, malformed or doesn't contain a usable KiCad project."""


@dataclass(frozen=True)
class ArchiveLimits:
    max_entries: int = 5000
    max_board_bytes: int = 512 * 1024 * 1024
    max_side_file_bytes: int = 16 * 1024 * 1024  # .kicad_pro / .kicad_dru
    max_ratio: int = 200  # uncompressed / compressed, for members over 1 MiB


@dataclass
class ProjectFiles:
    board_name: str
    board: bytes
    project_name: str | None = None
    project: bytes | None = None
    rules_name: str | None = None
    rules: bytes | None = None
    warnings: list[ParseWarning] = field(default_factory=list)


def is_project_archive(filename: str | None, head: bytes) -> bool:
    ext_ok = filename is None or filename.lower().endswith(ARCHIVE_EXTENSIONS)
    return ext_ok and head.startswith(_ZIP_MAGIC)


def _safe_name(name: str) -> str | None:
    """Normalized member path, or None for entries to ignore. Raises on unsafe paths."""
    if name.endswith("/"):
        return None
    norm = name.replace("\\", "/")
    if norm.startswith("/") or re.match(r"^[A-Za-z]:", norm) or ".." in norm.split("/"):
        raise ProjectArchiveError(f"The archive contains an unsafe path: {name[:120]!r}")
    parts = norm.split("/")
    if any(p.startswith(".") or p == "__MACOSX" or p.endswith("-backups") for p in parts):
        return None  # hidden files, macOS metadata, KiCad's automatic backups
    return norm


def select_project(
    source: bytes | BinaryIO, limits: ArchiveLimits | None = None
) -> tuple[zipfile.ZipFile, dict[str, zipfile.ZipInfo]]:
    """Open the archive, validate every entry and return (zip, members by safe name)."""
    limits = limits or ArchiveLimits()
    try:
        zf = zipfile.ZipFile(io.BytesIO(source) if isinstance(source, bytes) else source)
    except (zipfile.BadZipFile, ValueError) as exc:
        raise ProjectArchiveError("The file isn't a valid .zip archive.") from exc
    infos = zf.infolist()
    if len(infos) > limits.max_entries:
        raise ProjectArchiveError(f"The archive has more than {limits.max_entries} entries.")
    members: dict[str, zipfile.ZipInfo] = {}
    for info in infos:
        name = _safe_name(info.filename)
        if name is None:
            continue
        if info.flag_bits & 0x1:
            raise ProjectArchiveError("Encrypted archives aren't supported.")
        if info.file_size > 1024 * 1024 and info.file_size > limits.max_ratio * max(info.compress_size, 1):
            raise ProjectArchiveError(f"'{name}' is compressed suspiciously well; refusing to expand it.")
        members[name] = info
    return zf, members


def _read(zf: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int) -> bytes:
    if info.file_size > limit:
        raise ProjectArchiveError(f"'{info.filename}' is larger than the {limit // (1024 * 1024)} MB limit.")
    with zf.open(info) as fh:
        data = fh.read(limit + 1)
    if len(data) > limit:  # the declared size lied
        raise ProjectArchiveError(f"'{info.filename}' is larger than the {limit // (1024 * 1024)} MB limit.")
    return data


@dataclass
class ProjectPlan:
    """Which members an archive's project consists of, decided from the central directory only."""

    board_name: str
    board_size: int
    project_name: str | None = None
    rules_name: str | None = None
    warnings: list[ParseWarning] = field(default_factory=list)


def _plan(members: dict[str, zipfile.ZipInfo], limits: ArchiveLimits) -> ProjectPlan:
    boards = sorted(n for n in members if n.lower().endswith(".kicad_pcb"))
    if not boards:
        raise ProjectArchiveError("The archive doesn't contain a .kicad_pcb board.")

    def sibling(board: str, ext: str) -> str | None:
        want = posixpath.splitext(board)[0] + ext
        return next((n for n in members if n.lower() == want.lower()), None)

    if len(boards) > 1:
        with_project = [b for b in boards if sibling(b, ".kicad_pro")]
        if len(with_project) != 1:
            listed = ", ".join(boards[:5]) + (" ..." if len(boards) > 5 else "")
            raise ProjectArchiveError(
                f"The archive contains several boards ({listed}). Upload an archive with one KiCad project."
            )
        boards = with_project
    board_name = boards[0]
    board = members[board_name]
    if board.file_size > limits.max_board_bytes:
        raise ProjectArchiveError(
            f"'{board_name}' is larger than the {limits.max_board_bytes // (1024 * 1024)} MB limit."
        )
    plan = ProjectPlan(board_name=board_name, board_size=board.file_size)
    plan.project_name = sibling(board_name, ".kicad_pro")
    plan.rules_name = sibling(board_name, ".kicad_dru")
    for name in (plan.project_name, plan.rules_name):
        if name and members[name].file_size > limits.max_side_file_bytes:
            raise ProjectArchiveError(
                f"'{name}' is larger than the {limits.max_side_file_bytes // (1024 * 1024)} MB limit."
            )
    if plan.project_name is None:
        if sibling(board_name, ".pro"):
            plan.warnings.append(
                ParseWarning(
                    code="legacy_project_file",
                    message="KiCad 5 project files (.pro) aren't read; only rules stored in the board file are used.",
                )
            )
        else:
            plan.warnings.append(
                ParseWarning(
                    code="missing_project_file",
                    message=(
                        f"No .kicad_pro next to {board_name}: project design rules and net classes are unavailable."
                    ),
                )
            )
    return plan


def inspect_project(source: bytes | BinaryIO, limits: ArchiveLimits | None = None) -> ProjectPlan:
    """Validate an archive and choose its project without decompressing anything (for upload checks)."""
    limits = limits or ArchiveLimits()
    zf, members = select_project(source, limits)
    with zf:
        return _plan(members, limits)


def read_project(data: bytes, limits: ArchiveLimits | None = None) -> ProjectFiles:
    """Pick the board in the archive and read it with its project and rule files."""
    limits = limits or ArchiveLimits()
    zf, members = select_project(data, limits)
    with zf:
        plan = _plan(members, limits)
        files = ProjectFiles(
            board_name=plan.board_name,
            board=_read(zf, members[plan.board_name], limits.max_board_bytes),
            warnings=plan.warnings,
        )
        if plan.project_name:
            files.project_name = plan.project_name
            files.project = _read(zf, members[plan.project_name], limits.max_side_file_bytes)
        if plan.rules_name:
            files.rules_name = plan.rules_name
            files.rules = _read(zf, members[plan.rules_name], limits.max_side_file_bytes)
    return files


# --- .kicad_pro ------------------------------------------------------------------------------

_RULE_FIELDS = set(DesignRules.model_fields)
_CLASS_FIELDS = {
    "clearance",
    "track_width",
    "via_diameter",
    "via_drill",
    "microvia_diameter",
    "microvia_drill",
    "diff_pair_width",
    "diff_pair_gap",
}


def _obj(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def project_rules(raw: bytes, net_names: list[str]) -> tuple[DesignRules | None, list[NetClass], list[ParseWarning]]:
    """Design rules and net classes (with resolved nets) from a .kicad_pro file."""
    warnings: list[ParseWarning] = []
    try:
        doc = json.loads(raw.decode("utf-8"))
        if not isinstance(doc, dict):
            raise ValueError("not an object")
    except (UnicodeDecodeError, ValueError):
        warnings.append(
            ParseWarning(code="invalid_project_file", message="The .kicad_pro file isn't valid JSON; ignored.")
        )
        return None, [], warnings

    board = _obj(doc.get("board"))
    settings = _obj(board.get("design_settings"))
    raw_rules = _obj(settings.get("rules"))
    values: dict[str, Any] = {}
    for key, value in raw_rules.items():
        if key not in _RULE_FIELDS:
            continue
        if key.startswith("allow_"):
            if isinstance(value, bool):
                values[key] = value
        elif (n := _num(value)) is not None:
            values[key] = n
    rules = DesignRules(**values) if values else None

    net_settings = _obj(doc.get("net_settings"))
    classes: dict[str, NetClass] = {}
    explicit: dict[str, list[str]] = {}
    for entry in net_settings.get("classes") or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            continue
        nc = NetClass.model_validate({"name": entry["name"], **{k: _num(entry.get(k)) for k in _CLASS_FIELDS}})
        classes[nc.name] = nc
        for net in entry.get("nets") or []:  # KiCad 6: nets listed per class
            if isinstance(net, str):
                explicit.setdefault(net, []).append(nc.name)
    for item in net_settings.get("netclass_patterns") or []:  # KiCad 7+
        if isinstance(item, dict) and isinstance(item.get("pattern"), str) and item.get("netclass") in classes:
            classes[item["netclass"]].patterns.append(item["pattern"])
    assignments = net_settings.get("netclass_assignments")  # KiCad 8+: {net: class | [classes]}
    if isinstance(assignments, dict):
        for net, value in assignments.items():
            names = [value] if isinstance(value, str) else [v for v in value or [] if isinstance(v, str)]
            explicit.setdefault(net, []).extend(n for n in names if n in classes)

    # Resolve: explicit assignments, else wildcard patterns, else the Default class.
    default = classes.get("Default")
    for net in net_names:
        targets = list(dict.fromkeys(explicit.get(net, [])))
        if not targets:
            targets = [nc.name for nc in classes.values() if any(fnmatch.fnmatchcase(net, p) for p in nc.patterns)]
        if not targets and default is not None:
            targets = [default.name]
        for name in targets:
            classes[name].nets.append(net)
    return rules, list(classes.values()), warnings


# --- .kicad_dru ------------------------------------------------------------------------------

_UNIT_MM = {"mm": 1.0, "mil": 0.0254, "mils": 0.0254, "in": 25.4, "um": 0.001}
_VALUE_RE = re.compile(r"^(-?\d+(?:\.\d+)?)\s*(mm|mils?|in|um)$")


def _mm(token: str | None) -> float | None:
    if token is None:
        return None
    m = _VALUE_RE.match(str(token).strip())
    return round(float(m.group(1)) * _UNIT_MM[m.group(2)], 6) if m else None


def _render(node: SExpr) -> str:
    parts = [f"({_render(a)})" if isinstance(a, SExpr) else str(a) for a in node]
    return " ".join(parts)


def custom_rules(raw: bytes) -> tuple[list[CustomRule], list[ParseWarning]]:
    try:
        root = parse_sexpr("(dru " + raw.decode("utf-8") + "\n)")
    except (UnicodeDecodeError, SExprParseError) as exc:
        return [], [ParseWarning(code="invalid_rules_file", message=f"The .kicad_dru file couldn't be read: {exc}")]
    rules: list[CustomRule] = []
    for node in root.children("rule"):
        atoms = node.atoms()
        constraints = []
        for c in node.children("constraint"):
            kind = c.atoms()[0] if c.atoms() else ""
            constraints.append(
                RuleConstraint(
                    kind=kind,
                    min=_mm(c.atom("min")),
                    opt=_mm(c.atom("opt")),
                    max=_mm(c.atom("max")),
                    raw=f"({_render(c)})",
                )
            )
        rules.append(
            CustomRule(
                name=atoms[0] if atoms else "",
                condition=node.atom("condition"),
                layer=node.atom("layer"),
                severity=node.atom("severity"),
                constraints=constraints,
            )
        )
    return rules, []


# --- Entry point -----------------------------------------------------------------------------


def parse_project(data: bytes, filename: str | None = None, limits: ArchiveLimits | None = None) -> PCBDesign:
    """Parse a KiCad project archive into a design whose constraints include the project rules."""
    import hashlib

    files = read_project(data, limits)
    design = KiCadAdapter().parse(files.board, filename=posixpath.basename(files.board_name))
    # Identify the archive (what the user uploaded and VIA stores), and the members used.
    design.source.filename = filename
    design.source.sha256 = hashlib.sha256(data).hexdigest()
    design.source.size_bytes = len(data)
    design.source.board_file = files.board_name
    design.source.project_files = [n for n in (files.project_name, files.rules_name) if n]
    warnings = list(files.warnings)
    if files.project is not None:
        rules, classes, w = project_rules(files.project, [n.name for n in design.nets])
        warnings += w
        if rules is not None or classes:
            design.constraints.rules = rules
            design.constraints.net_classes = classes
            design.constraints.rules_source = "project_file"
    if files.rules is not None:
        design.constraints.custom_rules, w = custom_rules(files.rules)
        warnings += w
    design.warnings = warnings + design.warnings
    return design
