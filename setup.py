#!python3.6
# -*- coding: utf-8 -*-
from distutils.core import setup
from headlock import __version__
import sys

setup(
    name='headlock',
    version=__version__,
    description='An adapter for making C code testable from Python',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='Robert Hölzl',
    author_email='robert.hoelzl@posteo.de',
    url='https://headlock.readthedocs.io/en/latest/index.html',
    packages=['headlock', 'headlock.libclang', 'headlock.toolchains'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Operating System :: Microsoft :: Windows',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: C',
        'Topic :: Software Development :: Testing',
    ]
)
