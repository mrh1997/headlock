import subprocess
import os
from pathlib import Path


from . import ToolChainDriver, BuildError


BUILD_CACHE = set()


class GccToolChain(ToolChainDriver):

    ADDITIONAL_COMPILE_OPTIONS = []
    ADDITIONAL_LINK_OPTIONS = []

    def __init__(self):
        super().__init__()
        self.gcc_executable = 'gcc'
        self.sys_incl_dir_cache = None

    def sys_incl_dirs(self):
        if self.sys_incl_dir_cache is None:
            try:
                gcc_info = subprocess.check_output(
                    [self.gcc_executable,
                     '-v', '-xc', '-c', '/dev/null', '-o', '/dev/null'],
                    stderr=subprocess.STDOUT,
                    encoding='utf8')
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                raise BuildError('failed to retrieve SYS include path from gcc')
            else:
                self.sys_incl_dir_cache = []
                collecting = False
                for line in gcc_info.splitlines():
                    if line.startswith('#include <...> search starts here'):
                        collecting = True
                    elif line.startswith('End of search list.'):
                        collecting = False
                    elif collecting:
                        self.sys_incl_dir_cache.append(Path(line.strip()))
        return self.sys_incl_dir_cache

    def _run_gcc(self, call_params, dest_file):
        try:
            completed_proc = subprocess.run(
                [self.gcc_executable] + call_params,
                encoding='utf8',
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise BuildError(f'failed to call gcc: {e}', dest_file)
        else:
            if completed_proc.returncode != 0:
                raise BuildError(completed_proc.stderr, dest_file)

    def exe_path(self, name, build_dir):
        return build_dir / '__headlock__.dll'

    def build(self, name, build_dir, transunits, req_libs, lib_dirs):
        if (tuple(transunits), build_dir) in BUILD_CACHE:
            return
        for tu in transunits:
            obj_file_path = build_dir / (tu.abs_src_filename.stem + '.o')
            self._run_gcc(['-c', os.fspath(tu.abs_src_filename)]
                          + ['-o', os.fspath(obj_file_path)]
                          + ['-I' + os.fspath(incl_dir)
                             for incl_dir in tu.abs_incl_dirs]
                          + [f'-D{mname}={mval or ""}'
                             for mname, mval in tu.predef_macros.items()]
                          + self.ADDITIONAL_COMPILE_OPTIONS,
                          obj_file_path)
        exe_file_path = self.exe_path(name, build_dir)
        self._run_gcc([str(build_dir / (tu.abs_src_filename.stem + '.o'))
                       for tu in transunits]
                      + ['-shared', '-o', os.fspath(exe_file_path)]
                      + ['-l' + req_lib for req_lib in req_libs]
                      + ['-L' + str(lib_dir) for lib_dir in lib_dirs]
                      + self.ADDITIONAL_LINK_OPTIONS,
                      exe_file_path)
        BUILD_CACHE.add((tuple(transunits), build_dir))


class Gcc32ToolChain(GccToolChain):
    CLANG_TARGET = 'i386-pc-linux-gnu'


class Gcc64ToolChain(GccToolChain):
    CLANG_TARGET = 'x86_64-pc-linux-gnu'
    ADDITIONAL_COMPILE_OPTIONS = ['-fPIC']
