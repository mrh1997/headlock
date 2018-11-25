import abc
from pathlib import Path
from typing import List, Dict, Any, NamedTuple


class BuildError(Exception):

    def __init__(self, msg, path=None):
        super().__init__(msg)
        self.path = path

    def __str__(self):
        return (f'building {self.path} failed: ' if self.path
                else '') \
               + super().__str__()


class TransUnit(NamedTuple):
    """
    Represents a reference to a "translation unit" which is a unique
    translation of C file. As the preprocessor allows a lot of different
    translations of the same code base (depending on the macros passed by
    command line and the include files) this object provides all information
    to get unique preprocessor runs.
    """
    subsys_name:str
    abs_src_filename:Path
    abs_incl_dirs:List[Path] = []
    predef_macros:Dict[str, Any] = {}

    def __hash__(self):
        return sum(map(hash, [self.subsys_name,
                              self.abs_src_filename,
                              tuple(self.abs_incl_dirs),
                              tuple(sorted(self.predef_macros.items()))]))


class ToolChainDriver:
    """
    This is an abstract base class for all ToolChain-Drivers.
    a toolchain is the compiler, linker, libraries and header files.
    """

    CLANG_TARGET = ''

    def sys_predef_macros(self):
        """
        A dictionary of toolchain-inhernt macros, that shall be always
        predefined additionally to the predefined macros provided by clang
        """
        return {}

    @abc.abstractmethod
    def sys_incl_dirs(self):
        """
        retrieves a list of all system include directories
        """

    @abc.abstractmethod
    def exe_path(self, name:str, build_dir:Path):
        """
        returns name of executable image/shared object library/dll
        """

    @abc.abstractmethod
    def build(self, name:str, build_dir:Path,
              transunits:List[TransUnit], req_libs:List[str],
              lib_dirs:List[Path]):
        """
        builds executable image from translation units 'transunits'
        """
