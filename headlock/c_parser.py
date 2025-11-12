import operator
import re
import os
import sys
import platform
from pathlib import Path
import warnings
from typing import Dict, List, Any, Union

from .libclang.cindex import CursorKind, StorageClass, TypeKind, \
    TranslationUnit, Config, TranslationUnitLoadError, LibclangError, Type
from .c_data_model import BuildInDefs, CProxyType, CFuncType, CStructType, \
    CUnionType, CEnumType, CVectorType, CStruct, CUnion, CEnum, CArrayType


if sys.platform == 'win32':
    if platform.architecture()[0] == '32bit':
        default_llvm_dir = r'C:\Program Files (x86)\LLVM\bin'
    else:
        default_llvm_dir = r'C:\Program Files\LLVM\bin'
elif sys.platform == 'linux':
    import glob
    default_llvm_dir = max(glob.glob(r'/usr/lib/llvm-*/lib'))
elif sys.platform == 'darwin':
    import glob
    # Try Homebrew installation first, then system locations
    homebrew_paths = glob.glob('/usr/local/opt/llvm*/lib') + \
                     glob.glob('/opt/homebrew/opt/llvm*/lib')
    if homebrew_paths:
        default_llvm_dir = max(homebrew_paths)
    else:
        # Fallback to Xcode Command Line Tools
        default_llvm_dir = '/Library/Developer/CommandLineTools/usr/lib'
else:
    raise NotImplementedError('This operating system is not supported yet')
Config.set_library_path(os.environ.get('LLVM_DIR', default_llvm_dir))
Config.set_required_version(7, 0, 0)


class ParseError(Exception):
    """
    failed to parse the source code
    """

    def __init__(self, errs):
        self.errors = errs

    def __str__(self):
        desc, fname, fline = self.errors[0]
        return f'{len(self.errors)} compile errors ({desc} in {fname}:{fline})'

    def __iter__(self):
        yield from self.errors



