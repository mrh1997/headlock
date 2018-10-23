import pytest
import ctypes
import platform
from pathlib import Path
from unittest.mock import patch, Mock

from ..helpers import build_tree

from headlock.testsetup import TransUnit
from headlock.toolchains.mingw import MinGW32ToolChain

if platform.architecture()[0] == '32bit':
    from headlock.toolchains.mingw import MinGW32ToolChain as MinGWxxToolChain
else:
    from headlock.toolchains.mingw import MinGW64ToolChain as MinGWxxToolChain


class TestMinGW32ToolChain:

    def test_build_createsDll(self, tmpdir):
        basedir = build_tree(tmpdir, {'src.c': b'int func(void) { return 22; }',
                                      'build': {}})
        toolchain = MinGWxxToolChain()
        toolchain.build('xyz', basedir / 'build',
                        [TransUnit('', basedir / 'src.c')], [], [])
        dll = ctypes.CDLL(str(toolchain.exe_path('xyz', basedir / 'build')))
        assert dll.func() == 22

    @patch('subprocess.run')
    @patch.object(MinGWxxToolChain, 'ADDITIONAL_COMPILE_OPTIONS', ['-O1','-Cx'])
    @patch.object(MinGWxxToolChain, 'ADDITIONAL_LINK_OPTIONS', ['-O2','-Lx'])
    def test_build_passesParametersToGcc(self, subprocess_run):
        subprocess_run.return_value.returncode = 0
        toolchain = MinGWxxToolChain()
        toolchain.build('name', Path('dir'), [TransUnit('', Path('src.c'))],
                        ['lib_name'], [Path('lib_dir')])
        first_call_pos_args, *_ = subprocess_run.call_args_list[0]
        assert '-Cx' in first_call_pos_args[0]
        assert '-O1' in first_call_pos_args[0]
        assert '-O2' not in first_call_pos_args[0]
        second_call_pos_args, *_ = subprocess_run.call_args_list[1]
        assert '-Lx' in second_call_pos_args[0]
        assert '-O2' in second_call_pos_args[0]
        assert '-llib_name' in second_call_pos_args[0]
        assert '-Llib_dir' in second_call_pos_args[0]
        assert '-O1' not in second_call_pos_args[0]
