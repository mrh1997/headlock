import pytest
import sys
import subprocess
from unittest.mock import patch
from headlock.buildsys_drvs.gcc import GccBuildDescription
import platform
from pathlib import Path
import ctypes as ct

from ..helpers import build_tree
if platform.architecture()[0] == '32bit':
    from headlock.buildsys_drvs.gcc import Gcc32BuildDescription as GccXXBuildDescription
else:
    from headlock.buildsys_drvs.gcc import Gcc64BuildDescription as GccXXBuildDescription


class TestGccBuildDescription:

    def test_init_withoutParams_createsEmptyBuilddesc(self):
        builddesc = GccBuildDescription('dummy', Path('.'))
        assert builddesc.c_sources() == []
        assert builddesc.predef_macros() == {}
        assert builddesc.incl_dirs() == {}

    def test_init_withParams_createsPreinitializedBuilddesc(self):
        predef_macros = {'m1': 'v1', 'm2': 'v2'}
        incl_dirs = [Path('dir/1'), Path('dir/2')]
        builddesc = GccBuildDescription(
            'dummy', Path('.'),
            c_sources=[Path('src1.c'), Path('src2.c')],
            predef_macros=predef_macros, incl_dirs=incl_dirs)
        assert builddesc.c_sources() == [Path('src1.c'), Path('src2.c')]
        assert builddesc.predef_macros() \
               == {Path('src1.c'): predef_macros, Path('src2.c'): predef_macros}
        assert builddesc.incl_dirs() \
               == {Path('src1.c'): incl_dirs, Path('src2.c'): incl_dirs}

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
        GccBuildDescription.SYS_INCL_DIR_CACHE = {}
        assert GccBuildDescription('dummy', Path('.')).sys_incl_dirs() == [
            Path('/usr/lib/gcc/x86_64-linux-gnu/7/include'),
            Path('/usr/local/include'),
            Path('/usr/lib/gcc/x86_64-linux-gnu/7/include-fixed'),
            Path('/usr/include/x86_64-linux-gnu'),
            Path('/usr/include')]
        check_output.assert_called_with(
            ['gcc', '-v', '-xc', '-c', '/dev/null', '-o', '/dev/null'],
            encoding='utf8', stderr=subprocess.STDOUT)

    def test_addCSources_addsCSources(self):
        builddesc = GccBuildDescription('dummy', Path('.'),
                                        c_sources=[Path('src1.c')])
        builddesc.add_c_source(Path('src2.c'))
        assert set(builddesc.c_sources()) == {Path('src1.c'), Path('src2.c')}

    def test_addPredefMacros_addsMacros(self):
        builddesc = GccBuildDescription(
            'dummy', Path('.'), c_sources=[Path('src.c')],
            predef_macros={'m1': 'old', 'm2': 'old'})
        builddesc.add_predef_macros({'m2': 'new', 'm3': 'new'})
        assert builddesc.predef_macros() \
               == {Path('src.c'): {'m1': 'old', 'm2': 'new', 'm3': 'new'}}

    def test_addInclDirs_addsInclDirs(self):
        builddesc = GccBuildDescription(
            'dummy', Path('.'), c_sources=[Path('src.c')],
            incl_dirs=[Path('dir/1')])
        builddesc.add_incl_dir(Path('dir/2'))
        assert builddesc.incl_dirs() \
               == {Path('src.c'): [Path('dir/1'), Path('dir/2')]}

    @patch('subprocess.run')
    @patch.object(GccXXBuildDescription, 'ADDITIONAL_COMPILE_OPTIONS', ['-O1', '-Cx'])
    @patch.object(GccXXBuildDescription, 'ADDITIONAL_LINK_OPTIONS', ['-O2', '-Lx'])
    def test_build_passesParametersToGcc(self, subprocess_run):
        subprocess_run.return_value.returncode = 0
        builddesc = GccXXBuildDescription('dummy', Path('.'))
        builddesc.add_c_source(Path('src.c'))
        builddesc.add_predef_macros({'MACRO1': 1, 'MACRO2':''})
        builddesc.add_incl_dir(Path('incl_dir'))
        builddesc.add_lib_dir(Path('lib_dir'))
        builddesc.add_req_lib('lib_name')
        builddesc.build()
        ((gcc_call, *_), *_), ((linker_call, *_), *_) = \
            subprocess_run.call_args_list
        assert '-Cx' in gcc_call
        assert '-O1' in gcc_call
        assert '-O2' not in gcc_call
        assert '-DMACRO1=1' in gcc_call
        assert '-DMACRO2=' in gcc_call
        assert '-Iincl_dir' in gcc_call
        assert 'src.c' in gcc_call
        assert '-Lx' in linker_call
        assert '-O2' in linker_call
        assert '-llib_name' in linker_call
        assert '-Llib_dir' in linker_call
        assert '-O1' not in linker_call
        assert 'src.o' in linker_call

    @patch('subprocess.run')
    def test_build_passesAdditonalSourcesToGcc(self, subprocess_run):
        subprocess_run.return_value.returncode = 0
        builddesc = GccXXBuildDescription('dummy', Path('.'))
        builddesc.add_c_source(Path('src.c'))
        builddesc.build([Path('additional_src.c')])
        ((gcc1_call, *_), *_), ((gcc2_call, *_), *_), ((linker_call, *_), *_) =\
            subprocess_run.call_args_list
        assert 'src.c' in gcc1_call
        assert 'additional_src.c' in gcc2_call
        assert 'src.o' in linker_call
        assert 'additional_src.o' in linker_call

    @pytest.mark.skipif(sys.platform == 'win32',
                        reason='works only on non-win platforms')
    def test_build_createsDll(self, tmpdir):
        basedir = build_tree(tmpdir, {'src.c': b'int func(void) { return 22; }',
                                      'build': {}})
        builddesc = GccXXBuildDescription('dummy', basedir / 'build')
        builddesc.add_c_source(basedir / 'src.c')
        builddesc.build()
        c_dll = ct.CDLL(str(builddesc.exe_path()))
        assert c_dll.func() == 22
