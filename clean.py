import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
INPUT_FILENAME = "input.txt"

CACHE_DIR_NAMES = ("__pycache__", ".pytest_cache", ".ruff_cache")


def remove_cache_dirs() -> list[Path]:
    removed = []
    for name in CACHE_DIR_NAMES:
        for cache_dir in PROJECT_ROOT.rglob(name):
            shutil.rmtree(cache_dir)
            removed.append(cache_dir)
    return removed


def remove_generated_data_files() -> list[Path]:
    if not DATA_DIR.exists():
        return []

    removed = []
    for path in DATA_DIR.iterdir():
        if path.is_file() and path.name != INPUT_FILENAME:
            path.unlink()
            removed.append(path)
    return removed


def main() -> None:
    removed = remove_cache_dirs() + remove_generated_data_files()

    if not removed:
        print("Nothing to clean.")
        return

    for path in removed:
        print(f"Removed {path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
