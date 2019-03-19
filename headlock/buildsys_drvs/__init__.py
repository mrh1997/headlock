import abc
import hashlib
import os
from pathlib import Path
from typing import List, Dict


class BuildError(Exception):

    def __init__(self, msg, path=None):
        super().__init__(msg)
        self.path = path

    def __str__(self):
        return (f'building {self.path} failed: ' if self.path
                else '') \
               + super().__str__()


class BuildDescription:
    """
    This is an abstract base class for all classes that allow to specify
    C projects
    """

    def __init__(self, name:str, build_dir:Path, unique_name=True):
        """
        Abstract Base Class for Descriptions how to build a bunch of C files
        :param name: Descriptive Name of BuildDescription
        :param build_dir: Directory where all generated files shall be stored
        :param unique_name: If True, a BuildDescription with the same name
                          cannot exist
        """
        self.name = name
        self.__build_dir = build_dir
        self.unique_name = unique_name

    @property
    def build_dir(self):
        if self.unique_name:
            return self.__build_dir
        else:
            hash = hashlib.md5()
            incl_dirs = self.incl_dirs()
            predef_macros = self.predef_macros()
            for c_source in self.c_sources():
                hash.update(os.fsencode(c_source))
                for incl_dir in incl_dirs[c_source]:
                    hash.update(os.fsencode(incl_dir))
                for mname, mvalue in predef_macros[c_source].items():
                    hash.update((mname + '=' + mvalue).encode('ascii'))
            return self.__build_dir.parent \
                   / (self.__build_dir.name + '_' + hash.hexdigest()[:8])

    @abc.abstractmethod
    def clang_target(self) -> str:
        """
        returns a string that represents the "target" parameter of clang
        """
        raise NotImplementedError()

    @abc.abstractmethod
    def sys_incl_dirs(self) -> List[Path]:
        """
        retrieves a list of all system include directories
        """

    def sys_predef_macros(self) -> Dict[str, str]:
        """
        A dictionary of toolchain-inhernt macros, that shall be always
        predefined additionally to the predefined macros provided by clang
        """
        return {}

    def c_sources(self) -> List[Path]:
        """
        returns all C source files
        """

    @abc.abstractmethod
    def incl_dirs(self) -> Dict[Path, List[Path]]:
        """
        returns a list of all source code files.
        :return:
        """

    @abc.abstractmethod
    def predef_macros(self) -> Dict[Path, Dict[str, str]]:
        """
        returns all predefined macros per source file a list of all source code files.
        :return:
        """

    @abc.abstractmethod
    def exe_path(self) -> Path:
        """
        returns name of executable image/shared object library/dll
        """

    @abc.abstractmethod
    def build(self, additonal_c_sources:List[Path]=None):
        """
        builds executable image
        """

    def is_header_file(self, src_path:Path) -> bool:
        """
        Returns True, if this is a header file
        """
        return src_path.suffix.lower() == '.h'
