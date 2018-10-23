import ctypes as ct
import functools
import os
import sys
import weakref
import abc
import hashlib
import copy
import platform
from typing import List, Iterator, Dict, NamedTuple, Any, Tuple, Union

from pathlib import Path

from .c_data_model import BuildInDefs, CStructType, CEnumType, CFuncType, \
    CPointerType
from .c_parser import CParser, ParseError


class BuildError(Exception):

    def __init__(self, msg, path=None):
        super().__init__(msg)
        self.path = path

    def __str__(self):
        return (f'building {self.path} failed: ' if self.path
                else '') \
               + super().__str__()


class CompileError(BuildError):

    def __init__(self, errors, path=None):
        super().__init__(f'{len(errors)} compile errors', path)
        self.errors = errors

    def __iter__(self):
        yield from self.errors



class MethodNotMockedError(Exception):
    pass


class CustomTypeContainer:
    pass


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


class CModuleDecoratorBase:
    """
    This is a class-decorator, that creates a derived class from a TestSetup
    which is extended by a C-Module.
    """

    def __call__(self, parent_cls):
        class SubCls(parent_cls):
            pass
        SubCls.__name__ = parent_cls.__name__
        SubCls.__qualname__ = parent_cls.__qualname__
        SubCls.__module__ = parent_cls.__module__
        for transunit in self.iter_transunits(deco_cls=parent_cls):
            SubCls.__extend_by_transunit__(transunit)
        req_libs, lib_dirs = self.get_lib_search_params(deco_cls=parent_cls)
        SubCls.__extend_by_lib_search_params__(req_libs, lib_dirs)
        return SubCls

    @abc.abstractmethod
    def iter_transunits(self, deco_cls: 'TestSetup') -> Iterator[TransUnit]:
        return iter([])

    def get_lib_search_params(self, deco_cls: 'TestSetup') \
            -> Tuple[List[str], List[str]]:
        return [], []


class CModule(CModuleDecoratorBase):
    """
    This is a standard implementation for CModuleDecoratorBase, that allows
    multiple source-filenames and parametersets to be combined into one module.
    """

    def __init__(self, *src_filenames:Union[str, Path],
                 include_dirs:List[Union[os.PathLike, str]]=(),
                 library_dirs:List[Union[os.PathLike, str]]=(),
                 required_libs:List[str]=(),
                 predef_macros:Dict[str, Any]=None,
                 **kw_predef_macros:Any):
        if len(src_filenames) == 0:
            raise ValueError('expect at least one positional argument as C '
                             'source filename')
        self.src_filenames = list(map(Path, src_filenames))
        self.include_dirs = list(map(Path, include_dirs))
        self.library_dirs = list(map(Path, library_dirs))
        self.required_libs = required_libs
        self.predef_macros = kw_predef_macros
        if predef_macros:
            self.predef_macros.update(predef_macros)

    def iter_transunits(self, deco_cls):
        srcs = self._resolve_and_check_list('C Sourcefile', self.src_filenames,
                                            Path.is_file, deco_cls)
        for src in srcs:
            yield TransUnit(
                self.src_filenames[0].stem,
                src,
                self._resolve_and_check_list(
                    'Include directorie', self.include_dirs, Path.is_dir,
                    deco_cls),
                self.predef_macros)

    def get_lib_search_params(self, deco_cls):
        return (list(self.required_libs),
                self._resolve_and_check_list('Library Directorie',
                                             self.library_dirs, Path.is_dir,
                                             deco_cls))

    @classmethod
    def _resolve_and_check_list(cls, name, paths, valid_check, deco_cls):
        abs_paths = [cls.resolve_path(p, deco_cls) for p in paths]
        invalid_paths = [str(p) for p in abs_paths if not valid_check(p)]
        if invalid_paths:
            raise IOError('Cannot find ' + name + '(s): '
                          + ', '.join(invalid_paths))
        return abs_paths

    @staticmethod
    def resolve_path(filename, deco_cls:'TestSetup') -> Path:
        mod = sys.modules[deco_cls.__module__]
        return (Path(mod.__file__).parent / filename).resolve()


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


SYS_WHITELIST = [
    'NULL', 'EOF',
    'int8_t', 'uint8_t', 'int16_t', 'uint16_t', 'int32_t', 'uint32_t',
    'int64_t', 'uint64_t', 'wchar_t', 'size_t']


