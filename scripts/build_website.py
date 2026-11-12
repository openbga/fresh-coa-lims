"""Build the static presentation website into build/website using the shared UI assets."""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    destination = ROOT / "build" / "website"
    assets = destination / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "style.css"):
        shutil.copyfile(ROOT / "website" / name, destination / name)
    for source, name in (
        ("static/vendor/bootstrap-5.3.8/css/bootstrap.min.css", "bootstrap.min.css"),
        ("static/vendor/bootstrap-5.3.8/css/bootstrap.min.css.map", "bootstrap.min.css.map"),
        # The MIT licence requires its notice to travel with copies of Bootstrap.
        ("static/vendor/bootstrap-5.3.8/LICENSE", "bootstrap.LICENSE.txt"),
        ("static/css/app.css", "app.css"),
        ("static/img/mark.svg", "mark.svg"),
    ):
        shutil.copyfile(ROOT / source, assets / name)
    print(f"Built OpenBGA Fresh CoA LIMS presentation: {destination}")


if __name__ == "__main__":
    main()
