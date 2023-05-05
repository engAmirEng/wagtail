import io
import json
import os
import subprocess

from setuptools import Command
from setuptools.command.bdist_egg import bdist_egg
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist as base_sdist

from wagtail import __semver__


class assets_mixin:
    def compile_assets(self):
        try:
            subprocess.check_call(["npm", "run", "build"])
        except (OSError, subprocess.CalledProcessError) as e:
            print("Error compiling assets: " + str(e))  # noqa
            raise SystemExit(1)

    def publish_assets(self):
        try:
            subprocess.check_call(["npm", "publish", "client"])
        except (OSError, subprocess.CalledProcessError) as e:
            print("Error publishing front-end assets: " + str(e))  # noqa
            raise SystemExit(1)

    def bump_client_version(self):
        """
        Writes the current Wagtail version number into package.json
        """
        path = os.path.join(".", "client", "package.json")
        input_file = io.open(path, "r")

        try:
            package = json.loads(input_file.read().decode("utf-8"))
        except (ValueError) as e:
            print("Unable to read " + path + " " + e)  # noqa
            raise SystemExit(1)

        package["version"] = __semver__

        try:
            with io.open(path, "w", encoding="utf-8") as f:
                f.write(str(json.dumps(package, indent=2, ensure_ascii=False)))
        except (IOError) as e:
            print("Error setting the version for front-end assets: " + str(e))  # noqa
            raise SystemExit(1)


class assets(Command, assets_mixin):
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        self.bump_client_version()
        self.compile_assets()
        self.publish_assets()


class sdist(base_sdist, assets_mixin):
    def run(self):
        self.compile_assets()
        base_sdist.run(self)


class check_bdist_egg(bdist_egg):

    # If this file does not exist, warn the user to compile the assets
    sentinel_dir = "wagtail/wagtailadmin/static/"

    def run(self):
        bdist_egg.run(self)
        if not os.path.isdir(self.sentinel_dir):
            print(  # noqa
                "\n".join(
                    [  # noqa
                        "************************************************************",
                        "The front end assets for Wagtail are missing.",
                        "To generate the assets, please refer to the documentation in",
                        "docs/contributing/developing.md",
                        "************************************************************",
                    ]
                )
            )


class PipStaticBuild(build_py):
    def run(self):
        import shutil

        try:
            res, err = subprocess.Popen(
                [shutil.which("npm"), "install", "-y"],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
            ).communicate()
            print(f"npm install:err: {err}")
            print(f"npm install:res: {res}")
        except Exception as e:
            print("error during npm install: ", e)
            raise
        try:
            res, err = subprocess.Popen(
                [shutil.which("npm"), "run", "build"],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
            ).communicate()
            print(f"npm run build:err: {err}")
            print(f"npm run build:res: {res}")
        except Exception as e:
            print("error during npm run build: ", e)
            raise
        build_py.run(self)
