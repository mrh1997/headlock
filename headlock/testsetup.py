import ctypes as ct
import functools
import os
import sys
import weakref
import abc
import hashlib
import platform
from typing import List, Iterator, Dict, Any, Tuple, Union
from pathlib import Path

from .c_data_model import BuildInDefs, CStructType, CEnumType, CFuncType, \
    CProxyType
from .address_space import AddressSpace
from .address_space.inprocess import InprocessAddressSpace
from .c_parser import CParser, ParseError
from .toolchains import ToolChainDriver, BuildError, TransUnit
from .bridge_gen import write_bridge_code


class CompileError(BuildError):

    def __init__(self, errors, path=None):
        super().__init__(f'{len(errors)} compile errors', path)
        self.errors = errors

    def __iter__(self):
        yield from self.errors



class MethodNotMockedError(Exception):
    pass


class GlobalCProxyDescriptor:
    """
    This internal class provides descriptors for global CProxy objects.
    If the testsetup is instantiated, they return a CProxy object.
    Otherwise they return the corresponding CProxyType
    """

    def __init__(self, name:str, ctype:CProxyType):
        self.name = name
        self.ctype = ctype

    def __get__(self, instance, owner):
        if instance is None:
            return self.ctype
        else:
            addrspace = instance.__addrspace__
            sym_adr = addrspace.get_symbol_adr(self.name)
            return self.ctype.bind(addrspace).create_cproxy_for(sym_adr)


class StructUnionEnumCTypeCollection:
    def __init__(self, addrspace:AddressSpace):
        self.__addrspace__ = addrspace


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


SYS_WHITELIST = [
    'NULL', 'EOF',
    'int8_t', 'uint8_t', 'int16_t', 'uint16_t', 'int32_t', 'uint32_t',
    'int64_t', 'uint64_t', 'wchar_t', 'size_t']


if sys.platform == 'win32':
    unload_library_func = ct.windll.kernel32.FreeLibrary
elif sys.platform == 'linux':
    unload_library_func = ct.CDLL('libdl.so').dlclose
else:
    raise NotImplementedError('the platform is not supported yet')

class TestSetup(BuildInDefs):

    class struct(StructUnionEnumCTypeCollection): pass
    union = struct
    enum = struct

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
        cls.struct = type(cls.__name__ + '_struct',
                          tuple(base.struct for base in bases),
                          {})
        cls.union = cls.struct
        cls.enum = cls.struct
        cls.__transunits__ = bases[0].__transunits__
        for base in reversed(bases[1:]):
            cls.__globals.update(base.__globals)
            cls.__implementations.update(base.__implementations)
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

            for name, ctype in parser.funcs.items():
                descr = GlobalCProxyDescriptor(name, ctype)
                setattr(cls, name, descr)
            for name, ctype in parser.vars.items():
                descr = GlobalCProxyDescriptor(name, ctype)
                setattr(cls, name, descr)
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
        self.__addrspace__:AddressSpace = None
        self.__started = False
        if self._delayed_exc:
            raise self._delayed_exc
        self.__build__()
        self.__load__()

    @classmethod
    def __logger__(cls):
        return None

    def __build__(self):
        if not self.get_build_dir().exists():
            self.get_build_dir().mkdir(parents=True)
        mock_proxy_path = self.get_build_dir() / '__headlock_bridge__.c'
        write_bridge_code(mock_proxy_path.open('wt'),
                          self.__globals,
                          self.__implementations)
        mock_tu = TransUnit('mocks', mock_proxy_path, [], {})
        self.__TOOLCHAIN__.build(self.get_ts_name(),
                                 self.get_build_dir(),
                                 sorted(self.__transunits__ | {mock_tu}),
                                 self.__required_libraries,
                                 self.__library_directories)

    def __load__(self):
        exepath = self.__TOOLCHAIN__.exe_path(self.get_ts_name(),
                                              self.get_build_dir())
        cdll = ct.CDLL(os.fspath(exepath))
        self.__addrspace__ = InprocessAddressSpace([cdll])
        self.struct = self.struct(self.__addrspace__)
        self.union = self.struct
        self.enum = self.struct
        try:
            for name, ctype in self.__globals.items():
                if isinstance(ctype, CFuncType) \
                    and name not in self.__implementations:
                    self.__setup_mock_callback(name, ctype.bind(self.__addrspace__))
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

        mock_ptr_adr = self.__addrspace__.get_symbol_adr(name + '_mock')
        mock_ptr = cfunc_type.ptr.create_cproxy_for(mock_ptr_adr)
        mock_ptr.val = cfunc_type(callback_wrapper).val

    def __shutdown__(self):
        self.__started = False

    def __unload__(self):
        if self.__addrspace__:
            if self.__started:
                self.__shutdown__()
            for event, args in reversed(self.__unload_events):
                event(*args)
            self._global_refs = dict()
            unload_library_func(self.__addrspace__.cdll._handle)
            self.__addrspace__ = None

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
if sys.platform == 'win32':
    if platform.architecture()[0] == '32bit':
        from .toolchains.mingw import MinGW32ToolChain
        TestSetup.__TOOLCHAIN__ = MinGW32ToolChain()
    else:
        from .toolchains.mingw import MinGW64ToolChain
        TestSetup.__TOOLCHAIN__ = MinGW64ToolChain()
elif sys.platform == 'linux':
    if platform.architecture()[0] == '32bit':
        from .toolchains.gcc import Gcc32ToolChain
        TestSetup.__TOOLCHAIN__ = Gcc32ToolChain()
    else:
        from .toolchains.gcc import Gcc64ToolChain
        TestSetup.__TOOLCHAIN__ = Gcc64ToolChain()
