import ctypes as ct
import os
import os.path
import subprocess
import sys
import weakref
import abc
import hashlib
from collections import namedtuple
import copy

from pathlib import Path

from .c_data_model import BuildInDefs, CStruct, CEnum, CFunc
from .c_parser import CParser, ParseError


DEFAULT_MINGW64_DIR = r'C:\Program Files (x86)\mingw-w64'


BUILD_CACHE = set()
DISABLE_AUTOBUILD = False


class BuildError(Exception):

    def __init__(self, msg, testsetup=None):
        super().__init__(msg)
        self.testsetup = testsetup

    def __str__(self):
        return (f'building {self.testsetup.__name__} failed: ' if self.testsetup
                else '') \
               + super().__str__()


class CompileError(BuildError):

    def __init__(self, errors, goal=None):
        super().__init__(f'{len(errors)} compile errors', goal)
        self.errors = errors

    def __iter__(self):
        yield from self.errors



class MethodNotMockedError(Exception):
    pass


class CustomTypeContainer:
    pass


def get_mingw_dir():
    mingw64_dir = Path(os.environ.get('MINGW64_DIR', DEFAULT_MINGW64_DIR))
    envs = list(mingw64_dir.glob(r'i686-*-*-dwarf-rt_v5-*\mingw32'))
    if not envs:
        raise BuildError(f'no MinGW64 found in {mingw64_dir} '
                         f'(see MINGW64_DIR environment variable)')
    envs.sort()
    return envs[-1]


TransUnit = namedtuple(
    'TransUnit',
    'subsys_name abs_src_filename abs_incl_dirs predef_macros')


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
    def iter_transunits(self, cls): return iter([])


class CModule(CModuleDecoratorBase):
    """
    This is a standard implementation for CModuleDecoratorBase, that allows
    multiple source-filenames and parametersets to be combined into one module.
    """

    def __init__(self, *src_filenames, **predef_macros):
        self.src_filenames = list(map(Path, src_filenames))
        self.predef_macros = predef_macros

    def get_fqn(self, cls):
        rev_qualname = '.'.join(reversed(cls.__qualname__.split('.')))
        return f'{self.src_filenames[0].stem}.{rev_qualname}.{cls.__module__}'

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
            yield TransUnit(self.get_fqn(cls),
                            abs_src_filename,
                            abs_incl_dirs,
                            self.predef_macros)

    def resolve_path(self, filename, cls):
        mod = sys.modules[cls.__module__]
        return Path(mod.__file__).parent / filename


