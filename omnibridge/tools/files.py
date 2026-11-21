"""File + project tools (sandboxed to the workspace)."""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from ..core.permissions import ToolDef, redact_secrets
from ..core.registry import Registry
from ..core.sandbox import sandbox_resolve

SKIP_DIRS = {"node_modules", ".git", "dist", ".next", "build", "out", "target", ".cache", ".venv",
             "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".idea", ".vscode",
             "coverage", "htmlcov", ".tox", "site-packages"}
TEXT_EXTS = {".ts", ".js", ".mjs", ".cjs", ".json", ".md", ".txt", ".luau", ".lua", ".rbxlx", ".xml",
             ".html", ".css", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".sh", ".py", ".rs", ".go",
             ".java", ".c", ".h", ".cpp", ".cs", ".rb", ".php", ".sql", ".graphql", ".example"}


def _walk(root: Path, directory: Path, out: list[str], depth: int, max_depth: int) -> None:
    if depth > max_depth or len(out) > 5000:
        return
    try:
        entries = sorted(directory.iterdir(), key=lambda p: p.name)
    except OSError:
        return
    for e in entries:
        if e.name in SKIP_DIRS:
            continue
        if e.is_dir():
            _walk(root, e, out, depth + 1, max_depth)
        else:
            out.append(str(e.relative_to(root)))


def _backup(cfg, abs_path: Path) -> str | None:
    if not abs_path.exists():
        return None
    backup_dir = cfg.data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / f"{abs_path.name}.{int(time.time() * 1000)}.bak"
    shutil.copy2(abs_path, dest)
    return str(dest)


