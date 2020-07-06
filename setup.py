#!/usr/bin/env python

# Get version without importing boardfarm because
# dependencies may not be installed yet
import os

from setuptools import find_packages, setup

g, ver = {}, {}
with open(os.path.join("boardfarm", "version.py")) as f:
    exec(f.read(), g, ver)

setup(
    name="boardfarm",
    version=ver["__version__"],
    description="Automated testing of network devices",
    author="Various",
    url="https://github.com/lgirdk/boardfarm",
    packages=find_packages(),
    package_data={"": ["*.txt", "*.json", "*.cfg", "*.md", "*.tcl"]},
    include_package_data=True,
    data_files=[(
        "html",
        [
            "boardfarm/html/template_results.html",
            "boardfarm/html/template_results_basic.html",
        ],
    )],
    entry_points={
        "console_scripts": ["bft=boardfarm.bft:main"],
    },
)
