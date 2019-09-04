#!/usr/bin/env python

# Get version without importing boardfarm because
# dependencies may not be installed yet
import os
g, ver = {}, {}
with open(os.path.join("boardfarm","version.py")) as f:
    exec(f.read(), g, ver)

from setuptools import setup, find_packages

setup(name='boardfarm',
      version=ver['__version__'],
      description='Automated testing of network devices',
      author='Various',
      url='https://github.com/lgirdk/boardfarm',
      packages=find_packages(),
      package_data={'': ['*.txt','*.json','*.cfg','*.md','*.tcl']},
      include_package_data=True,
      entry_points = {
        'console_scripts': ['bft=boardfarm.bft:main'],
      }
     )
