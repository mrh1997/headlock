import pytest
import sys
import subprocess
from unittest.mock import patch
from headlock.toolchains.gcc import GccToolChain
import platform
from pathlib import Path
import ctypes as ct

from ..helpers import build_tree
from headlock.testsetup import TransUnit
if platform.architecture()[0] == '32bit':
    from headlock.toolchains.gcc import Gcc32ToolChain as GccXXToolChain
else:
    from headlock.toolchains.gcc import Gcc64ToolChain as GccXXToolChain


class TestGccToolChain:

    @patch('subprocess.check_output', return_value=
        'Using built-in specs.\n'
        'COLLECT_GCC=gcc\n'
        '...\n'
        'ignoring nonexistent directory "/usr/lib/gcc/x86_64-linux-gnu/7/../../../../x86_64-linux-gnu/include"\n'
        '#include "..." search starts here:\n'
        '#include <...> search starts here:\n'
        ' /usr/lib/gcc/x86_64-linux-gnu/7/include\n'
        ' /usr/local/include\n'
        ' /usr/lib/gcc/x86_64-linux-gnu/7/include-fixed\n'
        ' /usr/include/x86_64-linux-gnu\n'
        ' /usr/include\n'
        'End of search list.\n'
        '...\n')
    def test_sysInclDirs_returnsSysInclDirsReturnedByGcc(self, check_output):
        assert GccToolChain().sys_incl_dirs() == [
            Path('/usr/lib/gcc/x86_64-linux-gnu/7/include'),
            Path('/usr/local/include'),
            Path('/usr/lib/gcc/x86_64-linux-gnu/7/include-fixed'),
            Path('/usr/include/x86_64-linux-gnu'),
            Path('/usr/include')]
        check_output.assert_called_with(
            ['gcc', '-v', '-xc', '-c', '/dev/null', '-o', '/dev/null'],
            encoding='utf8', stderr=subprocess.STDOUT)

    @patch('subprocess.run')
    @patch.object(GccXXToolChain, 'ADDITIONAL_COMPILE_OPTIONS', ['-O1','-Cx'])
    @patch.object(GccXXToolChain, 'ADDITIONAL_LINK_OPTIONS', ['-O2','-Lx'])
    def test_build_passesParametersToGcc(self, subprocess_run):
        subprocess_run.return_value.returncode = 0
        toolchain = GccXXToolChain()
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

    @pytest.mark.skipif(sys.platform == 'win32',
                        reason='works only on non-win platforms')
    def test_build_createsDll(self, tmpdir):
        basedir = build_tree(tmpdir, {'src.c': b'int func(void) { return 22; }',
                                      'build': {}})
        toolchain = GccXXToolChain()
        toolchain.build('xyz', basedir / 'build',
                        [TransUnit('', basedir / 'src.c')], [], [])
        dll = ct.CDLL(str(toolchain.exe_path('xyz', basedir / 'build')))
        assert dll.func() == 22
