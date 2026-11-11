"""Build the static presentation into .local/website using the shared UI assets."""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    destination = ROOT / ".local" / "website"
    assets = destination / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "style.css"):
        shutil.copyfile(ROOT / "website" / name, destination / name)
    for source, name in (
        ("static/vendor/bootstrap-5.3.8/css/bootstrap.min.css", "bootstrap.min.css"),
        ("static/vendor/bootstrap-5.3.8/css/bootstrap.min.css.map", "bootstrap.min.css.map"),
        ("static/css/app.css", "app.css"),
        ("static/img/mark.svg", "mark.svg"),
    ):
        shutil.copyfile(ROOT / source, assets / name)
    print(f"Built OpenBGA Qualab presentation: {destination}")


if __name__ == "__main__":
    main()
