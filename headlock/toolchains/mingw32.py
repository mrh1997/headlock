import subprocess
import os
from pathlib import Path

from ..testsetup import ToolChainDriver, BuildError


class MinGW32ToolChain(ToolChainDriver):

    CLANG_TARGET = 'i386-pc-mingw32'
    DEFAULT_MINGW64_DIR = r'C:\Program Files (x86)\mingw-w64'

    def _get_mingw_dir(self):
        mingwdir = Path(os.environ.get('MINGW64_DIR', self.DEFAULT_MINGW64_DIR))
        envs = list(mingwdir.glob(r'i686-*-*-dwarf-rt_v5-*\mingw32'))
        if not envs:
            raise BuildError(f'no MinGW64 found in {mingwdir} '
                             f'(see MINGW64_DIR environment variable)')
        envs.sort()
        return envs[-1]

    def sys_incl_dirs(self):
        return [str(self._get_mingw_dir() / 'i686-w64-mingw32/include')]

    def _run_gcc(self, call_params, dest_file):
        try:
            completed_proc = subprocess.run(
                [str(self._get_mingw_dir() / 'bin' / 'gcc')] + call_params,
                encoding='ascii',
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise BuildError(f'failed to call gcc: {e}', dest_file)
        else:
            if completed_proc.returncode != 0:
                raise BuildError(completed_proc.stderr, dest_file)

    def exe_path(self, build_dir, name):
        return build_dir / f'{name}.dll'

    def build(self, transunits, build_dir, name):
        for tu in transunits:
            obj_file_path = build_dir / (tu.abs_src_filename.stem + '.o')
            self._run_gcc(['-c', os.fspath(tu.abs_src_filename)]
                          + ['-o', os.fspath(obj_file_path)]
                          + ['-I' + os.fspath(incl_dir)
                             for incl_dir in tu.abs_incl_dirs]
                          + [f'-D{mname}={mval or ""}'
                             for mname, mval in tu.predef_macros.items()],
                          obj_file_path)
        exe_file_path = self.exe_path(build_dir, name)
        self._run_gcc([str(build_dir / (tu.abs_src_filename.stem + '.o'))
                       for tu in transunits]
                      + ['-shared', '-o', os.fspath(exe_file_path)],
                      exe_file_path)
