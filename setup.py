#!python3.10
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
              'headlock.buildsys_drvs'],
    install_requires=[
        'libclang>=18.1.1,<19.0.0',
    ],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX :: Linux',
        'Operating System :: MacOS',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: 3.14',
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
