import os
import sys
import pytcc
from pathlib import Path

from typing import Dict, List, Any
from . import BuildDescription, BuildError


class PyTccBuildDescription(BuildDescription):

    SYS_INCL_DIR_CACHE:Dict[Path, List[Path]] = {}

    def __init__(self, name:str, build_dir:Path, unique_name=True, *,
                 c_sources:List[Path]=None, predef_macros:Dict[str, Any]=None,
                 incl_dirs:List[Path]=None, lib_dirs:List[Path]=None,
                 req_libs:List[str]=None):
        super().__init__(name, build_dir, unique_name)
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
        return [sys_incl_dir
                for sys_incl_dir in pytcc.TCC_LIB_PATH.glob("include/**/*")
                if sys_incl_dir.is_dir()]

    def c_sources(self):
        return self.__c_sources

    def predef_macros(self):
        return dict.fromkeys(self.__c_sources, self.__predef_macros)

    def incl_dirs(self):
        return dict.fromkeys(self.__c_sources, self.__incl_dirs)

    def exe_path(self):
        return self.build_dir / '__headlock__.dll'

    def build(self, additonal_c_sources=None):
        total_sources = [
            os.fspath(c_src)
            for c_src in self.__c_sources + (additonal_c_sources or [])
            if not self.is_header_file(c_src)]
        tcc = pytcc.TCC(
            '-rdynamic',
            include_dirs=list(map(os.fspath, self.__incl_dirs)),
            lib_dirs=self.__lib_dirs,
            **self.__predef_macros)
        tcc.build_to_lib(os.fspath(self.exe_path()), *total_sources)

    def clang_target(self):
        if sys.platform == "win32":
            if sys.maxsize > 2 ** 32:
                return 'x86_64-pc-mingw64'
            else:
                return 'i386-pc-mingw32'
        else:
            if sys.maxsize > 2 ** 32:
                return 'x86_64-pc-linux-gnu'
            else:
                return 'i386-pc-linux-gnu'
