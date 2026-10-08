"""Install the course data pack (not in git) into backend/data/.

The repository excludes the database and product photos. Get the course's data.zip, then run (from hw4/backend):

    .\\.venv\\Scripts\\python.exe setup_data.py path\\to\\data.zip
    # or an already-extracted folder that contains campus_customs.db and products/
    .\\.venv\\Scripts\\python.exe setup_data.py path\\to\\data

It copies:
    data/campus_customs.db  -> backend/data/campus_customs.db
    data/products/*.jpg     -> backend/data/images/products/
Existing files are never overwritten (the database is preserved).
"""

import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"


def find_pack(root: Path) -> Path:
    for db in root.rglob("campus_customs.db"):
        if (db.parent / "products").is_dir():
            return db.parent
    raise SystemExit(f"No campus_customs.db with a products/ folder found in {root}")


def install(pack: Path) -> None:
    (DATA / "images" / "products").mkdir(parents=True, exist_ok=True)
    db_target = DATA / "campus_customs.db"
    if db_target.exists():
        print(f"kept existing {db_target.name}")
    else:
        shutil.copy2(pack / "campus_customs.db", db_target)
        print(f"installed {db_target.name}")
    copied = 0
    for img in (pack / "products").iterdir():
        target = DATA / "images" / "products" / img.name
        if img.is_file() and not target.exists():
            shutil.copy2(img, target)
            copied += 1
    print(f"copied {copied} product images to data/images/products/")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    source = Path(sys.argv[1])
    if source.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory() as tmp:
            zipfile.ZipFile(source).extractall(tmp)
            install(find_pack(Path(tmp)))
    else:
        install(find_pack(source))


if __name__ == "__main__":
    main()