class MacroDef:

    REGEX_WORD = re.compile(r'\b[A-Za-z_]\w*', re.ASCII)
    REGEX_VAR = re.compile(r'\b(?P<varname>[A-Za-z_]\w*)'
                           r'(?P<attrs>\s*\.\s*[A-Za-z_]\w*)*', re.ASCII)
    REGEX_COMMENT = re.compile(r'/\*.*?\*/|//.*?$', re.DOTALL|re.MULTILINE)
    REGEX_CAST = re.compile(r'\(\s*(?P<basetype>[A-Za-z_]\w*'
                            r'(\s*\.\s*[A-Za-z_]\w+)*)'
                            r'\s*(?P<ptrs>(\*\s*)*)\)', re.ASCII)
    REGEX_INTLITERAL = re.compile(r'('
                                  r'0[xX](?P<hex>[0-9A-Fa-f]+)|'
                                  r'0+(?P<oct>\d+)|'
                                  r'(?P<dec>\d+)|'
                                  r'0[bB](?P<bin>[01]+)'
                                  r')[uU]?[Ll]{0,2}', re.ASCII)

    class Caster:
        """
        This is a helper class needed to implement type casts
        without needed to parse the C code.

        It allows to write "int.ptr(x)" as "Caster(int.ptr) ** x" which is
        needed if the end of the expression "x" is unkown
        """

        def __init__(self, cast_type):
            self.cast_type = cast_type

        def __pow__(self, power, modulo=None):
            return self.cast_type(power)

    def __init__(self, name, code=None, params=None, valid=True):
        self.name = name
        self.code = code
        self.params = params
        self.valid = valid

    def __eq__(self, other):
        if not isinstance(other, MacroDef):
            return NotImplemented
        else:
            return (self.name == other.name
                   and ((not self.code or self.code.co_code) ==
                        (not other.code or other.code.co_code))
                   and self.params == other.params
                   and self.valid == other.valid)

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return f'{type(self).__name__}({self.name!r}, {self.code!r}, ' \
               f'{self.params!r}, {self.valid!r})'

    @classmethod
    def create_from_srccode(cls, content):
        name_mobj = cls.REGEX_WORD.match(content)
        if name_mobj is None:
            raise ParseError([(f'"#define {content}" is an invalid definition',
                               None, None)])
        name_end = name_mobj.end(0)
        if content[name_end:name_end+1] == '(':
            params_end = content.find(')')
            params_str = content[name_end+1:params_end].strip()
            if params_str == '':
                params = ()
            else:
                params = tuple(map(str.strip, params_str.split(',')))
            src_code = content[params_end + 1:]
            def add_resolver(mobj):
                return mobj[0] if mobj['varname'] in params else 'self.'+mobj[0]
        else:
            params = None
            src_code = content[name_end:]
            add_resolver = r"self.\g<0>"
        def caster(mobj):
            if params is not None and mobj['basetype'] in params:
                return mobj['basetype']
            else:
                return '__Caster__({basetype}{ptrs}) ** '.format(
                    basetype=mobj["basetype"],
                    ptrs=mobj['ptrs'].replace('*', '.ptr'))
        def intliteral(mobj):
            if mobj['dec']:
                return mobj['dec']
            elif mobj['hex']:
                return '0x' + mobj['hex']
            elif mobj['oct']:
                return '0o' + mobj['oct']
            elif mobj['bin']:
                return '0b' + mobj['bin']
        src_code = src_code.replace('struct', 'struct.')
        src_code = src_code.replace('union', 'union.')
        src_code = src_code.replace('enum', 'enum.')
        src_code = src_code.replace('->', '.ref.')
        src_code = cls.REGEX_INTLITERAL.sub(intliteral, src_code)
        src_code = cls.REGEX_VAR.sub(add_resolver, src_code)
        src_code = cls.REGEX_CAST.sub(caster, src_code)
        src_code = cls.REGEX_COMMENT.sub(' ', src_code)
        src_code = cls.REGEX_COMMENT.sub(' ', src_code)
        src_code = src_code.replace('/', '//')
        src_code = src_code.replace('?', 'and')
        src_code = src_code.replace(':', 'or')
        src_code = src_code.replace('\r\n', '\n')
        src_code = src_code.replace('\\\n', ' ')
        src_code = src_code.strip()
        valid = True
        if src_code == '':
            code = None
        else:
            try:
                with warnings.catch_warnings(record=True):
                    code = compile(src_code, '<string>', 'eval')
            except SyntaxError:
                code = None
                valid = False
        return MacroDef(name_mobj[0], code, params, valid)

    def __get__(self, instance, owner):
        context_vars = dict(self=instance or owner,
                            __Caster__=self.Caster)
        if not self.valid:
            raise ValueError(f'Macro {self.name} cannot be evaluted in python')
        elif self.code is None:
            return None
        elif self.params is None:
            return eval(self.code, None, context_vars)
        else:
            def macro_evaluator(*args):
                return eval(self.code,
                            dict(zip(self.params, args)),
                            context_vars)
            return macro_evaluator


