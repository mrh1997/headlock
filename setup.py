#!python3.6
# -*- coding: utf-8 -*-
from setuptools import setup
from headlock import __version__
from pathlib import Path


README_PATH = Path(__file__).parent / 'README.md'


setup(
    name='headlock',
    version=__version__,
    description='An adapter for making C code testable from Python',
    long_description=README_PATH.read_text(),
    long_description_content_type='text/markdown',
    author='Robert Hölzl',
    author_email='robert.hoelzl@posteo.de',
    url='https://headlock.readthedocs.io/en/latest/index.html',
    packages=['headlock',
              'headlock.address_space',
              'headlock.c_data_model',
              'headlock.integrations.pytest',
              'headlock.libclang',
              'headlock.buildsys_drvs'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Operating System :: Microsoft :: Windows',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: C',
        'Topic :: Software Development :: Testing',
    ],
    entry_points = {
        'pytest11': [
            'headlock-debug-support = '
                      'headlock.integrations.pytest.plugin_headlock_debug',
            'headlock-report-error = '
                     'headlock.integrations.pytest.plugin_headlock_report',
        ]
    },
)
