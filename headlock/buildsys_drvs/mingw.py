import os
from pathlib import Path
import itertools
import fnmatch
from typing import List, Dict, Any
try:
    import winreg
except ImportError:
    pass

from . import BuildError, gcc


MINGW_DIR = {
    "mingw32": ("MINGW_I686_DIR", "C:\Program Files (x86)\mingw32"),
    "mingw64": ("MINGW_X86_64_DIR", "C:\Program Files\mingw64")
}

BUILD_CACHE = set()


class MinGWBuildDescription(gcc.GccBuildDescription):

    ADDITIONAL_COMPILE_OPTIONS = []
    ADDITIONAL_LINK_OPTIONS = ['-static-libgcc', '-static-libstdc++']

    ARCHITECTURE:str = None

    def __init__(self, name, build_dir, unique_name=True, *,
                 c_sources:List[Path]=None, predef_macros:Dict[str, Any]=None,
                 incl_dirs:List[Path]=None, lib_dirs:List[Path]=None,
                 req_libs:List[str]=None, version:str=None,
                 thread_model:str=None, exception_model:str=None, rev:str=None,
                 mingw_install_dir:Path=None):
        if mingw_install_dir is not None:
            self.mingw_install_dir = mingw_install_dir
        else:
            arch, plat, compiler = self.clang_target().split('-')
            mingw_dir_varname, mingw_dir_default = MINGW_DIR[compiler]
            if mingw_dir_varname in os.environ:
                self.mingw_install_dir = (
                    Path(os.environ.get(mingw_dir_varname, mingw_dir_default)))
            else:
                try:
                    self.mingw_install_dir = self._autodetect_mingw_dir(
                        version, thread_model, exception_model, rev)  / compiler
                except BuildError:
                    self.mingw_install_dir = Path(mingw_dir_default)
        gcc_executable = self.mingw_install_dir / 'bin' / 'gcc.exe'
        if not gcc_executable.exists():
            raise OSError("MinGW compiler not found: " + str(gcc_executable))
        super().__init__(
            name, build_dir, unique_name,
            c_sources=c_sources, predef_macros=predef_macros,
            incl_dirs=incl_dirs, lib_dirs=lib_dirs, req_libs=req_libs,
            gcc_executable=str(gcc_executable))

    @classmethod
    def _autodetect_mingw_dir(cls, version, thread_model, exception_model, rev):
        def iter_uninstall_progkeys():
            for uninstall_regkey in [r"SOFTWARE\WOW6432Node\Microsoft\Windows"
                                        r"\CurrentVersion\Uninstall",
                                     r"SOFTWARE\Microsoft\Windows"
                                        r"\CurrentVersion\Uninstall"]:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                    uninstall_regkey) as uninst_key:
                    for ndx in itertools.count(0):
                        try:
                            subkey_name = winreg.EnumKey(uninst_key, ndx)
                        except OSError:
                            break
                        if not subkey_name.startswith('{'):
                            with winreg.OpenKey(uninst_key,
                                                subkey_name) as subkey:
                                yield subkey_name, subkey

        mingw_filter = f"{cls.ARCHITECTURE}-{version or '*'}" \
                       f"-{thread_model or '*'}-{exception_model or '*'}" \
                       f"-*-{rev or '*'}"
        mingw_install_dirs = {}
        for progkey_name, progkey in iter_uninstall_progkeys():
            try:
                publisher_name, publisher_type = \
                    winreg.QueryValueEx(progkey, "Publisher")
                install_dir, install_dir_type = \
                    winreg.QueryValueEx(progkey, "InstallLocation")
            except OSError:
                pass
            else:
                install_dir_path = Path(install_dir)
                if install_dir_type == publisher_type == winreg.REG_SZ \
                        and publisher_name == 'MinGW-W64' \
                        and install_dir_path.exists() \
                        and fnmatch.fnmatch(install_dir_path.name,mingw_filter):
                    mingw_install_dirs[progkey_name] = install_dir_path

        if len(mingw_install_dirs) == 0:
            raise BuildError(
                f'Requested MinGW Version ({mingw_filter}) was not found '
                f'on this system')
        _, mingw_install_dir = max(mingw_install_dirs.items())
        return mingw_install_dir

    def sys_incl_dirs(self):
        ext_incl_dir_base = self.mingw_install_dir \
                            / f'lib/gcc/{self.ARCHITECTURE}-w64-mingw32'
        return [self.mingw_install_dir
                / f'{self.ARCHITECTURE}-w64-mingw32/include'] \
               + list(ext_incl_dir_base.glob('*.*.*/include'))[:1]


class MinGW32BuildDescription(MinGWBuildDescription):
    ARCHITECTURE = 'i686'

    def clang_target(self):
        return 'i386-pc-mingw32'


class MinGW64BuildDescription(MinGWBuildDescription):
    ARCHITECTURE = 'x86_64'

    def clang_target(self):
        return 'x86_64-pc-mingw64'
