from pathlib import Path
import winreg
import itertools
import fnmatch

from . import BuildError
from .gcc import GccToolChain


BUILD_CACHE = set()


class MinGWToolChain(GccToolChain):

    ADDITIONAL_COMPILE_OPTIONS = []
    ADDITIONAL_LINK_OPTIONS = ['-static-libgcc', '-static-libstdc++']

    ARCHITECTURE:str = None

    def __init__(self, version=None, thread_model=None,
                 exception_model=None, rev=None, mingw_install_dir=None):
        super().__init__()
        if mingw_install_dir is None:
            self.mingw_install_dir = self._autodetect_mingw_dir(
                version, thread_model, exception_model, rev)
        else:
            self.mingw_install_dir = mingw_install_dir
        self.gcc_executable = str(self.mingw_install_dir / 'bin' / 'gcc')

    def _autodetect_mingw_dir(self,version, thread_model, exception_model, rev):
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

        mingw_filter = f"{self.ARCHITECTURE}-{version or '*'}" \
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

        arch, plat, compiler = self.CLANG_TARGET.split('-')
        return mingw_install_dir / compiler

    def sys_incl_dirs(self):
        ext_incl_dir_base = self.mingw_install_dir \
                            / f'lib/gcc/{self.ARCHITECTURE}-w64-mingw32'
        return [self.mingw_install_dir
                / f'{self.ARCHITECTURE}-w64-mingw32/include'] \
               + list(ext_incl_dir_base.glob('*.*.*/include'))[:1]


class MinGW32ToolChain(MinGWToolChain):
    CLANG_TARGET = 'i386-pc-mingw32'
    ARCHITECTURE = 'i686'


class MinGW64ToolChain(MinGWToolChain):
    CLANG_TARGET = 'x86_64-pc-mingw64'
    ARCHITECTURE = 'x86_64'
