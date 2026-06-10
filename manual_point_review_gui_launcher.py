from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from manual_point_review import DEFAULT_POINTS_CSV, read_csv_rows


def log_file() -> Path:
    return executable_dir().parent / "CrackWidthManualReview.log"


def write_log(message: str) -> None:
    try:
        with log_file().open("a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n")
    except Exception:
        pass


def executable_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def default_points_csv() -> Path:
    exe_dir = executable_dir()
    candidates = [
        Path.cwd() / DEFAULT_POINTS_CSV,
        exe_dir / DEFAULT_POINTS_CSV,
        exe_dir.parent / DEFAULT_POINTS_CSV,
        Path(__file__).resolve().parent / DEFAULT_POINTS_CSV,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the crack-width point-level manual review GUI.")
    parser.add_argument("--points-csv", type=Path, default=None)
    parser.add_argument("--self-test", action="store_true", help="Check whether the default review CSV can be loaded.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    points_csv = args.points_csv or default_points_csv()
    write_log("=" * 60)
    write_log(f"exe={sys.executable}")
    write_log(f"cwd={Path.cwd()}")
    write_log(f"points_csv={points_csv}")
    if args.self_test:
        rows = read_csv_rows(points_csv)
        message = f"OK: {points_csv} rows={len(rows)}"
        write_log(message)
        print(message)
        return 0
    if not points_csv.exists():
        raise FileNotFoundError(
            f"Cannot find review CSV: {points_csv}\n"
            "Keep this exe in the project folder or pass --points-csv explicitly."
        )
    from manual_point_review_pyside import run_pyside_gui

    return run_pyside_gui(points_csv, log=write_log)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        write_log(detail)
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "CrackWidthManualReview 启动失败",
                f"{exc}\n\n详细日志：{log_file()}",
            )
            root.destroy()
        except Exception:
            pass
        raise
