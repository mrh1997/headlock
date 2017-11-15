import ctypes as ct
import itertools
import os
import os.path
import re
import subprocess
import sys
import weakref

from pathlib import Path

from .c_data_model import BuildInDefs, CStruct, CEnum
from .c_parser import CParser, ParseError


DEFAULT_MINGW64_DIR = r'C:\Program Files (x86)\mingw-w64'


BUILD_CACHE = set()
DISABLE_AUTOBUILD = False
ATTR_MACRO_DEF = re.compile(rb'^\s*\#\s*define\s+__attribute__', re.MULTILINE)


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


class CMakeList:

    CMAKEFILE_HEADER = (
        '# This file was generated by testsetup.py automaticially.\n'
        '# Do not modify it manually!\n')

    def __init__(self, filename):
        self.filename = filename
        if os.path.exists(filename):
            self.content = open(filename).read()
            self.cur_content = self.content
        else:
            self.content = self.CMAKEFILE_HEADER
            self.cur_content = None

    def set(self, cmd, params, key_param=''):
        parts = re.split((r'^[ \t]*' + cmd +
                          r'\s*\(\s*' +
                          key_param + ('\s+' if key_param else '') +
                          r'( \"(\\\"|[^"])*?\" | [^"] )*? \)[ \t]*\n{0,2}'),
                         self.content,
                         0,
                         re.IGNORECASE | re.MULTILINE | re.DOTALL | re.VERBOSE)
        all_params = key_param + (' ' if key_param and params else '') + params
        complete_cmd = cmd + '(' + all_params + ')\n\n'
        self.content = (parts[0] +
                        ('\n' if parts[0] and not parts[0].endswith('\n') else
                         '') +
                        complete_cmd +
                        ''.join(parts[3::3]))

    @classmethod
    def escape(cls, str):
        if '"' in str or '(' in str or ')' in str:
            return '"' + str.replace('"', '\\"') + '"'
        else:
            return str

    def update(self):
        if self.cur_content != self.content:
            open(self.filename, 'wt').write(self.content)
            return True
        else:
            return False


class CustomTypeContainer:
    pass


