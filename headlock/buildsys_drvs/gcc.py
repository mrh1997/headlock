import subprocess
import os
from pathlib import Path

from typing import Dict, List, Any
from . import BuildDescription, BuildError


BUILD_CACHE = set()


class GccBuildDescription(BuildDescription):

    SYS_INCL_DIR_CACHE:Dict[Path, List[Path]] = {}

    ADDITIONAL_COMPILE_OPTIONS = []
    ADDITIONAL_LINK_OPTIONS = []

    def __init__(self, name:str, build_dir:Path, unique_name=True, *,
                 c_sources:List[Path]=None, predef_macros:Dict[str, Any]=None,
                 incl_dirs:List[Path]=None, lib_dirs:List[Path]=None,
                 req_libs:List[str]=None, gcc_executable='gcc'):
        super().__init__(name, build_dir, unique_name)
        self.gcc_executable = gcc_executable
        self.__c_sources = c_sources or []
        self.__incl_dirs = incl_dirs or []
        self.__req_libs = req_libs or []
        self.__lib_dirs = lib_dirs or []
        self.__predef_macros = {}
        self.add_predef_macros(predef_macros or {})

    def add_c_source(self, c_filename:Path):
        if c_filename in self.__c_sources:
            raise ValueError(f'Translation Unit {c_filename!r} is already part '
                             f'of BuildDescription')
        self.__c_sources.append(c_filename)

    def add_predef_macros(self, predef_macros:Dict[str, Any]):
        for name, val in predef_macros.items():
            self.__predef_macros[name] = str(val) if val is not None else None

    def add_incl_dir(self, incl_dir:Path):
        self.__incl_dirs.append(incl_dir)

    def add_lib_dir(self, lib_dir:Path):
        self.__lib_dirs.append(lib_dir)

    def add_req_lib(self, lib_name:str):
        self.__req_libs.append(lib_name)

    def sys_incl_dirs(self):
        if self.gcc_executable not in self.SYS_INCL_DIR_CACHE:
            try:
                gcc_info = subprocess.check_output(
                    [self.gcc_executable,
                     '-v', '-xc', '-c', '/dev/null', '-o', '/dev/null'],
                    stderr=subprocess.STDOUT,
                    encoding='utf8')
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                raise BuildError('failed to retrieve SYS include path from gcc')
            else:
                incl_dirs = self.SYS_INCL_DIR_CACHE[self.gcc_executable] = []
                collecting = False
                for line in gcc_info.splitlines():
                    if line.startswith('#include <...> search starts here'):
                        collecting = True
                    elif line.startswith('End of search list.'):
                        collecting = False
                    elif collecting:
                        incl_dirs.append(Path(line.strip()))
        return self.SYS_INCL_DIR_CACHE[self.gcc_executable]

    def c_sources(self):
        return self.__c_sources

    def predef_macros(self):
        return dict.fromkeys(self.__c_sources, self.__predef_macros)

    def incl_dirs(self):
        return dict.fromkeys(self.__c_sources, self.__incl_dirs)

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

    def exe_path(self):
        return self.build_dir / '__headlock__.dll'

    def build(self, additonal_c_sources=None):
        transunits = (tuple(self.__c_sources),
                      tuple(self.__predef_macros.items()),
                      tuple(self.__incl_dirs),
                      tuple(self.__req_libs),
                      tuple(self.__lib_dirs))
        if (tuple(transunits), self.build_dir) in BUILD_CACHE:
            return
        total_sources = self.__c_sources + (additonal_c_sources or [])
        for c_src in total_sources:
            if self.is_header_file(c_src):
                continue
            obj_file_path = self.build_dir / (c_src.stem + '.o')
            self._run_gcc(['-c', os.fspath(c_src)]
                          + ['-o', os.fspath(obj_file_path)]
                          + ['-I' + os.fspath(incl_dir)
                             for incl_dir in self.__incl_dirs]
                          + [f'-D{mname}={mval or ""}'
                             for mname, mval in self.__predef_macros.items()]
                          + ['-Werror']
                          + self.ADDITIONAL_COMPILE_OPTIONS,
                          obj_file_path)
        exe_file_path = self.exe_path()
        self._run_gcc([str(self.build_dir / (c_src.stem + '.o'))
                       for c_src in total_sources
                       if not self.is_header_file(c_src)]
                      + ['-shared', '-o', os.fspath(exe_file_path)]
                      + ['-l' + str(req_lib) for req_lib in self.__req_libs]
                      + ['-L' + str(lib_dir) for lib_dir in self.__lib_dirs]
                      + ['-Werror']
                      + self.ADDITIONAL_LINK_OPTIONS,
                      exe_file_path)
        BUILD_CACHE.add((tuple(transunits), self.build_dir))


# Platform-specific base classes

class GccLinuxBuildDescription(GccBuildDescription):
    """Base class for Linux builds"""
    def exe_path(self):
        return self.build_dir / '__headlock__.so'


class GccMacOSBuildDescription(GccBuildDescription):
    """Base class for macOS builds"""
    def exe_path(self):
        return self.build_dir / '__headlock__.dylib'


# Architecture-specific implementations

class GccLinux32BuildDescription(GccLinuxBuildDescription):
    def clang_target(self):
        return 'i386-pc-linux-gnu'


class GccLinux64BuildDescription(GccLinuxBuildDescription):
    ADDITIONAL_COMPILE_OPTIONS = ['-fPIC']
    def clang_target(self):
        return 'x86_64-pc-linux-gnu'


class GccMacOS64BuildDescription(GccMacOSBuildDescription):
    ADDITIONAL_COMPILE_OPTIONS = ['-fPIC']
    def clang_target(self):
        return 'x86_64-apple-darwin'


class GccMacOSArm64BuildDescription(GccMacOSBuildDescription):
    ADDITIONAL_COMPILE_OPTIONS = ['-fPIC']
    def clang_target(self):
        return 'arm64-apple-darwin'


# Backward compatibility aliases (deprecated)
Gcc32BuildDescription = GccLinux32BuildDescription
Gcc64BuildDescription = GccLinux64BuildDescription