class CParser:

    INLINE_ATTR_TEXT = 'converted-inline'
    CDECL_ATTR_TEXT = 'converted-cdecl'
    DEFAULT_PACKING = None

    GCC_VECTOR_BUILTINS = {
        'addss': '__m128', 'subss': '__m128', 'mulss': '__m128',
        'divss': '__m128', 'andps': '__m128', 'andnps': '__m128',
        'orps': '__m128', 'xorps': '__m128', 'movss': '__m128',
        'cmpgtps': '__m128', 'cmpgeps': '__m128', '__cmpneqps': '__m128',
        'cmpngtps': '__m128', 'cmpngeps': '__m128', 'cvtsi2ss': '__m128',
        'movlhps': '__m128', 'movhlps': '__v4sf', 'unpckhps': '__m128',
        'unpcklps': '__m128', 'loadhps': '__m128', 'loadlps': '__m128',
        'movntq': '__m128', 'movsd': '__m128d', 'addsd': '__m128d',
        'subsd': '__m128d', 'mulsd': '__m128d', 'divsd': '__m128d',
        'andpd': '__m128d', 'andnpd': '__m128d', 'orpd': '__m128d',
        'xorpd': '__m128d', 'cmpgtpd': '__m128d', 'cmpgepd': '__m128d',
        'cmpneqpd': '__m128d', 'cmpnltpd': '__m128d', 'cmpngtpd': '__m128d',
        'cmpngepd': '__m128d', 'cmpordpd': '__m128d', 'cmpunordpd': '__m128d',
        'cmpeqsd': '__m128d', 'cmpltsd': '__m128d', 'cmplesd': '__m128d',
        'movq128': '__m128d', 'cvtdq2pd': '__m128d', 'cvtdq2ps': '__m128d',
        'cvtps2pd': '__m128d', 'cvttsd2si': 'int', 'cvtss2sd': '__m128d',
        'unpckhpd': '__m128d', 'unpcklpd': '__m128d', 'cvtsi2sd': '__m128d',
        'loadhpd': '__m128d', 'loadlpd': '__m128d', 'punpckhbw128': '__m128d',
        'punpckhwd128': '__m128d', 'punpckhdq128': '__m128d',
        'punpckhqdq128': '__m128d', 'punpcklbw128': '__m128d',
        'punpcklwd128': '__m128d', 'punpckldq128': '__m128d',
        'punpcklqdq128': '__m128d', 'pandn128': '__m128d',
        'pavgb128': '__m128d', 'pavgw128': '__m128d',
        'cvtsi642ss': '__m128', 'cvtsi642ss': '__m128', 'cvtsi642sd': '__m128d',
        'cvtsi642sd': '__m128d', 'paddsb128': '__m128i', 'paddsw128': '__m128i',
        'paddusb128': '__m128i', 'paddusw128': '__m128i',
        'psubsb128': '__m128i', 'psubsw128': '__m128i', 'psubusb128': '__m128i',
        'psubusw128': '__m128i', 'pmaxsw128': '__m128i', 'pmaxub128': '__m128i',
        'pminsw128': '__m128i', 'pminub128': '__m128i',
        'movntps': '__m128', 'movntdq': '__m128', 'movntpd': '__m128'}
    GCC_ZEROTYPE_MAP = {
        '__m128': '_mm_setzero_ps()', '__v4sf': '_mm_setzero_ps()',
        '__m128d': '__extension__(__m128){0,0,0,0}', 'int': '0',
        '__m128i': '_mm_setzero_pd()'}

    def __init__(self, predef_macros:Dict[str, Any]=None,
                 include_dirs:List[Path]=None,
                 sys_include_dirs:List[Path]=None,
                 sys_whitelist:List[str]=None,
                 target_compiler:str=None):
        super().__init__()
        self.__resolve_cache:Dict[str, Path] = {}
        self.__syshdr_cache:Dict[str, bool] = {}
        self.__sys_typedefs:Dict[str, Type] = {}
        self.include_dirs = list(map(self.resolve, include_dirs or []))
        self.sys_include_dirs = list(map(self.resolve, sys_include_dirs or []))
        self.sys_whitelist = frozenset(sys_whitelist or [])
        self.predef_macros = predef_macros.copy() if predef_macros else {}
        annotate = '__attribute__((annotate("{}")))'.format
        self.predef_macros.update(
            __cdecl=annotate(self.CDECL_ATTR_TEXT),
            __forceinline=annotate(self.INLINE_ATTR_TEXT),
            __inline=annotate(self.INLINE_ATTR_TEXT),
            forceinline=annotate(self.INLINE_ATTR_TEXT),
            inline=annotate(self.INLINE_ATTR_TEXT))
        self.macro_locs = {}
        self.macros = {nm: MacroDef.create_from_srccode(f'{nm} {content or ""}')
                       for nm, content in self.predef_macros.items()}
        self.typedefs = {n: t for n, t in BuildInDefs.__dict__.items()
                         if isinstance(t, CProxyType)}
        self.structs = {}
        self.vars = {}
        self.funcs = {}
        self.implementations = set()
        self.source_files = set()
        self.target_compiler = target_compiler

    def convert_compount_from_cursor(self, cmpnd_crs:Type) \
            -> Union[CStruct, CUnion]:
        try:
            struct_type = self.structs[cmpnd_crs.displayname]
        except KeyError:
            pytype = (CStructType if cmpnd_crs.kind == CursorKind.STRUCT_DECL
                      else CUnionType)
            if cmpnd_crs.displayname.startswith("struct (unnamed at"):
                name = ""
            else:
                name = cmpnd_crs.displayname
            struct_type = pytype(name, packing=self.DEFAULT_PACKING)
            self.structs[struct_type.struct_name] = struct_type
        else:
            if struct_type._members_:
                return struct_type

        members = []
        for member_cursor in cmpnd_crs.get_children():
            if member_cursor.kind == CursorKind.FIELD_DECL:
                member_type = self.convert_type_from_cursor(member_cursor.type)
                members.append( (member_cursor.displayname, member_type) )
            else:
                self.convert_datatype_decl_from_cursor(member_cursor)
        if members or struct_type._members_ is None:
            struct_type.delayed_def(members)
        return struct_type

    def convert_enum_from_cursor(self, enum_crs:Type) -> CEnum:
        try:
            enum_type = self.structs[enum_crs.displayname]
        except KeyError:
            enum_type = CEnumType(enum_crs.displayname)
            if enum_crs.displayname:
                self.structs[enum_crs.displayname] = enum_type
        return enum_type

    def convert_datatype_decl_from_cursor(self, cursor:Type) \
            -> Union[CStruct, CEnum, CUnion]:
        if cursor.displayname and not "(unnamed at" in cursor.displayname:
            if cursor.kind == CursorKind.STRUCT_DECL:
                return self.convert_compount_from_cursor(cursor)
            elif cursor.kind == CursorKind.ENUM_DECL:
                return self.convert_enum_from_cursor(cursor)
            elif cursor.kind == CursorKind.UNION_DECL:
                return self.convert_compount_from_cursor(cursor)

    def convert_type_from_cursor(self, type_crs:Type):
        def is_function_proto(cursor):
            # due to a bug in libclang (v4.0) TypeKind.FUNCTIONPROTO does
            # not work on function pointers. This this helper does
            # the corresponding check
            return cursor.get_result().kind != TypeKind.INVALID

        if type_crs.kind == TypeKind.POINTER:
            res = self.convert_type_from_cursor(type_crs.get_pointee()).ptr
        elif type_crs.kind == TypeKind.CONSTANTARRAY:
            element_type = self.convert_type_from_cursor(type_crs.element_type)
            res = element_type.array(type_crs.element_count)
        elif type_crs.kind == TypeKind.INCOMPLETEARRAY:
            element_type = self.convert_type_from_cursor(type_crs.element_type)
            res = element_type.array(0)
        elif type_crs.kind == TypeKind.RECORD:
            res = self.convert_compount_from_cursor(type_crs.get_declaration())
        elif type_crs.kind == TypeKind.ENUM:
            res = self.convert_enum_from_cursor(type_crs.get_declaration())
        elif type_crs.kind == TypeKind.VECTOR:
            res = CVectorType()
        elif is_function_proto(type_crs) and type_crs.kind != TypeKind.TYPEDEF:
            if type_crs.get_result().kind == TypeKind.VOID:
                ret_objtype = None
            else:
                ret_objtype = self.convert_type_from_cursor(
                    type_crs.get_result())
            arg_cproxytypes = []
            for param in type_crs.argument_types():
                arg_cproxytype = self.convert_type_from_cursor(param)
                if isinstance(arg_cproxytype, CArrayType):
                    arg_cproxytype = arg_cproxytype.base_type.ptr
                arg_cproxytypes.append(arg_cproxytype)
            res = CFuncType(ret_objtype, arg_cproxytypes)
        elif type_crs.kind == TypeKind.ELABORATED:
            decl_cursor = type_crs.get_declaration()
            struct_name = decl_cursor.displayname
            try:
                struct_def = self.structs[struct_name]
            except KeyError:
                # a struct could not be found in self.structs for two reasons:
                # - its an anonymous struct (without struct_name == '')
                # - it was defined in system header file and thus skipped for
                #   performance reasons
                struct_def = self.convert_type_from_cursor(decl_cursor.type)
            res = struct_def
        else:
            typedef_name = type_crs.spelling.replace(' ', '_')
            if type_crs.is_const_qualified():
                typedef_name = typedef_name.replace('const_', '')
            if type_crs.is_volatile_qualified():
                typedef_name = typedef_name.replace('volatile_', '')
            try:
                res = self.typedefs[typedef_name]
            except KeyError:
                # type was defined in system header files and not yet parsed
                typedef_typ = type_crs.get_declaration().underlying_typedef_type
                res = self.convert_type_from_cursor(typedef_typ)
                self.typedefs[typedef_name] = res
        if type_crs.is_const_qualified():
            res = res.with_attr('const')
        if type_crs.is_volatile_qualified():
            res = res.with_attr('volatile')
        return res

    def read_from_cursor(self, cursor):

        def has_attr(cursor, kind, name=None):
            return any(c.kind == kind and (name is None or c.spelling == name)
                       for c in cursor.get_children())

        for sub_cursor in cursor.get_children():
            start = sub_cursor.extent.start
            if start.file and self.is_sys_hdr(start.file.name) \
                    and sub_cursor.spelling not in self.sys_whitelist:
                if sub_cursor.kind == CursorKind.TYPEDEF_DECL:
                    self.__sys_typedefs[sub_cursor.displayname] = \
                                              sub_cursor.underlying_typedef_type
            elif sub_cursor.kind == CursorKind.MACRO_DEFINITION:
                if start.file is not None:
                    self.macro_locs[sub_cursor.displayname] = (
                        start.file.name,
                        start.offset,
                        sub_cursor.extent.end.offset)
            elif sub_cursor.kind == CursorKind.FUNCTION_DECL \
                    and sub_cursor.storage_class != StorageClass.STATIC:
                # ignore inline functions and dllimport-functions
                if not has_attr(sub_cursor, CursorKind.ANNOTATE_ATTR,
                                self.INLINE_ATTR_TEXT) \
                        and not has_attr(sub_cursor, CursorKind.DLLIMPORT_ATTR):
                    ctype = self.convert_type_from_cursor(sub_cursor.type)
                    if has_attr(sub_cursor, CursorKind.ANNOTATE_ATTR,
                                self.CDECL_ATTR_TEXT):
                        ctype = ctype.with_attr('__cdecl')
                    self.funcs[sub_cursor.spelling] = ctype
                    if any(c.kind == CursorKind.COMPOUND_STMT
                           for c in sub_cursor.get_children()):
                        self.implementations.add(sub_cursor.spelling)
                elif sub_cursor.spelling in self.funcs:
                    del self.funcs[sub_cursor.spelling]
            elif sub_cursor.kind == CursorKind.TYPEDEF_DECL:
                typedef_cursor = sub_cursor.underlying_typedef_type
                ctype = self.convert_type_from_cursor(typedef_cursor)
                self.typedefs[sub_cursor.displayname] = ctype
            elif sub_cursor.kind == CursorKind.VAR_DECL \
                    and sub_cursor.storage_class != StorageClass.STATIC:
                ctype = self.convert_type_from_cursor(sub_cursor.type)
                self.vars[sub_cursor.displayname] = ctype
                if sub_cursor.storage_class == StorageClass.NONE:
                    self.implementations.add(sub_cursor.displayname)
            else:
                self.convert_datatype_decl_from_cursor(sub_cursor)


    def read(self, file_name:os.PathLike,
             patches:Dict[os.PathLike, bytes]=None):
        patches = patches or {}
        def sys_inc_dir_args(sys_include_dirs):
            for sys_inc_dir in sys_include_dirs:
                yield '-isystem'
                yield os.fspath(sys_inc_dir)
        try:
            _ = Config.lib
        except Exception as exc:
            raise ParseError('Failed to load libclang: ' + str(exc))
        try:
            predefs = self.predef_macros.copy()
            predefs.update({'_mm_getcsr': '_mm_getcsr_CLANG',
                            '_mm_setcsr': '_mm_setcsr_CLANG',
                            '_mm_sfence': '_mm_sfence_CLANG',
                            '_mm_pause': '_mm_pause_CLANG',
                            '_mm_clflush': '_mm_clflush_CLANG',
                            '_mm_lfence': '_mm_lfence_CLANG',
                            '_mm_mfence': '_mm_mfence_CLANG',
                            '__rdtsc': '__rdtsc_CLANG',
                            '__builtin_shuffle(...)':
                                self.GCC_ZEROTYPE_MAP['__m128d'],
                            '__iamcu__': '1'})
            predefs.update({
                f'__builtin_ia32_{nm}(...)': self.GCC_ZEROTYPE_MAP[tp]
                for nm, tp in self.GCC_VECTOR_BUILTINS.items()})
            tu = TranslationUnit.from_source(
                os.fspath(file_name),
                unsaved_files=[(os.fspath(nm), c.decode('ascii'))
                               for nm, c in patches.items()],
                args=[f'-I{os.fspath(incdir)}' for incdir in self.include_dirs]
                     + [f'-D{mname}={mval or ""}'
                        for mname, mval in predefs.items()]
                     + list(sys_inc_dir_args(self.sys_include_dirs))
                     + ([] if not self.target_compiler
                        else [f'--target={self.target_compiler}'])
                    + ['-ferror-limit=0'],
                options=TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)
        except LibclangError as e:
            raise ParseError(str(e) + "\nMaybe libclang library is not found. "
                             "You might specify its path with LLVM_DIR")
        except TranslationUnitLoadError as e:
            raise FileNotFoundError(
                f'File {os.fspath(file_name)} cannot be opened/is invalid') \
                from e
        self.source_files.add(self.resolve(os.fspath(file_name)))
        for incl_file_obj in tu.get_includes():
            incl_file_path = incl_file_obj.include.name
            if not self.is_sys_hdr(incl_file_path):
                self.source_files.add(self.resolve(incl_file_path))
        errors = [diag for diag in tu.diagnostics
                   if diag.severity >= diag.Error
                   and not (diag.location.file is not None and self.is_sys_hdr(str(diag.location.file)))]
        if errors:
            raise ParseError([
                (err.spelling, err.location.file.name if err.location.file else "<unknown>", err.location.line)
                for err in errors[:20]])
        self.read_from_cursor(tu.cursor)
        filenames = set(map(operator.itemgetter(0), self.macro_locs.values()))
        files = {self.resolve(fn): Path(fn).read_bytes() for fn in filenames}
        files.update({Path(nm).resolve(): c for nm, c in patches.items()})
        for macro_name, (fn, start, end) in self.macro_locs.items():
            fcontent = files[self.resolve(fn)]
            macro_text = fcontent[start:end].replace(b'\n\f', b'\n')
            macro_def = MacroDef.create_from_srccode(macro_text.decode('ascii'))
            self.macros[macro_name] = macro_def

    def is_sys_hdr(self, src_filename:str):
        def is_parent_of_src_filename(root_dir):
            try:
                self.resolve(src_filename).relative_to(root_dir)
            except ValueError:
                return False
            else:
                return True
        try:
            is_sys_hdr = self.__syshdr_cache[src_filename]
        except KeyError:
            is_sys_hdr = any(map(is_parent_of_src_filename,
                                 self.sys_include_dirs))
            self.__syshdr_cache[src_filename] = is_sys_hdr
        return is_sys_hdr

    def resolve(self, path:str) -> Path:
        """
        Converts a string to a resolved path.
        This method is only for optimization purposes, as resolving needs
        quite a bit time and is done very often.
        """
        try:
            res_path_obj = self.__resolve_cache[path]
        except KeyError:
            res_path_obj = Path(path).resolve()
            self.__resolve_cache[path] = res_path_obj
        return res_path_obj