def register_file_tools(reg: Registry) -> None:
    async def file_list(args: dict, ctx) -> dict:
        abs_path = sandbox_resolve(ctx.config.workspace_root, str(args.get("path", ".")))
        files: list[str] = []
        if args.get("recursive") is False:
            for e in sorted(abs_path.iterdir(), key=lambda p: p.name):
                if e.name not in SKIP_DIRS:
                    files.append(str(e.relative_to(ctx.config.workspace_root)))
        else:
            _walk(ctx.config.workspace_root, abs_path, files, 0, int(args.get("maxDepth", 4)))
        return {"path": str(args.get("path", ".")), "count": len(files), "files": files[:2000]}

    async def file_read(args: dict, ctx) -> dict:
        abs_path = sandbox_resolve(ctx.config.workspace_root, str(args["path"]))
        if abs_path.stat().st_size > ctx.config.max_file_bytes:
            raise ValueError(f"File too large ({abs_path.stat().st_size} bytes > {ctx.config.max_file_bytes})")
        if abs_path.suffix.lower() not in TEXT_EXTS and abs_path.suffix != "":
            raise ValueError(f"Refusing to read non-text file: {abs_path.suffix}")
        lines = abs_path.read_text(encoding="utf-8").split("\n")
        offset = int(args.get("offset", 1))
        limit = int(args.get("limit", 2000))
        return {"path": str(args["path"]), "totalLines": len(lines),
                "lines": lines[offset - 1: offset - 1 + limit]}

    async def file_search(args: dict, ctx) -> dict:
        abs_path = sandbox_resolve(ctx.config.workspace_root, str(args.get("path", ".")))
        pattern = re.compile(str(args["pattern"]), re.I)
        glob = str(args["glob"]).lstrip("*") if args.get("glob") else None
        files: list[str] = []
        _walk(ctx.config.workspace_root, abs_path, files, 0, 6)
        hits: list[dict] = []
        max_results = int(args.get("maxResults", 100))
        for f in files:
            if glob and not f.endswith(glob):
                continue
            if Path(f).suffix.lower() not in TEXT_EXTS:
                continue
            full = ctx.config.workspace_root / f
            try:
                if full.stat().st_size > ctx.config.max_file_bytes:
                    continue
                content = full.read_text(encoding="utf-8")
            except OSError:
                continue
            for i, line in enumerate(content.split("\n")):
                if len(hits) < max_results and pattern.search(line):
                    hits.append({"file": f, "line": i + 1, "text": line.strip()[:300]})
            if len(hits) >= max_results:
                break
        return {"pattern": str(args["pattern"]), "count": len(hits), "hits": hits}

    async def file_create(args: dict, ctx) -> dict:
        abs_path = sandbox_resolve(ctx.config.workspace_root, str(args["path"]))
        if abs_path.exists():
            raise ValueError(f"File already exists: {args['path']}. Use file_update.")
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        content = redact_secrets(str(args["content"]))
        abs_path.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(args["path"]), "bytes": len(content.encode())}

    async def file_update(args: dict, ctx) -> dict:
        abs_path = sandbox_resolve(ctx.config.workspace_root, str(args["path"]))
        bak = _backup(ctx.config, abs_path)
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        content = redact_secrets(str(args["content"]))
        abs_path.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(args["path"]), "backup": bak, "bytes": len(content.encode())}

    async def file_backup(args: dict, ctx) -> dict:
        abs_path = sandbox_resolve(ctx.config.workspace_root, str(args["path"]))
        bak = _backup(ctx.config, abs_path)
        if not bak:
            raise ValueError(f"File not found: {args['path']}")
        return {"ok": True, "path": str(args["path"]), "backup": bak}

    async def file_delete(args: dict, ctx) -> dict:
        abs_path = sandbox_resolve(ctx.config.workspace_root, str(args["path"]))
        if not abs_path.exists():
            raise ValueError(f"File not found: {args['path']}")
        if not abs_path.is_file():
            raise ValueError("file_delete only removes files (never directories).")
        bak = _backup(ctx.config, abs_path)
        abs_path.unlink()
        return {"ok": True, "path": str(args["path"]), "backup": bak,
                "note": "The file was backed up before deletion and can be restored from the backup path."}

    async def project_inspect(args: dict, ctx) -> dict:
        abs_path = sandbox_resolve(ctx.config.workspace_root, str(args.get("path", ".")))
        files: list[str] = []
        _walk(ctx.config.workspace_root, abs_path, files, 0, 5)
        by_ext: dict[str, int] = {}
        for f in files:
            e = Path(f).suffix.lower() or "(none)"
            by_ext[e] = by_ext.get(e, 0) + 1

        def read_json(name: str):
            try:
                return json.loads((abs_path / name).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None

        pkg = read_json("package.json")
        rojo = read_json("project.json") or read_json("default.project.json")
        pyproject = (abs_path / "pyproject.toml").exists()
        ptype = "roblox-rojo" if rojo else "node" if pkg else "python" if pyproject else (
            "python" if any(f.endswith(".py") for f in files) else "unknown")
        return {
            "path": str(args.get("path", ".")), "type": ptype, "fileCount": len(files), "byExtension": by_ext,
            "packageJson": ({"name": pkg.get("name"), "version": pkg.get("version"),
                             "scripts": pkg.get("scripts"), "dependencies": pkg.get("dependencies")} if pkg else None),
            "pyproject": pyproject,
            "rojoProject": rojo,
            "topLevel": [f for f in files if "/" not in f][:100],
        }

    async def project_analyze(args: dict, ctx) -> dict:
        from ..roblox.luau import analyze_luau

        abs_path = sandbox_resolve(ctx.config.workspace_root, str(args.get("path", ".")))
        files: list[str] = []
        _walk(ctx.config.workspace_root, abs_path, files, 0, 6)
        luau_files = [f for f in files if f.endswith((".luau", ".lua"))]
        luau_issues: list[dict] = []
        for f in luau_files[:200]:
            try:
                src = (ctx.config.workspace_root / f).read_text(encoding="utf-8")
                for issue in analyze_luau(src, f):
                    luau_issues.append({"file": f, **issue.to_dict()})
            except OSError:
                continue
        todos: list[dict] = []
        for f in files[:2000]:
            if Path(f).suffix.lower() not in TEXT_EXTS:
                continue
            try:
                for i, line in enumerate((ctx.config.workspace_root / f).read_text(encoding="utf-8").split("\n")):
                    if re.search(r"TODO|FIXME|HACK", line):
                        todos.append({"file": f, "line": i + 1, "text": line.strip()[:200]})
            except OSError:
                continue
        return {
            "path": str(args.get("path", ".")), "fileCount": len(files),
            "luauFiles": len(luau_files), "luauIssues": luau_issues[:200],
            "luauErrorCount": sum(1 for i in luau_issues if i["severity"] == "error"),
            "todos": todos[:100],
        }

    reg.register(ToolDef("file_list",
                         "List files in a directory inside the workspace (recursive up to depth). "
                         "Sandboxed: cannot escape the workspace root.",
                         {"path": {"type": "string", "default": "."},
                          "recursive": {"type": "boolean", "default": True},
                          "maxDepth": {"type": "integer", "default": 4, "minimum": 1, "maximum": 8}},
                         [], 1, "files", True, file_list))
    reg.register(ToolDef("file_read",
                         "Read a text file inside the workspace. Binary files and files over the size limit "
                         "are rejected with a clear error.",
                         {"path": {"type": "string"},
                          "offset": {"type": "integer", "default": 1, "minimum": 1},
                          "limit": {"type": "integer", "default": 2000, "minimum": 1, "maximum": 10000}},
                         ["path"], 1, "files", True, file_read))
    reg.register(ToolDef("file_search",
                         "Search file contents (regex) across the workspace. Returns matching files with line "
                         "numbers and snippets. Skips node_modules/.git/dist/.venv.",
                         {"pattern": {"type": "string"}, "path": {"type": "string", "default": "."},
                          "glob": {"type": "string", "description": "Optional extension filter e.g. .luau"},
                          "maxResults": {"type": "integer", "default": 100, "minimum": 1, "maximum": 500}},
                         ["pattern"], 1, "files", True, file_search))
    reg.register(ToolDef("file_create",
                         "Create a new file inside the workspace (parent dirs created). Fails if the file "
                         "already exists — use file_update to modify.",
                         {"path": {"type": "string"}, "content": {"type": "string"}},
                         ["path", "content"], 3, "files", False, file_create))
    reg.register(ToolDef("file_update",
                         "Create or overwrite a file inside the workspace. Always backs up the previous "
                         "version to the data dir first (reversible).",
                         {"path": {"type": "string"}, "content": {"type": "string"}},
                         ["path", "content"], 3, "files", False, file_update))
    reg.register(ToolDef("file_backup",
                         "Manually back up a workspace file to the data dir. Returns the backup path.",
                         {"path": {"type": "string"}}, ["path"], 2, "files", False, file_backup))
    reg.register(ToolDef("file_delete",
                         "Delete a workspace file after backing it up. Level 4: requires confirm=true. "
                         "Directories are never deleted.",
                         {"path": {"type": "string"}, "confirm": {"type": "boolean", "default": False}},
                         ["path"], 4, "files", False, file_delete))
    reg.register(ToolDef("project_inspect",
                         "Inspect a project directory: file tree summary, detected project type "
                         "(Node/Rojo/Roblox/Python), entry points, package.json / project.json contents.",
                         {"path": {"type": "string", "default": "."}}, [], 1, "project", True, project_inspect))
    reg.register(ToolDef("project_analyze",
                         "Analyze a project: counts Luau files, runs Luau static analysis on every .luau file, "
                         "reports TODOs and dependency health.",
                         {"path": {"type": "string", "default": "."}}, [], 1, "project", True, project_analyze))
