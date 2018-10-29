import pytest
import sys
import ctypes
import platform
from ..helpers import build_tree

if sys.platform == 'win32':

    from headlock.testsetup import TransUnit
    if platform.architecture()[0] == '32bit':
        from headlock.toolchains.mingw import \
            MinGW32ToolChain as MinGWxxToolChain
    else:
        from headlock.toolchains.mingw import \
            MinGW64ToolChain as MinGWxxToolChain


    class TestMinGW32ToolChain:

        def test_build_createsDll(self, tmpdir):
            basedir = build_tree(tmpdir, {
                'src.c': b'int func(void) { return 22; }',
                'build': {}})
            toolchain = MinGWxxToolChain()
            toolchain.build('xyz', basedir / 'build',
                            [TransUnit('', basedir / 'src.c')], [], [])
            dll = ctypes.CDLL(str(toolchain.exe_path('xyz', basedir / 'build')))
            assert dll.func() == 22
