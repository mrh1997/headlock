import ctypes as ct
import functools
import os
import sys
import weakref
import abc
import hashlib
import copy

from pathlib import Path

from .c_data_model import BuildInDefs, CStruct, CEnum, CFunc
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


@functools.total_ordering
class TransUnit:

    def __init__(self, subsys_name, abs_src_filename, abs_incl_dirs,
                 predef_macros):
        self.subsys_name = subsys_name
        self.abs_src_filename = abs_src_filename
        self.abs_incl_dirs = abs_incl_dirs
        self.predef_macros = predef_macros

    def __repr__(self):
        return f'{type(self).__name__}({self.subsys_name}, ' \
               f'{self.abs_src_filename}, {self.abs_incl_dirs}, ' \
               f'{self.predef_macros})'

    def __iter_attrs(self):
        yield self.subsys_name
        yield self.abs_src_filename
        yield from self.abs_incl_dirs
        yield from self.predef_macros.items()

    def __hash__(self):
        return hash(tuple(self.__iter_attrs()))

    def __eq__(self, other):
        return tuple(self.__iter_attrs()) == tuple(other.__iter_attrs())

    def __lt__(self, other):
        return tuple(self.__iter_attrs()) < tuple(other.__iter_attrs())


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
        for transunit in self.iter_transunits(SubCls):
            SubCls.__extend_by_transunit__(transunit)
        return SubCls

    @abc.abstractmethod
    def iter_transunits(self, cls):
        return iter([])


class CModule(CModuleDecoratorBase):
    """
    This is a standard implementation for CModuleDecoratorBase, that allows
    multiple source-filenames and parametersets to be combined into one module.
    """

    def __init__(self, *src_filenames, **predef_macros):
        self.src_filenames = list(map(Path, src_filenames))
        self.predef_macros = predef_macros

    def iter_transunits(self, cls):
        abs_src_filenames = []
        abs_incl_dirs = []
        for src_filename in self.src_filenames:
            item_path = self.resolve_path(src_filename, cls)
            if item_path.is_dir():
                abs_incl_dirs.append(item_path)
            elif item_path.is_file():
                abs_src_filenames.append(item_path)
            else:
                raise IOError('Cannot find C-File / Include-Dir path {}'
                              .format(item_path))
        for abs_src_filename in abs_src_filenames:
            yield TransUnit(self.src_filenames[0].stem,
                            abs_src_filename,
                            abs_incl_dirs,
                            self.predef_macros)

    @staticmethod
    def resolve_path(filename, cls):
        mod = sys.modules[cls.__module__]
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
    def exe_path(self, build_dir, name):
        """
        returns name of executable image
        """

    @abc.abstractmethod
    def build(self, transunits, build_dir, name):
        """
        builds executable image from translation units 'transunits'
        """


class TestSetup(BuildInDefs):

    struct = CustomTypeContainer()
    enum = CustomTypeContainer()

    _BUILD_DIR_ = '.headlock'

    __test__ = False   # avoid that pytest/nose/... collect this as test

    __parser_factory__ = CParser
    __TOOLCHAIN__:ToolChainDriver = None

    __globals = {}
    __implementations = set()
    __ts_name__ = None

    _delayed_exc = None

    __transunits__ = frozenset()

    ### provide structs with packing 1

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        bases = list(reversed([base for base in cls.__bases__
                               if issubclass(base, TestSetup)]))
        cls.__ts_name__ = None
        cls.__globals = bases[0].__globals.copy()
        cls.__implementations = bases[0].__implementations.copy()
        cls.struct = copy.copy(bases[0].struct)
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
    def __extend_by_transunit__(cls, transunit):
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

            for name, typedef in parser.structs.items():
                if issubclass(typedef, CStruct):
                    setattr(cls.struct, name, typedef)
                elif issubclass(typedef, CEnum):
                    setattr(cls.enum, name, typedef)

            for name, typedef in parser.typedefs.items():
                setattr(cls, name, typedef)
            for name, macro_def in parser.macros.items():
                setattr(cls, name, macro_def)

        if transunit.abs_src_filename.suffix != '.h':
            cls.__transunits__ |= {transunit}

        if cls.__ts_name__ is None:
            cls.__ts_name__ = transunit.abs_src_filename.stem

    def __init__(self):
        super(TestSetup, self).__init__()
        self.__unload_events = []
        self._global_refs_ = {}
        self.__dll = None
        if self._delayed_exc:
            raise self._delayed_exc
        self.__build__()
        self.__load__()

    @classmethod
    def __logger__(cls):
        return None

    def __build_mock_proxy__(self):
        def mock_proxy_generator():
            def iter_in_dep_order(only_full_defs=False):
                already_processed = set()
                for objtype in mocks.values():
                    for req_type_name in objtype.iter_req_custom_types(
                            only_full_defs, already_processed):
                        yield req_type_name
            mocks = {name: type
                     for name, type in self.__globals.items()
                     if name not in self.__implementations}
            yield '/* This file is automaticially generated by testsetup.py. *\n'
            yield ' * DO NOT MODIFY IT MANUALLY.                             */\n'
            yield '\n'
            if mocks:
                for struct_name in iter_in_dep_order():
                    struct = getattr(self.struct, struct_name)
                    yield struct.c_definition() + ';\n'
                for struct_name in iter_in_dep_order(only_full_defs=True):
                    struct = getattr(self.struct, struct_name)
                    yield struct.c_definition_full() + ';\n'
            yield '\n'
            for mock_name, mock in sorted(mocks.items()):
                if not issubclass(mock, CFunc):
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
        mock_proxy_ccode = ''.join(mock_proxy_generator())
        mock_proxy_path.write_text(mock_proxy_ccode)

        return mock_proxy_path

    def __build__(self):
        if not self.get_build_dir().exists():
            self.get_build_dir().mkdir(parents=True)
        mock_proxy_path = self.__build_mock_proxy__()
        mock_tu = TransUnit('mocks', mock_proxy_path, [], {})
        self.__TOOLCHAIN__.build(sorted(self.__transunits__ | {mock_tu}),
                                 self.get_build_dir(),
                                 self.get_ts_name())

    def __load__(self):
        exepath = self.__TOOLCHAIN__.exe_path(self.get_build_dir(),
                                              self.get_ts_name())
        self.__dll = ct.CDLL(os.fspath(exepath))
        try:
            for name, cobj_type in self.__globals.items():
                if issubclass(cobj_type, CFunc):
                    if name not in self.__implementations:
                        self.__setup_mock_callback(name, cobj_type)
                    cobj = cobj_type(getattr(self.__dll, name),
                                     logger=self.__logger__())
                else:
                    ctypes_var = cobj_type.ctypes_type.in_dll(self.__dll, name)
                    cobj = cobj_type(ctypes_var)
                setattr(self, name, cobj)
        except:
            self.__unload__()
            raise

    def __startup__(self):
        self.__load__()

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
        for event, args in reversed(self.__unload_events):
            event(*args)

    def __unload__(self):
        self.__shutdown__()
        for name in self.__globals:
            delattr(self, name)
        self._global_refs = dict()
        if self.__dll:
            ct.windll.kernel32.FreeLibrary(self.__dll._handle)
            self.__dll = None

    def __enter__(self):
        self.__startup__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.__unload__()

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
from .toolchains.mingw32 import MinGW32ToolChain
TestSetup.__TOOLCHAIN__ = MinGW32ToolChain(architecture='i686',
                                           exception_model='dwarf')
