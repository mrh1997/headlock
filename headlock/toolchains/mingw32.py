import subprocess
import os
from pathlib import Path
import winreg
import itertools
import fnmatch

from ..testsetup import ToolChainDriver, BuildError


class MinGW32ToolChain(ToolChainDriver):

    CLANG_TARGET = 'i386-pc-mingw32'
    ADDITIONAL_COMPILE_OPTIONS = []
    ADDITIONAL_LINK_OPTIONS = []

    def __init__(self, architecture=None, version=None, thread_model=None,
                 exception_model=None, rev=None, mingw_install_dir=None):
        super().__init__()
        if mingw_install_dir is None:
            self.mingw_install_dir = self._autodetect_mingw_dir(
                architecture, version, thread_model, exception_model, rev)
        else:
            self.mingw_install_dir = mingw_install_dir

    def _autodetect_mingw_dir(
            self, architecture, version, thread_model, exception_model, rev):
        def iter_uninstall_progkeys():
            uninst_keyname = r"SOFTWARE\WOW6432Node\Microsoft\Windows" \
                                r"\CurrentVersion\Uninstall"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, uninst_keyname) \
                    as uninst_key:
                for ndx in itertools.count(0):
                    try:
                        subkey_name = winreg.EnumKey(uninst_key, ndx)
                    except OSError:
                        break
                    if not subkey_name.startswith('{'):
                        with winreg.OpenKey(uninst_key, subkey_name) as subkey:
                            yield subkey_name, subkey

        mingw_filter = f"{architecture or '*'}-{version or '*'}" \
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
        return mingw_install_dir / 'mingw32'

    def sys_incl_dirs(self):
        return [self.mingw_install_dir / 'i686-w64-mingw32/include']

    def _run_gcc(self, call_params, dest_file):
        try:
            completed_proc = subprocess.run(
                [str(self.mingw_install_dir / 'bin' / 'gcc')] + call_params,
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
                             for mname, mval in tu.predef_macros.items()]
                          + self.ADDITIONAL_COMPILE_OPTIONS,
                          obj_file_path)
        exe_file_path = self.exe_path(build_dir, name)
        self._run_gcc([str(build_dir / (tu.abs_src_filename.stem + '.o'))
                       for tu in transunits]
                      + ['-shared', '-o', os.fspath(exe_file_path)]
                      + self.ADDITIONAL_LINK_OPTIONS,
                      exe_file_path)
