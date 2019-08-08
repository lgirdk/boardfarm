#!/usr/bin/env python

from setuptools import setup, find_packages

setup(name='boardfarm',
      version='1.0.0',
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
