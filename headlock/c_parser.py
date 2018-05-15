import re
import os
from pathlib import Path

from .libclang.cindex import CursorKind, StorageClass, TypeKind, \
    TranslationUnit, Config, TranslationUnitLoadError
from .c_data_model import BuildInDefs, CObjType, CFunc, CStruct, CEnum


Config.set_library_path(os.environ.get('LLVM_DIR', r'C:\Program Files (x86)\LLVM\bin'))
Config.set_required_version(7, 0, 0)


class ParseError(Exception):
    """
    failed to parse the source code
    """

    def __init__(self, errs):
        self.errors = errs

    def __str__(self):
        return f'{len(self.errors)} compile errors'

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
            return self.name == other.name \
                   and self.code == other.code \
                   and self.params == other.params \
                   and self.valid == other.valid

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
        src_code = src_code.strip()
        valid = True
        if src_code == '':
            code = None
        else:
            try:
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

    def __init__(self, predef_macros=None, include_dirs=None,
                 sys_include_dirs=None, target_compiler=None):
        super().__init__()
        self.include_dirs = include_dirs or []
        self.sys_include_dirs = sys_include_dirs or []
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
                         if isinstance(t, CObjType)}
        self.structs = {}
        self.vars = {}
        self.funcs = {}
        self.implementations = set()
        self.source_files = set()
        self.target_compiler = target_compiler

    def convert_struct_from_cursor(self, struct_crs):
        try:
            struct_type = self.structs[struct_crs.displayname]
        except KeyError:
            struct_type = CStruct.typedef(struct_crs.displayname,
                                          packing=self.DEFAULT_PACKING)
            self.structs[struct_type.__name__] = struct_type
        else:
            if len(struct_type._members_) > 0:
                return struct_type

        members = []
        for member_cursor in struct_crs.get_children():
            if member_cursor.kind == CursorKind.FIELD_DECL:
                member_type = self.convert_type_from_cursor(
                    member_cursor.type)
                members.append( (member_cursor.displayname, member_type) )
            else:
                self.read_datatype_decl_from_cursor(member_cursor)
        if members:
            struct_type.delayed_def(*members)
        return struct_type

    def convert_enum_from_cursor(self, enum_crs):
        try:
            enum_type = self.structs[enum_crs.displayname]
        except KeyError:
            enum_type = CEnum
            if enum_crs.displayname:
                self.structs[enum_crs.displayname] = enum_type
        return enum_type

    def read_datatype_decl_from_cursor(self, cursor):
        if cursor.displayname:
            if cursor.kind == CursorKind.STRUCT_DECL:
                self.convert_struct_from_cursor(cursor)
            elif cursor.kind == CursorKind.ENUM_DECL:
                self.convert_enum_from_cursor(cursor)

    def convert_type_from_cursor(self, type_crs):
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
            res = self.convert_struct_from_cursor(type_crs.get_declaration())
        elif type_crs.kind == TypeKind.ENUM:
            res = self.convert_enum_from_cursor(type_crs.get_declaration())
        elif is_function_proto(type_crs):
            if type_crs.get_result().kind == TypeKind.VOID:
                ret_objtype = None
            else:
                ret_objtype = self.convert_type_from_cursor(
                    type_crs.get_result())
            arg_cobjtypes = [self.convert_type_from_cursor(param)
                             for param in type_crs.argument_types()]
            res = CFunc.typedef(*arg_cobjtypes, returns=ret_objtype)
        elif type_crs.kind == TypeKind.ELABORATED:
            decl_cursor = type_crs.get_declaration()
            if decl_cursor.displayname:
                struct_def = self.structs[decl_cursor.displayname]
            else:
                struct_def = self.convert_type_from_cursor(decl_cursor.type)
            res = struct_def
        else:
            typedef_name = type_crs.spelling.replace(' ', '_')
            if type_crs.is_const_qualified():
                typedef_name = typedef_name.replace('const_', '')
            if type_crs.is_volatile_qualified():
                typedef_name = typedef_name.replace('volatile_', '')
            res = self.typedefs[typedef_name]
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
            if sub_cursor.kind == CursorKind.MACRO_DEFINITION:
                start = sub_cursor.extent.start
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
                        and not has_attr(sub_cursor, CursorKind.DLLIMPORT_ATTR)\
                        and not self.is_sys_func(
                            sub_cursor.extent.start.file.name):
                    cobj_type = self.convert_type_from_cursor(sub_cursor.type)
                    if has_attr(sub_cursor, CursorKind.ANNOTATE_ATTR,
                                self.CDECL_ATTR_TEXT):
                        cobj_type = cobj_type.with_attr('cdecl')
                    self.funcs[sub_cursor.spelling] = cobj_type
                    if any(c.kind == CursorKind.COMPOUND_STMT
                           for c in sub_cursor.get_children()):
                        self.implementations.add(sub_cursor.spelling)
                elif sub_cursor.spelling in self.funcs:
                    del self.funcs[sub_cursor.spelling]
                    if sub_cursor.spelling in self.implementations:
                        del self.implementations[sub_cursor.spelling]
            elif sub_cursor.kind == CursorKind.TYPEDEF_DECL:
                typedef_cursor = sub_cursor.underlying_typedef_type
                cobj_type = self.convert_type_from_cursor(typedef_cursor)
                self.typedefs[sub_cursor.displayname] = cobj_type
            elif sub_cursor.kind == CursorKind.VAR_DECL \
               and sub_cursor.storage_class != StorageClass.STATIC:
                cobj_type = self.convert_type_from_cursor(sub_cursor.type)
                self.vars[sub_cursor.displayname] = cobj_type
                if sub_cursor.storage_class == StorageClass.NONE:
                    self.implementations.add(sub_cursor.displayname)
            else:
                self.read_datatype_decl_from_cursor(sub_cursor)


    def read(self, file_name, patches=None):
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
            predefs = self.predef_macros.items()
            tu = TranslationUnit.from_source(
                os.fspath(file_name),
                unsaved_files=[(os.fspath(nm), c.decode('ascii'))
                               for nm, c in patches.items()],
                args=[f'-I{inc_dir}' for inc_dir in self.include_dirs]
                     + [f'-D{mname}={mval or ""}' for mname, mval in predefs]
                     + list(sys_inc_dir_args(self.sys_include_dirs))
                     + ([] if not self.target_compiler
                        else [f'--target={self.target_compiler}']),
                options=TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD)
        except TranslationUnitLoadError as e:
            raise FileNotFoundError(
                f'File {file_name} cannot be opened/is invalid') from e
        self.source_files.add(Path(file_name).resolve())
        self.source_files |= {Path(i.include.name).resolve()
                              for i in tu.get_includes()
                              if not self.is_sys_func(i.include.name)}
        errors = [diag for diag in tu.diagnostics
                   if diag.severity >= diag.Error]
        if errors:
            raise ParseError([
                (err.spelling, err.location.file.name, err.location.line)
                for err in errors if err.location.file is not None])
        self.read_from_cursor(tu.cursor)
        files = {Path(name).resolve(): Path(name).read_bytes()
                 for name, start, end in self.macro_locs.values()}
        files.update({Path(nm).resolve(): c for nm, c in patches.items()})
        for macro_name, (fname, start, end) in self.macro_locs.items():
            fcontent = files[Path(fname).resolve()]
            macro_text = fcontent[start:end].replace(b'\n\f', b'\n')
            macro_def = MacroDef.create_from_srccode(macro_text.decode('ascii'))
            self.macros[macro_name] = macro_def

    def is_sys_func(self, src_filename):
        return any(src_filename.startswith(os.fspath(sysdir))
                   for sysdir in self.sys_include_dirs)