class TestSetup(BuildInDefs):

    struct = CustomTypeContainer()
    enum = CustomTypeContainer()

    _BUILD_DIR_ = '.headlock'
    DELAYED_PARSEERROR_REPORTING = True

    __test__ = False   # avoid that pytest/nose/... collect this as test

    __parser_factory__ = CParser

    __globals = {}
    __mocks = set()

    _delayed_exc = None

    __transunits__ = ()

    ### provide structs with packing 1

    @classmethod
    def get_ts_abspath(cls):
        src_filename = sys.modules[cls.__module__].__file__
        return os.path.normpath(os.path.abspath(src_filename))

    @classmethod
    def get_src_dir(cls):
        return os.path.dirname(cls.get_ts_abspath())

    @classmethod
    def get_root_dir(cls):
        return os.path.dirname(os.path.dirname(__file__))

    @classmethod
    def get_build_dir(cls):
        static_dir = os.path.join(cls.get_src_dir(), cls._BUILD_DIR_,
                                  cls.__qualname__.replace('.<locals>.', '.'))
        if '.<locals>.' not in cls.__qualname__:
            return static_dir
        else:
            # this is a dynamicially generated class
            # => require separate directory for every generated variant
            hash = hashlib.md5()
            for tu in cls.__transunits__:
                hash.update(bytes(tu.abs_src_filename))
                hash.update(repr(sorted(tu.abs_incl_dirs)).encode('utf8'))
                hash.update(repr(sorted(tu.predef_macros.items()))
                            .encode('utf8'))
            return static_dir + '_' + hash.hexdigest()

    @classmethod
    def get_ts_name(cls):
        if len(cls.__transunits__) == 0:
            return cls.__name__
        else:
            filename = cls.__transunits__[-1].abs_src_filename
            return filename.stem + '_' + cls.__name__

    @classmethod
    def get_mock_proxy_path(cls):
        return os.path.join(cls.get_build_dir(), f'{cls.get_ts_name()}_mocks.c')

    @classmethod
    def get_makefile_path(cls):
        return os.path.join(cls.get_build_dir(), 'Makefile')

    @classmethod
    def __extend_by_transunit__(cls, transunit):
        parser = cls.__parser_factory__(
            transunit.predef_macros,
            list(map(str, transunit.abs_incl_dirs)),
            [str(get_mingw_dir() / 'i686-w64-mingw32/include')],
            target_compiler='i386-pc-mingw32')
        try:
            parser.read(str(transunit.abs_src_filename))
        except ParseError as exc:
            exc = CompileError(exc.errors, cls)
            if cls.DELAYED_PARSEERROR_REPORTING:
                cls._delayed_exc = exc
            else:
                raise exc
        else:
            cls.__globals = super(cls, cls).__globals.copy()
            cls.__globals.update(parser.funcs)
            cls.__globals.update(parser.vars)

            cls.struct = copy.copy(super(cls, cls).struct)
            cls.enum = copy.copy(super(cls, cls).enum)
            for name, typedef in parser.structs.items():
                if issubclass(typedef, CStruct):
                    setattr(cls.struct, name, typedef)
                elif issubclass(typedef, CEnum):
                    setattr(cls.enum, name, typedef)

            for name, typedef in parser.typedefs.items():
                setattr(cls, name, typedef)
            for name, macro_def in parser.macros.items():
                setattr(cls, name, macro_def)

            cls.__mocks = set(cls.__globals) - parser.implementations
        cls.__transunits__ = cls.__transunits__ + (transunit,)

    def __init__(self):
        super(TestSetup, self).__init__()
        self.__unload_events = []
        self._global_refs_ = {}
        self.__dll = None
        if self._delayed_exc:
            raise self._delayed_exc
        if type(self) not in BUILD_CACHE:
            self.__build__()
            BUILD_CACHE.add(type(self))
        self.__load__()

    @classmethod
    def __logger__(cls):
        return None

    def __build__(self):
        def mock_proxy_generator():
            def iter_in_dep_order(only_full_defs=False):
                already_processed = set()
                for objtype in mocks.values():
                    for req_type_name in objtype.iter_req_custom_types(
                            only_full_defs, already_processed):
                        yield req_type_name
            mocks = {name: type
                     for name, type in self.__globals.items()
                     if name in self.__mocks}
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

        def mock_proxy_writer():
            with open(self.get_mock_proxy_path(), 'wt') as f:
                for text_chunk in mock_proxy_generator():
                    f.write(text_chunk)

        def run_gcc(call_params):
            try:
                completed_proc = subprocess.run(
                    [str(get_mingw_dir() / 'bin' / 'gcc')] + call_params,
                    encoding='ascii',
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                raise BuildError(f'failed to call gcc: {e}',
                                 type(self))
            else:
                if completed_proc.returncode != 0:
                    raise BuildError(completed_proc.stderr, type(self))

        def build_dll():
            mock_proxy_src = Path(self.get_mock_proxy_path())
            mock_tu = TransUnit('mocks', mock_proxy_src, [], {})
            transunits = self.__transunits__ + (mock_tu,)
            build_dir = Path(self.get_build_dir())
            for tu in transunits:
                run_gcc(['-c', str(tu.abs_src_filename)]
                        + ['-o', str(build_dir
                                     / (tu.abs_src_filename.stem + '.o'))]
                        + ['-I' + str(incl_dir)
                           for incl_dir in tu.abs_incl_dirs]
                        + [f'-D{name}={val or ""}'
                           for name, val in tu.predef_macros.items()])
            run_gcc([str(build_dir / (tu.abs_src_filename.stem + '.o'))
                     for tu in transunits]
                    + ['-shared', '-o', str(build_dir / 'cmodule.dll')])

        if not DISABLE_AUTOBUILD:
            if not os.path.exists(self.get_build_dir()):
                os.makedirs(self.get_build_dir())
            mock_proxy_writer()
            build_dll()

    def __load__(self):
        self.__dll = ct.CDLL(os.path.join(self.get_build_dir(), 'cmodule.dll'))
        try:
            for name, cobj_type in self.__globals.items():
                if issubclass(cobj_type, CFunc):
                    if name in self.__mocks:
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
        callback_ptr.value = callback_func.ptr.val

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