class TestSetup(BuildInDefs):

    struct = CustomTypeContainer()
    enum = CustomTypeContainer()

    _BUILD_DIR_ = '.headlock'

    __test__ = False   # avoid that pytest/nose/... collect this as test

    __parser_factory__ = functools.partial(CParser, sys_whitelist=SYS_WHITELIST)
    __TOOLCHAIN__:ToolChainDriver = None

    __globals = {}
    __implementations = set()
    __ts_name__ = None

    _delayed_exc = None

    __transunits__ = frozenset()

    __required_libraries = []
    __library_directories = []

    ### provide structs with packing 1

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        bases = list(reversed([base for base in cls.__bases__
                               if issubclass(base, TestSetup)]))
        cls.__ts_name__ = None
        cls.__globals = bases[0].__globals.copy()
        cls.__implementations = bases[0].__implementations.copy()
        cls.struct = copy.copy(bases[0].struct)
        cls.union = cls.struct
        cls.enum = copy.copy(bases[0].enum)
        cls.__transunits__ = bases[0].__transunits__
        for base in reversed(bases[1:]):
            cls.__globals.update(base.__globals)
            cls.__implementations.update(base.__implementations)
            cls.struct.__dict__.update(base.struct.__dict__)
            cls.enum.__dict__.update(base.enum.__dict__)
            cls.__transunits__ |= base.__transunits__

    @classmethod
    def get_ts_abspath(cls):
        src_filename = sys.modules[cls.__module__].__file__
        return Path(src_filename).resolve()

    @classmethod
    def get_src_dir(cls):
        return cls.get_ts_abspath().parent

    @classmethod
    def get_build_dir(cls):
        return cls.get_src_dir() / cls._BUILD_DIR_ / cls.get_ts_abspath().stem \
               / cls.get_ts_name()

    @classmethod
    def get_ts_name(cls):
        static_qualname = cls.__qualname__.replace('.<locals>.', '.')
        shortend_name_parts = [nm[:32] for nm in static_qualname.split('.')]
        rev_static_qualname = '.'.join(reversed(shortend_name_parts))
        if '.<locals>.' not in cls.__qualname__:
            return rev_static_qualname
        else:
            # this is a dynamicially generated class
            # => require separate directory for every generated variant
            hash = hashlib.md5()
            for tu in sorted(cls.__transunits__):
                hash.update(bytes(tu.abs_src_filename))
                hash.update(repr(sorted(tu.abs_incl_dirs)).encode('utf8'))
                hash.update(repr(sorted(tu.predef_macros.items()))
                            .encode('utf8'))
            return rev_static_qualname + '_' + hash.hexdigest()[:8]

    @classmethod
    def __extend_by_transunit__(cls, transunit:TransUnit):
        predef_macros = cls.__TOOLCHAIN__.sys_predef_macros()
        predef_macros.update(transunit.predef_macros)
        parser = cls.__parser_factory__(
            predef_macros,
            transunit.abs_incl_dirs,
            cls.__TOOLCHAIN__.sys_incl_dirs(),
            target_compiler=cls.__TOOLCHAIN__.CLANG_TARGET)
        try:
            parser.read(str(transunit.abs_src_filename))
        except ParseError as exc:
            exc = CompileError(exc.errors, transunit.abs_src_filename)
            raise exc
        else:
            cls.__globals.update(parser.funcs)
            cls.__globals.update(parser.vars)
            cls.__implementations |= parser.implementations

            for name, typedef in parser.typedefs.items():
                if isinstance(typedef, CStructType) \
                    and typedef.is_anonymous_struct():
                    typedef.struct_name = '__anonymousfromtypedef__' + name
                setattr(cls, name, typedef)
            for name, typedef in parser.structs.items():
                if isinstance(typedef, CStructType):
                    setattr(cls.struct, typedef.struct_name, typedef)
                elif isinstance(typedef, CEnumType):
                    setattr(cls.enum, name, typedef)

            for name, macro_def in parser.macros.items():
                setattr(cls, name, macro_def)

        if transunit.abs_src_filename.suffix != '.h':
            cls.__transunits__ |= {transunit}

        if cls.__ts_name__ is None:
            cls.__ts_name__ = transunit.abs_src_filename.stem

    @classmethod
    def __extend_by_lib_search_params__(cls, req_libs:List[str],
                                        lib_dirs:List[Path]=()):
        cls.__required_libraries = cls.__required_libraries[:] + \
                                   [req_lib for req_lib in req_libs
                                    if req_lib not in cls.__required_libraries]
        cls.__library_directories = cls.__library_directories[:] + \
                                    [libdir for libdir in lib_dirs
                                     if libdir not in cls.__library_directories]

    def __init__(self):
        super(TestSetup, self).__init__()
        self.__unload_events = []
        self._global_refs_ = {}
        self.__dll = None
        self.__started = False
        if self._delayed_exc:
            raise self._delayed_exc
        self.__build__()
        self.__load__()

    @classmethod
    def __logger__(cls):
        return None

    def __build_mock_proxy__(self):
        def mock_proxy_generator():
            yield '/* This file is automaticially generated by testsetup.py. *\n'
            yield ' * DO NOT MODIFY IT MANUALLY.                             */\n'
            yield '\n'
            mocks = {name: type
                     for name, type in self.__globals.items()
                     if name not in self.__implementations}
            def iter_in_dep_order(only_embedded_types=False):
                processed = set()
                def emb_struct_only(cobj_type, parent_cobj_type):
                    return not (isinstance(cobj_type, CStructType)
                                and isinstance(parent_cobj_type, CPointerType))
                for cobj_type in mocks.values():
                    sub_types = cobj_type.iter_subtypes(
                        top_level_last=True,
                        filter=emb_struct_only if only_embedded_types else None,
                        processed=processed)
                    for sub_type in sub_types:
                        if isinstance(sub_type, CStructType) \
                                and not sub_type.is_anonymous_struct():
                            yield sub_type
            for cstruct_type in iter_in_dep_order():
                yield cstruct_type.c_definition() + ';\n'
            for cstruct_type in iter_in_dep_order(only_embedded_types=True):
                yield cstruct_type.c_definition_full() + ';\n'
            yield '\n'
            for mock_name, mock in sorted(mocks.items()):
                if not isinstance(mock, CFuncType):
                    yield mock.c_definition(mock_name) + ';\n'
                else:
                    yield mock.c_definition(f'(* {mock_name}_mock)') + ' = 0;\n'
                    yield mock.c_definition(mock_name) + '\n'
                    yield '{\n'
                    yield '\treturn ' if mock.returns is not None else '\t'
                    params = ', '.join(f'p{pndx}'
                                       for pndx in range(len(mock.args)))
                    yield f'(* {mock_name}_mock)({params});\n'
                    yield '}\n'

        mock_proxy_path = self.get_build_dir() / f'__headlock_mocks__.c'
        mock_proxy_path.open('wt').writelines(mock_proxy_generator())

        return mock_proxy_path

    def __build__(self):
        if not self.get_build_dir().exists():
            self.get_build_dir().mkdir(parents=True)
        mock_proxy_path = self.__build_mock_proxy__()
        mock_tu = TransUnit('mocks', mock_proxy_path, [], {})
        self.__TOOLCHAIN__.build(self.get_ts_name(),
                                 self.get_build_dir(),
                                 sorted(self.__transunits__ | {mock_tu}),
                                 self.__required_libraries,
                                 self.__library_directories)

    def __load__(self):
        exepath = self.__TOOLCHAIN__.exe_path(self.get_ts_name(),
                                              self.get_build_dir())
        self.__dll = ct.CDLL(os.fspath(exepath))
        try:
            for name, cobj_type in self.__globals.items():
                if isinstance(cobj_type, CFuncType):
                    if name not in self.__implementations:
                        self.__setup_mock_callback(name, cobj_type)
                    cobj = cobj_type(getattr(self.__dll, name),
                                     logger=self.__logger__())
                else:
                    ctypes_var = cobj_type.ctypes_type.in_dll(self.__dll, name)
                    cobj = cobj_type.COBJ_CLASS(cobj_type, ctypes_var)
                setattr(self, name, cobj)
        except:
            self.__unload__()
            raise

    def __startup__(self):
        self.__started = True

    def __setup_mock_callback(self, name, cfunc_type):
        self_weakref = weakref.ref(self)
        def callback_wrapper(*args):
            try:
                pymock = getattr(self_weakref(), name + '_mock')
            except AttributeError:
                return self.mock_fallback(name, *args)
            else:
                return pymock(*args)
        callback_wrapper.__name__ = name

        callback_func = cfunc_type(callback_wrapper, logger=self.__logger__())

        callback_ptr = ct.c_void_p.in_dll(self.__dll, name + '_mock')
        callback_ptr.value = callback_func.adr.val

        # ensure that callback closure is not garbage collected:
        self._global_refs_[name + '_mock'] = callback_func

    def __shutdown__(self):
        self.__started = False

    def __unload__(self):
        if self.__dll:
            if self.__started:
                self.__shutdown__()
            for event, args in reversed(self.__unload_events):
                event(*args)
            for name in self.__globals:
                delattr(self, name)
            self._global_refs = dict()
            ct.windll.kernel32.FreeLibrary(self.__dll._handle)
            self.__dll = None

    def __enter__(self):
        if not self.__started:
            self.__startup__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.__unload__()

    def __del__(self):
        try:
            self.__unload__()
        except Exception:
            pass

    def mock_fallback(self, funcname, *args):
        raise MethodNotMockedError(
            f'{funcname!r} is not mocked yet')

    def register_unload_event(self, func, *args):
        """
        Allows to register functions, that are called when the testsetup is
        unloaded via __unload__()
        """
        self.__unload_events.append((func, args))


# This is a preliminary workaround until there is a clean solution on
# how to configure toolchains.
if platform.architecture()[0] == '32bit':
    from .toolchains.mingw import MinGW32ToolChain
    TestSetup.__TOOLCHAIN__ = MinGW32ToolChain()
else:
    from .toolchains.mingw import MinGW64ToolChain
    TestSetup.__TOOLCHAIN__ = MinGW64ToolChain()
