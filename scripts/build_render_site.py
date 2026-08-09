from __future__ import annotations

import argparse
import shutil
from pathlib import Path


PUBLIC_DIRECTORIES = ("assets", "css", "data", "js", "pages")
PUBLIC_ROOT_FILES = ("index.html",)
FORBIDDEN_NAMES = {".env", "backend", "tests", "__pycache__"}
FORBIDDEN_SUFFIXES = {".db", ".key", ".log", ".pem", ".sqlite", ".sqlite3"}
RUNTIME_CONFIG = """(function (global) {
  'use strict';

  const B = global.Bambiku = global.Bambiku || {};
  B.runtimeConfig = Object.assign({}, B.runtimeConfig || {}, {
    apiBaseUrl: '/api'
  });
})(window);
"""


def build_site(root: Path, output: Path) -> tuple[int, int]:
    root = root.resolve()
    output = output.resolve()
    if output == root or root in output.parents and output.name in PUBLIC_DIRECTORIES:
        raise ValueError("Output directory must not replace a public source directory")

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    for name in PUBLIC_ROOT_FILES:
        source = root / name
        if not source.is_file():
            raise FileNotFoundError(f"Required frontend file is missing: {source}")
        shutil.copy2(source, output / name)

    for name in PUBLIC_DIRECTORIES:
        source = root / name
        if not source.is_dir():
            raise FileNotFoundError(f"Required frontend directory is missing: {source}")
        shutil.copytree(source, output / name)

    runtime_path = output / "js" / "config" / "runtime.js"
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text(RUNTIME_CONFIG, encoding="utf-8", newline="\n")

    files = [path for path in output.rglob("*") if path.is_file()]
    html_files = [path for path in files if path.suffix.lower() == ".html"]
    for path in files:
        relative_parts = {part.lower() for part in path.relative_to(output).parts}
        if relative_parts & FORBIDDEN_NAMES or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            raise RuntimeError(f"Forbidden file entered frontend build: {path.relative_to(output)}")
    if len(html_files) < 2:
        raise RuntimeError("Frontend build does not contain the expected HTML pages")
    return len(files), len(html_files)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the public Bambiku frontend for Render")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output or (root / "dist")
    file_count, html_count = build_site(root, output)
    print(f"Render frontend built: {file_count} files, {html_count} HTML pages -> {output}")


if __name__ == "__main__":
    main()
