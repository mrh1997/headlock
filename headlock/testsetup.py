import functools
import os
import sys
import weakref
from typing import List, Dict, Any, Union, Set
from pathlib import Path

from .c_data_model import BuildInDefs, CStructType, CEnumType, CFuncType, \
    CFuncPointerType, CProxyType
from .address_space import AddressSpace
from .address_space.inprocess import InprocessAddressSpace
from .c_parser import CParser, ParseError
from .buildsys_drvs import BuildDescription, BuildError, default
from .bridge_gen import write_bridge


class CompileError(BuildError):

    def __init__(self, errors, path=None):
        super().__init__(f'{len(errors)} compile errors', path)
        self.errors = errors

    def __iter__(self):
        yield from self.errors



class MethodNotMockedError(Exception):
    pass


class CProxyTypeDescriptor:
    """
    This internal class provides descriptors for CProxyType objects contained
    by TestSetups.
    """

    def __init__(self, ctype:CProxyType):
        self.ctype = ctype

    def __get__(self, instance, owner):
        if instance is None:
            return self.ctype
        else:
            return self.ctype.bind(instance.__addrspace__)

    def __set__(self, instance, value):
        raise AttributeError("Can't set CProxyType")


class CProxyDescriptor:
    """
    This internal class provides descriptors for CProxy objects containted by
    TestSetups.
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

    def __set__(self, instance, value):
        raise AttributeError("Can't set CProxyType")


class CompoundTypeNamespace:
    def __init__(self, addrspace:AddressSpace):
        self.__addrspace__ = addrspace


SYS_WHITELIST = [
    'NULL', 'EOF',
    'int8_t', 'uint8_t', 'int16_t', 'uint16_t', 'int32_t', 'uint32_t',
    'int64_t', 'uint64_t', 'wchar_t', 'size_t']


class TestSetup(BuildInDefs):

    struct = CompoundTypeNamespace
    union = struct
    enum = struct

    _BUILD_DIR_ = '.headlock'

    __test__ = False   # avoid that pytest/nose/... collect this as test

    __parser_factory__ = functools.partial(CParser, sys_whitelist=SYS_WHITELIST)
    __builddesc__:BuildDescription = None

    __globals:Dict[str, CProxyType] = {}
    __implementations:Set[str] = set()
    __required_funcptrs:Dict[str, CFuncType] = {}

    __required_libraries = []
    __library_directories = []

    ### provide structs with packing 1

    # specifies the maximum  number of C function pointers to python callables
    # per C function signature.
    C2PY_BRIDGES_PER_SIG = 8

    @classmethod
    def __builddesc_factory__(cls) -> BuildDescription:
        # This is a preliminary workaround until there is a clean solution on
        # how to configure builddescs.
        src_filename = sys.modules[cls.__module__].__file__
        ts_abspath = Path(src_filename).resolve()
        src_dir = ts_abspath.parent
        static_qualname = cls.__qualname__.replace('.<locals>.', '.')
        shortend_name_parts = [nm[:32] for nm in static_qualname.split('.')]
        rev_static_qualname = '.'.join(reversed(shortend_name_parts))
        build_dir = src_dir / cls._BUILD_DIR_ / ts_abspath.stem \
               / rev_static_qualname
        return default.BUILDDESC_CLS(
            rev_static_qualname,
            build_dir,
            unique_name='.<locals>.' not in cls.__qualname__)

    @classmethod
    def __set_builddesc__(cls, builddesc:BuildDescription):
        cls.__builddesc__ = builddesc
        cls.__globals = {}
        cls.__implementations = set()
        cls.__required_funcptrs = {}
        compound_ns = {}
        for c_src in builddesc.c_sources():
            predef_macros = builddesc.sys_predef_macros()
            predef_macros.update(builddesc.predef_macros()[c_src])
            parser = cls.__parser_factory__(
                predef_macros,
                builddesc.incl_dirs()[c_src],
                builddesc.sys_incl_dirs(),
                target_compiler=builddesc.clang_target())
            try:
                parser.read(c_src)
            except ParseError as exc:
                exc = CompileError(exc.errors, c_src)
                raise exc

            cls.__globals.update(parser.funcs)
            cls.__globals.update(parser.vars)
            cls.__implementations.update(parser.implementations)
            cls.__required_funcptrs.update({
                subtype.base_type.c_sig: subtype.base_type
                for typedict in [parser.funcs, parser.vars,
                                 parser.typedefs, parser.structs]
                for ctype in typedict.values()
                for subtype in ctype.iter_subtypes()
                if isinstance(subtype, CFuncPointerType)})

            for name, ctype in parser.funcs.items():
                cfunc_descr = CProxyDescriptor(name, ctype)
                setattr(cls, name, cfunc_descr)
            for name, ctype in parser.vars.items():
                cglobal_descr = CProxyDescriptor(name, ctype)
                setattr(cls, name, cglobal_descr)
            for name, typedef in parser.typedefs.items():
                if isinstance(typedef, CStructType) \
                    and typedef.is_anonymous_struct():
                    typedef.struct_name = '__anonymousfromtypedef__' + name
                cstruct_descr = CProxyTypeDescriptor(typedef)
                setattr(cls, name, cstruct_descr)
            for name, typedef in parser.structs.items():
                typedef_descr = CProxyTypeDescriptor(typedef)
                if isinstance(typedef, CStructType):
                    compound_ns[typedef.struct_name] = typedef_descr
                elif isinstance(typedef, CEnumType):
                    compound_ns[name] = typedef_descr
            for name, macro_def in parser.macros.items():
                setattr(cls, name, macro_def)
        cls.struct = cls.enum = cls.union = \
            type('CompoundTypeNamespace', (CompoundTypeNamespace,), compound_ns)

    def __init__(self):
        super(TestSetup, self).__init__()
        self.__unload_events = []
        self._global_refs_ = {}
        self.__addrspace__:AddressSpace = None
        self.__mock_names = []
        self.__bridge_sigs = []
        self.__c2py_bridge_cnt = 0
        self.__started = False
        self.__build__()
        self.__load__()

    @classmethod
    def __logger__(cls):
        return None

    def __create_bridge__(self, bridge_path):
        c_sig = lambda f: f.c_sig
        req_funcptrs = set(self.__required_funcptrs.values())
        req_typedefs = set(self.__globals.values()) | req_funcptrs
        global_funcs = {f for f in self.__globals.values()
                        if isinstance(f, CFuncType)}
        c2py_funcs = sorted(req_funcptrs, key=c_sig)
        py2c_funcs = c2py_funcs + sorted(global_funcs - req_funcptrs, key=c_sig)
        mock_funcs = sorted([
            (name, type)
            for name, type in self.__globals.items()
            if name not in self.__implementations and
               isinstance(type, CFuncType)])
        mock_vars = {name: type
                     for name, type in self.__globals.items()
                     if name not in self.__implementations and
                        not isinstance(type, CFuncType)}
        with bridge_path.open('wt') as output:
            write_bridge(output, req_typedefs, py2c_funcs,
                         c2py_funcs, mock_funcs, mock_vars,
                         self.C2PY_BRIDGES_PER_SIG)
        self.__mock_names = [name for name, _ in mock_funcs]
        self.__bridge_sigs = list(map(c_sig, py2c_funcs))
        self.__c2py_bridge_cnt = len(c2py_funcs)

    def __build__(self):
        if not self.__builddesc__.build_dir.exists():
            self.__builddesc__.build_dir.mkdir(parents=True)
        bridge_file_path = self.__builddesc__.build_dir/'__headlock_bridge__.c'
        self.__create_bridge__(bridge_file_path)
        self.__builddesc__.build([bridge_file_path])

    def __load__(self):
        self_weakref = weakref.ref(self)
        def mock_bridge(mock_id:int, params_adr:int, retval_adr:int):
            self = self_weakref()
            mock_name = self.__mock_names[mock_id]
            try:
                pymock = getattr(self, mock_name + '_mock')
            except AttributeError:
                pymock = functools.partial(self.mock_fallback, mock_name)
            mock_ctype = getattr(self, mock_name).ctype
            mock_ctype.bridge_c2py(pymock, params_adr, retval_adr)

        exepath = self.__builddesc__.exe_path()
        self.__addrspace__ = InprocessAddressSpace(
            os.fspath(exepath),
            self.__bridge_sigs,
            set(range(self.__c2py_bridge_cnt)),
            self.C2PY_BRIDGES_PER_SIG,
            mock_bridge)
        self.struct = self.struct(self.__addrspace__)
        self.union = self.struct
        self.enum = self.struct

    def __startup__(self):
        self.__started = True

    def __shutdown__(self):
        self.__started = False

    def __unload__(self):
        if self.__addrspace__:
            if self.__started:
                self.__shutdown__()
            for event, args in reversed(self.__unload_events):
                event(*args)
            self._global_refs = dict()
            self.__addrspace__.close()
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


class CModule:
    """
    This is a decorator for classes derived from TestSetup, that allows
    multiple source-filenames and parametersets to be combined into one module.
    """

    def __init__(self, *src_filenames:Union[str, Path],
                 include_dirs:List[Union[os.PathLike, str]]=(),
                 library_dirs:List[Union[os.PathLike, str]]=(),
                 required_libs:List[str]=(),
                 predef_macros:Dict[str, Any]=None,
                 **kw_predef_macros:Any):
        self.src_filenames = list(map(Path, src_filenames))
        self.include_dirs = list(map(Path, include_dirs))
        self.library_dirs = list(map(Path, library_dirs))
        self.required_libs = required_libs
        self.predef_macros = kw_predef_macros
        if predef_macros:
            self.predef_macros.update(predef_macros)

    def __call__(self, ts):
        if ts.__builddesc__ is None:
            builddesc = ts.__builddesc_factory__()
        else:
            builddesc = ts.__builddesc__.copy()
        for c_src in self.src_filenames:
            abs_c_src = self.resolve_and_check(c_src, Path.is_file, ts)
            builddesc.add_c_source(abs_c_src)
        for incl_dir in self.include_dirs:
            abs_incl_dir = self.resolve_and_check(incl_dir, Path.is_dir, ts)
            builddesc.add_incl_dir(abs_incl_dir)
        for lib_dir in self.library_dirs:
            abs_lib_dir = self.resolve_and_check(lib_dir, Path.is_dir, ts)
            builddesc.add_lib_dir(abs_lib_dir)
        for req_lib in self.required_libs:
            builddesc.add_req_lib(req_lib)
        builddesc.add_predef_macros(self.predef_macros)
        ts.__set_builddesc__(builddesc)
        return ts

    @classmethod
    def resolve_and_check(cls, path, valid_check, ts):
        module_path = Path(sys.modules[ts.__module__].__file__).parent
        abs_path = (module_path / path).resolve()
        if not valid_check(abs_path):
            raise IOError(f'Cannot find {abs_path}')
        return abs_path
