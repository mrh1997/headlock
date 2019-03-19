import pytest
import sys
import ctypes
import platform
from ..helpers import build_tree

if sys.platform == 'win32':

    if platform.architecture()[0] == '32bit':
        from headlock.buildsys_drvs.mingw import \
            MinGW32BuildDescription as MinGWxxBuildDescription
    else:
        from headlock.buildsys_drvs.mingw import \
            MinGW64BuildDescription as MinGWxxBuildDescription


    class TestMinGW32ToolChain:

        def test_build_createsDll(self, tmpdir):
            basedir = build_tree(tmpdir, {
                'src.c': b'int func(void) { return 22; }',
                'build': {}})
            builddesc = MinGWxxBuildDescription('dummy', basedir / 'build')
            builddesc.add_c_source(basedir / 'src.c')
            builddesc.build()
            dll = ctypes.CDLL(str(builddesc.exe_path()))
            assert dll.func() == 22
