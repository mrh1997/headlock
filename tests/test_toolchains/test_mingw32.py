import pytest
import ctypes

from ..helpers import build_tree

from headlock.testsetup import TransUnit
from headlock.toolchains.mingw32 import MinGW32ToolChain



class TestMinGW32ToolChain:

    def test_build_createsDll(self, tmpdir):
        basedir = build_tree(tmpdir, {'src.c': b'int func(void) { return 22; }',
                                      'build': {}})
        toolchain = MinGW32ToolChain(architecture='i686')
        toolchain.build([TransUnit('', basedir / 'src.c', [], {})],
                        basedir / 'build', 'xyz')
        dll = ctypes.CDLL(str(toolchain.exe_path(basedir / 'build', 'xyz')))
        assert dll.func() == 22
