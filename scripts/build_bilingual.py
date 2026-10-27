#!/usr/bin/env python3
"""Build the English book and an isolated Chinese book for GitHub Pages.

Run from any directory: python scripts/build_bilingual.py
Use --zh-only to build only the Chinese book, or --check to validate inputs.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
import os


ROOT = Path(__file__).resolve().parent.parent
EN_CONFIG = ROOT / "_quarto.yml"
ZH_CONFIG = ROOT / "_quarto-zh.yml"
CHAPTER = re.compile(r"^\s*-\s+(index\.qmd|contents/[^\s]+\.qmd)\s*$", re.MULTILINE)


def chapters(config: Path) -> list[str]:
    return CHAPTER.findall(config.read_text(encoding="utf-8"))


def validate() -> list[str]:
    english = chapters(EN_CONFIG)
    chinese = chapters(ZH_CONFIG)
    if not english or english != chinese:
        raise ValueError("English and Chinese chapter lists must match in order.")
    for name in english:
        for source in (ROOT / name, ROOT / "zh" / name):
            if not source.is_file():
                raise FileNotFoundError(f"Missing chapter: {source}")
    for name in ("language-switch.html", "language-switch.css",
                 "theme-dark.scss", "files/bibliography.bib"):
        if not (ROOT / name).is_file():
            raise FileNotFoundError(f"Missing build input: {name}")
    if not (ROOT / "images").is_dir():
        raise FileNotFoundError("Missing images directory")
    print(f"Validated {len(english)} corresponding chapters.", flush=True)
    missing_images: set[str] = set()
    for name in chinese:
        text = (ROOT / "zh" / name).read_text(encoding="utf-8")
        for image in re.findall(r"\.\./\.\./images/([^\s)\]<>]+)", text):
            if not (ROOT / "images" / image).is_file():
                missing_images.add(image)
    if missing_images:
        print(f"Warning: {len(missing_images)} referenced images are missing:", flush=True)
        for image in sorted(missing_images):
            print(f"  images/{image}", flush=True)
    return chinese


def stage_chinese(stage: Path, chapter_names: list[str]) -> None:
    # The staged root contains only the standalone Chinese configuration,
    # so Quarto cannot merge its chapter list with the English project.
    shutil.copy2(ZH_CONFIG, stage / "_quarto.yml")
    for name in ("language-switch.html", "language-switch.css", "theme-dark.scss"):
        shutil.copy2(ROOT / name, stage / name)
    shutil.copytree(ROOT / "files", stage / "files")
    shutil.copytree(ROOT / "images", stage / "images")
    for name in chapter_names:
        source = ROOT / "zh" / name
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        content = source.read_text(encoding="utf-8")
        # Chinese source chapters are nested one directory deeper than their
        # staged counterparts. Adjust only the temporary copies.
        content = content.replace("../../images/", "../images/")
        target.write_text(content, encoding="utf-8")


def require_outputs(directory: Path, names: list[str]) -> None:
    missing = [name for name in names if not (directory / Path(name).with_suffix(".html")).is_file()]
    if missing:
        raise FileNotFoundError(f"Rendered pages missing from {directory}: {', '.join(missing)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="check inputs without rendering")
    parser.add_argument("--zh-only", action="store_true", help="build Chinese without rendering English")
    args = parser.parse_args()
    names = validate()
    if args.check:
        return
    quarto = shutil.which("quarto")
    if not quarto:
        raise SystemExit("Quarto not found; install it or use --check for static validation.")

    # An inherited profile could merge unrelated configurations into either
    # project; both builds must use their own base configuration.
    env = os.environ.copy()
    env.pop("QUARTO_PROFILE", None)
    with tempfile.TemporaryDirectory(prefix="keynotes-zh-") as temporary:
        stage = Path(temporary)
        stage_chinese(stage, names)
        english_output = ROOT / "docs"
        if not args.zh_only:
            print("Rendering English book (configured formats)...", flush=True)
            subprocess.run([quarto, "render"], cwd=ROOT, env=env, check=True)
            require_outputs(english_output, names)
        print("Rendering isolated Chinese HTML book...", flush=True)
        subprocess.run([quarto, "render", "--to", "html"], cwd=stage, env=env, check=True)
        chinese_output = stage / "_site"
        require_outputs(chinese_output, names)
        # Ensure referenced images are present even when automatic resource
        # discovery does not copy an image mentioned in a complex caption.
        shutil.copytree(stage / "images", chinese_output / "images", dirs_exist_ok=True)
        target = english_output / "zh"
        if target.is_symlink():
            raise RuntimeError(f"Refusing to copy into symlink: {target}")
        english_output.mkdir(parents=True, exist_ok=True)
        shutil.copytree(chinese_output, target, dirs_exist_ok=True)
        require_outputs(target, names)
        print(f"Combined site ready in {english_output}", flush=True)


if __name__ == "__main__":
    main()
