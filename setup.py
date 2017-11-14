from distutils.core import setup

setup(
    name='headlock',
    version='0.0.1a',
    description='An adapter for making C code testable from Python',
    author='Robert Hoelzl',
    author_email='robert.hoelzl@posteo.de',
    url='https://github.com/mrh1997/headlock',
    packages=['headlock', 'headlock.libclang'],
)
