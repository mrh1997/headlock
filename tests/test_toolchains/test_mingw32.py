import pytest
import ctypes
from pathlib import Path
from unittest.mock import patch, Mock

from ..helpers import build_tree

from headlock.testsetup import TransUnit
from headlock.toolchains.mingw32 import MinGW32ToolChain



class TestMinGW32ToolChain:

    def test_build_createsDll(self, tmpdir):
        basedir = build_tree(tmpdir, {'src.c': b'int func(void) { return 22; }',
                                      'build': {}})
        toolchain = MinGW32ToolChain(architecture='i686')
        toolchain.build('xyz', basedir / 'build',
                        [TransUnit('', basedir / 'src.c')], [], [])
        dll = ctypes.CDLL(str(toolchain.exe_path('xyz', basedir / 'build')))
        assert dll.func() == 22

    @patch('subprocess.run')
    @patch.object(MinGW32ToolChain, 'ADDITIONAL_COMPILE_OPTIONS', ['-O1','-Cx'])
    @patch.object(MinGW32ToolChain, 'ADDITIONAL_LINK_OPTIONS', ['-O2','-Lx'])
    def test_build_passesParametersToGcc(self, subprocess_run):
        subprocess_run.return_value.returncode = 0
        toolchain = MinGW32ToolChain()
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
