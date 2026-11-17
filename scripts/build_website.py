"""Build the static presentation website into build/website using the shared UI assets."""

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    destination = ROOT / "build" / "website"
    assets = destination / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    for name in ("index.html", "roadmap.html", "style.css", "theme.js", "site.js", "icons.svg"):
        shutil.copyfile(ROOT / "website" / name, destination / name)
    for source, name in (
        ("static/vendor/bootstrap-5.3.8/css/bootstrap.min.css", "bootstrap.min.css"),
        ("static/vendor/bootstrap-5.3.8/css/bootstrap.min.css.map", "bootstrap.min.css.map"),
        # The MIT licence requires its notice to travel with copies of Bootstrap.
        ("static/vendor/bootstrap-5.3.8/LICENSE", "bootstrap.LICENSE.txt"),
        ("static/css/app.css", "app.css"),
        ("static/img/mark.svg", "mark.svg"),
        # website/icons.svg holds Bootstrap Icons symbols: their MIT notice travels with them.
        ("static/img/icons.LICENSE", "icons.LICENSE.txt"),
        # The sign-in art doubles as the presentation's scene.
        ("static/img/signin-light.svg", "scene-light.svg"),
        ("static/img/signin-dark.svg", "scene-dark.svg"),
    ):
        shutil.copyfile(ROOT / source, assets / name)
    # app.css loads Archivo from ../vendor/archivo-2.001/, relative to assets/.
    fonts = "static/vendor/archivo-2.001"
    shutil.copytree(ROOT / fonts, destination / "vendor" / "archivo-2.001", dirs_exist_ok=True)
    print(f"Built OpenBGA QM LIMS presentation: {destination}")


if __name__ == "__main__":
    main()