class TestSetup(BuildInDefs):

    _BUILD_DIR_ = 'cmake-build-debug'
    DELAYED_PARSEERROR_REPORTING = True

    __test__ = False   # avoid that pytest/nose/... collect this as test

    __parser_factory__ = CParser

    ### provide structs with packing 1

    @classmethod
    def get_mingw_dir(cls):
        mingw64_dir = Path(os.environ.get('MINGW64_DIR', DEFAULT_MINGW64_DIR))
        envs = list(mingw64_dir.glob(r'i686-*-*-dwarf-rt_v5-*\mingw32'))
        if not envs:
            raise BuildError(f'no MinGW64 found in {mingw64_dir} '
                             f'(see MINGW64_DIR environment variable)')
        envs.sort()
        return envs[-1]

    @classmethod
    def get_mingw_include_dirs(cls):
        yield cls.get_mingw_dir() / 'i686-w64-mingw32' / 'include'

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
        return os.path.join(cls.get_src_dir(), cls._BUILD_DIR_)

    @classmethod
    def get_ts_name(cls):
        if len(cls._base_source_files) == 0:
            return cls.__name__
        else:
            c_files = [f for f in cls._base_source_files
                       if f.lower().endswith('.c')]
            mainfile = c_files[0] if c_files else cls._base_source_files[0]
            main, _ = os.path.splitext(os.path.basename(mainfile))
            return main + '_' + cls.__name__

    @classmethod
    def get_mock_proxy_path(cls):
        return os.path.join(cls.get_build_dir(), f'{cls.get_ts_name()}_mocks.c')

    @classmethod
    def get_makefile_path(cls):
        return os.path.join(cls.get_build_dir(), 'Makefile')

    @classmethod
    def __parse__(cls):
        root_dir = cls.get_root_dir()
        cls.__parser = cls.__parser_factory__(
            cls._predef_macros,
            cls.__get_include_dirs__(),
            list(map(str, cls.get_mingw_include_dirs())))
        for srcfile in cls._base_source_files:
            abs_srcfile = os.path.join(root_dir, srcfile)
            cls.__parser.read(abs_srcfile, patches=cls._get_patches())

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        cls._base_source_files = list()
        cls._predef_macros = {}
        cls._delayed_exc = None

        try:
            cls.__parse__()
        except ParseError as exc:
            exc = CompileError(exc.errors, cls)
            if cls.DELAYED_PARSEERROR_REPORTING:
                cls._delayed_exc = exc
            else:
                raise exc

        for name, typedef in cls.__parser.typedefs.items():
            setattr(cls, name, typedef)

        cls.struct = CustomTypeContainer()
        cls.enum = CustomTypeContainer()
        for name, typedef in cls.__parser.structs.items():
            if issubclass(typedef, CStruct):
                setattr(cls.struct, name, typedef)
            elif issubclass(typedef, CEnum):
                setattr(cls.enum, name, typedef)

        cls.__eval_macros()

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
    def _get_patches(cls):
        # fix _mingw.h (it contains "#define __attribute__()  /* nothing */
        # which makes __attribute__((annotate("..."))) not work any more)
        mingw_h_paths = (d / '_mingw.h' for d in cls.get_mingw_include_dirs())
        [mingw_h_path] = filter(Path.exists, mingw_h_paths)
        patches = {str(mingw_h_path):
                   ATTR_MACRO_DEF.sub(rb'#define __attribute__REDIRECTED__',
                                      mingw_h_path.read_bytes())}
        return patches

    @classmethod
    def __logger__(cls):
        return None

    @classmethod
    def __get_include_dirs__(cls):
        return []

    @classmethod
    def __add_source_file__(self, file_name):
        self._base_source_files.append(file_name)

    @classmethod
    def __add_macro__(self, name, value=''):
        self._predef_macros[name] = value

    def __build__(self):
        parser = self.__parser

        def mock_proxy_generator():
            def not_implemented(name_and_type_tuple):
                name, typ = name_and_type_tuple
                return name not in parser.implementations
            def iter_in_dep_order(only_full_defs=False):
                already_processed = set()
                for objtype in itertools.chain(mock_funcs.values(),
                                               global_vars.values()):
                    for req_type_name in objtype.iter_req_custom_types(
                            only_full_defs, already_processed):
                        yield req_type_name
            global_vars = dict(filter(not_implemented, parser.vars.items()))
            mock_funcs = dict(filter(not_implemented, parser.funcs.items()))
            yield '/* This file is automaticially generated by testsetup.py. *\n'
            yield ' * DO NOT MODIFY IT MANUALLY.                             */\n'
            yield '\n'
            if mock_funcs or global_vars:
                for struct_name in iter_in_dep_order():
                    struct = parser.structs[struct_name]
                    yield struct.c_definition() + ';\n'
                for struct_name in iter_in_dep_order(only_full_defs=True):
                    struct = parser.structs[struct_name]
                    yield struct.c_definition_full() + ';\n'
            yield '\n'
            for varname, var in sorted(global_vars.items()):
                yield var.c_definition(varname) + ';\n'
            yield '\n'
            for funcname, func in sorted(mock_funcs.items()):
                yield func.c_definition(f'(* {funcname}_mock)') + ' = 0;\n'
            yield '\n'
            for funcname, func in sorted(mock_funcs.items()):
                yield '\n'
                yield func.c_definition(funcname) + '\n'
                yield '{\n'
                yield '\treturn ' if func.returns is not None else '\t'
                params = ', '.join(f'p{pndx}' for pndx in range(len(func.args)))
                yield f'(* {funcname}_mock)({params});\n'
                yield '}\n'

        def mock_proxy_writer():
            with open(self.get_mock_proxy_path(), 'wt') as f:
                for text_chunk in mock_proxy_generator():
                    f.write(text_chunk)

        def cmakelist_rel_path(source_file):
            return source_file if os.path.isabs(source_file) \
                   else os.path.relpath(source_file, self.get_src_dir())

        def update_cmakelist():
            ts_name = self.get_ts_name()

            cmakelist = CMakeList(os.path.join(self.get_src_dir(),
                                               'CMakeLists.txt'))

            project_name='_'.join(self.get_src_dir().split(os.path.sep)[-2:])
            cmakelist.set('project', project_name + ' LANGUAGES C')
            cmakelist.set('cmake_minimum_required', 'VERSION 3.6')
            cmakelist.set('set', key_param='CMAKE_CONFIGURATION_TYPES',
                          params='Debug CACHE STRING "" FORCE')

            src_files = {*self.__parser.source_files, self.get_mock_proxy_path()}
            src_files_str = ''.join(
                '\n    ' + cmakelist_rel_path(source_file)
                for source_file in sorted(src_files)) \
                .replace(os.path.sep, '/')
            cmakelist.set('add_library', key_param=ts_name,
                          params='SHARED' + src_files_str)

            defines_str = ''.join(
                '\n    ' + cmakelist.escape(name + ('='+str(val)
                                                    if val is not None
                                                    else ''))
                for name, val in sorted(self._predef_macros.items()))
            cmakelist.set('target_compile_definitions', key_param=ts_name,
                          params='PUBLIC' + defines_str)

            incl_dirs_str = ''.join(
                '\n    ' + cmakelist_rel_path(incl_dir)
                for incl_dir in sorted(self.__parser.include_dirs)) \
                .replace(os.path.sep, '/')
            cmakelist.set('target_include_directories', key_param=ts_name,
                          params=f'PUBLIC' + incl_dirs_str)

            return cmakelist.update()

        def build_makefile():
            mingw_path_env = os.environ.copy()
            mingw_path_env['PATH'] = str(self.get_mingw_dir() / 'bin') \
                                     + ';' + mingw_path_env['PATH']
            try:
                completed_run = subprocess.run(
                    ['cmake', '-G', 'MinGW Makefiles', self.get_src_dir()],
                    cwd=self.get_build_dir(),
                    env=mingw_path_env,
                    encoding='ascii',
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                try:
                    os.remove(self.get_makefile_path())
                except OSError:
                    pass
                raise BuildError(f'failed to call cmake: {e}', type(self))
            else:
                if completed_run.returncode != 0:
                    return BuildError('CMAKE ERROR(S):' + completed_run.stderr,
                                      type(self))

        def build_dll():
            try:
                completed_proc = subprocess.run(
                    [str(self.get_mingw_dir() / 'bin' / 'mingw32-make'),
                     self.get_ts_name()],
                    cwd=self.get_build_dir(),
                    encoding='ascii',
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                raise BuildError(f'failed to call mingw32-make: {e}',
                                 type(self))
            else:
                if completed_proc.returncode != 0:
                    raise BuildError(completed_proc.stderr, type(self))

        if not DISABLE_AUTOBUILD:
            force_build_makefile = update_cmakelist()
            if not os.path.exists(self.get_build_dir()):
                os.makedirs(self.get_build_dir())
            if not os.path.exists(self.get_makefile_path()):
                force_build_makefile = True
            mock_proxy_writer()
            if force_build_makefile:
                build_makefile()
            build_dll()

    def __load__(self):
        self.__dll = ct.CDLL(os.path.join(self.get_build_dir(),
                                          'lib' + self.get_ts_name() + '.dll'))
        try:
            for name, cfunc_type in self.__parser.funcs.items():
                if name not in self.__parser.implementations:
                    self.__load_mock(name, cfunc_type)
                cfunc = cfunc_type(getattr(self.__dll,name),
                                   logger=self.__logger__())
                setattr(self, name, cfunc)
            for name, cvar_type in self.__parser.vars.items():
                ctypes_var = cvar_type.ctypes_type.in_dll(self.__dll, name)
                setattr(self, name, cvar_type(ctypes_var))
        except:
            self.__unload__()
            raise

    def __startup__(self):
        self.__load__()

    @classmethod
    def c_mixin(cls, *source_files, **defines):
        this_class = None
        def __parse__(cls):
            for name, content in defines.items():
                cls.__add_macro__(name, content)
            for source_file in source_files:
                cls.__add_source_file__(source_file)
            super(cls if this_class is None else this_class, cls).__parse__()
        if source_files:
            [name, _] = os.path.splitext(os.path.basename(source_files[0]))
        else:
            name = 'TSUnnamed'
        this_class = type(name.capitalize(),
                         (cls,),
                         {'__parse__': classmethod(__parse__)})
        return this_class

    def __load_mock(self, name, cfunc_type):
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

    @classmethod
    def __eval_macros(cls):
        def override_macro(macro):
            if hasattr(cls, macro):
                return getattr(cls, macro)
        for name in cls.__parser.macros:
            setattr(cls, name, cls.__parser.macros[name])

    def __shutdown__(self):
        for event, args in reversed(self.__unload_events):
            event(*args)

    def __unload__(self):
        self.__shutdown__()
        for name, cfunc_type in self.__parser.funcs.items():
            delattr(self, name)
        for name, cvar_type in self.__parser.vars.items():
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
