import contextlib
from unittest.mock import Mock, MagicMock
import pytest
from headlock.libclang.cindex import TranslationUnit
from headlock.c_parser import CParser, MacroDef, ParseError
from headlock.c_data_model import BuildInDefs as bd, CFunc, CStruct, CEnum
from tempfile import NamedTemporaryFile, TemporaryDirectory
import os


class TestParserError:

    SAMPLE_ERRORS = [('test.c', 33, 'Error message'),
                     ('test.c', 44, 'Another Message')]

    def test_str_returnsNumberOfErrors(self):
        err = ParseError(self.SAMPLE_ERRORS)
        assert str(len(self.SAMPLE_ERRORS)) in str(err)

    def test_iter_yieldsErrorTuples(self):
        err = ParseError(self.SAMPLE_ERRORS)
        assert list(err) == self.SAMPLE_ERRORS


class TestMacroDef:

    @pytest.fixture
    def obj(self):
        class BindObj: pass
        return BindObj()

    def test_init_setsAttrs(self):
        macro = MacroDef('NAME', '1 + 2', (), False)
        assert macro.name == 'NAME'
        assert macro.code == '1 + 2'
        assert macro.params == ()
        assert not macro.valid

    def assert_create_as(self, srccode, exp_expr=None, exp_params=None,
                         exp_valid=True, exp_name='MACRO'):
        pyexpr = compile(exp_expr, '<string>', 'eval') if exp_expr else None
        assert MacroDef.create_from_srccode(srccode) \
               == MacroDef(exp_name, pyexpr, exp_params, exp_valid)

    def test_createFromSrcCode_onEmptyMacro_returnsNone(self):
        self.assert_create_as('MACRO', None)

    def test_createFromSrcCode_onSpecialName_returnsNone(self):
        self.assert_create_as('OTHER_NAME', exp_name='OTHER_NAME')

    def test_createFromSrcCode_onSimpleInteger_returnsInt(self):
        self.assert_create_as('MACRO  3', '3')

    def test_createFromSrcCode_onComplexIntExpression_returnsResultInt(self):
        self.assert_create_as('MACRO (4*3 - 2) * 2', '(4*3-2)*2')

    def test_createFromSrcCode_onDiv_convertsToIntDiv(self):
        self.assert_create_as('MACRO 5 / 2', '5//2')

    def test_createFromSrcCode_onIfElseExpr_convertToAndOrExpr(self):
        self.assert_create_as('MACRO  1 ? 2 : 3', '1 and 2 or 3')

    def test_createFromSrcCode_onInvalidSyntax_setsValidToFalse(self):
        self.assert_create_as('MACRO  $invalid-code$', exp_valid=False)

    def test_createFromSrcCode_onRefToOtherMacros_resolvesMacros(self):
        self.assert_create_as('MACRO OTHERMACRO', "self.OTHERMACRO")

    def test_createFromSrcCode_onRefToOtherFuncMacros_resolvesMacros(self):
        self.assert_create_as('MACRO OTHERMACRO(1, 2)',
                              "self.OTHERMACRO(1, 2)")

    def test_createFromSrcCode_onMultipleRefs_resolvesMacros(self):
        self.assert_create_as('MACRO REF1 + REF2',
                              "self.REF1 + self.REF2")

    def test_createFromSrcCode_onSimpleTypeCast_replaceTypeCast(self):
        self.assert_create_as('MACRO (int)1',
                              "__Caster__(self.int) ** 1")

    def test_createFromSrcCode_onComplexTypeCast_replaceTypeCast(self):
        self.assert_create_as('MACRO ( int * ** ) 1 ',
                              "__Caster__(self.int.ptr.ptr.ptr) ** 1")

    def test_createFromSrcCode_onLineContinuation_lineContinuationWillBeRemoved(self):
        self.assert_create_as('MACRO 1 \\\n + \\\n2', '1+2')

    def test_createFromSrcCode_onEndOfLineComment_willBeRemoved(self):
        self.assert_create_as('MACRO  //comment')

    def test_createFromSrcCode_onBeginEndComment_willBeRemoved(self):
        self.assert_create_as('MACRO /* comment\n comment */  /**/ ')

    def test_createFromSrcCode_onFuncMacro_setsParams(self):
        self.assert_create_as('MACRO( )', exp_params=())

    def test_createFromSrcCode_onFuncMacroWithMultipleParams_setsParams(self):
        self.assert_create_as('MACRO( a, p2 ,CCC,s )',
                              exp_params=('a', 'p2', 'CCC', 's'))

    def test_createFromSrcCode_onReferenceToFuncParam_doNotResolve(self):
        self.assert_create_as('MACRO(a) a', 'a', exp_params=('a',))

    def test_get_onResolveStructAttr_ok(self):
        class Container:
            strct = Mock()
            macro = MacroDef.create_from_srccode('macro strct.member')
        Container.strct.member = "some content"
        assert Container.macro == "some content"

    def test_get_onResolveStructPtrAttr_ok(self):
        class Container:
            strct_ptr = Mock()
            macro = MacroDef.create_from_srccode('macro strct_ptr->member')
        Container.strct_ptr.ref.member = "some content"
        assert Container.macro == "some content"

    def test_get_onCastToStruct_ok(self):
        class Container:
            struct = Mock()
            macro = MacroDef.create_from_srccode('macro (struct name *)1')
        _ = Container.macro
        Container.struct.name.ptr.assert_called_with(1)

    def test_createFromSrcCode_onCastToUnion_ok(self):
        class Container:
            union = Mock()
            macro = MacroDef.create_from_srccode('macro (union name *)1')
        _ = Container.macro
        Container.union.name.ptr.assert_called_with(1)

    def test_createFromSrcCode_onCastToEnum_ok(self):
        class Container:
            enum = Mock()
            macro = MacroDef.create_from_srccode('macro (enum name)1')
        _ = Container.macro
        Container.enum.name.assert_called_with(1)

    def test_get_onEmptyMacro_returnsNone(self):
        class Container:
            macro = MacroDef('MACRO', None)
        assert Container.macro is None

    def test_get_onInvalidMacroDef_returnsNone(self):
        class Container:
            macro = MacroDef('MACRO', valid=False)
        with pytest.raises(ValueError):
            _ = Container.macro

    def test_get_onConstExpr_returnsCalcResult(self):
        class Container:
            macro = MacroDef.create_from_srccode('macro  3 + 2')
        assert Container.macro == 5

    def test_get_onFuncMacro_returnsCallable(self):
        class Container:
            macro = MacroDef.create_from_srccode('macro(a, b)  a + b')
        assert Container.macro(3, 4) == 7

    def test_get_onReferenceToConstMacros_resolvesReferencesToValues(self):
        class Container:
            macro = MacroDef.create_from_srccode('macro  constant')
            constant = 9
        assert Container.macro == 9

    def test_get_onReferenceToFuncMacros_resolvesReferencesToCallable(self):
        class Container:
            macro = MacroDef.create_from_srccode('macro  sub_macro(3)')
            @classmethod
            def sub_macro(cls, param):
                return param + 2
        assert Container.macro == 5

    def test_get_onNonFuncMacroPassesParams_raisesTypeError(self):
        class Container:
            macro = MacroDef('macro', '1')
        with pytest.raises(TypeError):
            _ = Container.macro(123)

    def test_get_onFuncMacroPassesWrongParamCount_raisesTypeError(self):
        class Container:
            macro = MacroDef.create_from_srccode('macro(a, b)')
        with pytest.raises(TypeError):
            Container.macro(1)
        with pytest.raises(TypeError):
            Container.macro(1, 2, 3)

    def test_get_onCast_returnsCastedValue(self):
        class Container:
            int = Mock()
            macro = MacroDef.create_from_srccode('macro (int*)1')
        Container.int.ptr.return_value="1 casted to int ptr"
        assert Container.macro == "1 casted to int ptr"

    def test_get_onCastCombinedWithOtherOps_useHighPrecedenceForCast(self):
        class Container:
            int = MagicMock()
            macro = MacroDef.create_from_srccode('macro (int*)1 * 2')
        _ = Container.macro
        Container.int.ptr.assert_called_with(1)

    def test_get_onInstanceReferenceToConstMacros_resolvesReferencesToValues(self):
        class Container:
            macro = MacroDef.create_from_srccode('macro  constant')
            constant = 9
        cont_inst = Container()
        assert cont_inst.macro == 9

    def test_get_onInstanceReferenceToFuncMacros_resolvesReferencesToCallable(self):
        class Container:
            macro = MacroDef.create_from_srccode('macro  sub_macro(3)')
            def sub_macro(cls, param):
                return param + 2
        cont_inst = Container()
        assert cont_inst.macro == 5


class TestCParser:

    def assert_parses(self, srccode, exp_typedefs=None, exp_structs=None,
                      exp_macro_locs=None, exp_funcs=None, exp_vars=None,
                      exp_impls=None):
        parser = CParser()
        exp_typedefs = exp_typedefs or {}
        exp_typedefs.update(parser.typedefs.copy())  # add builtin typedefs
        tu = TranslationUnit.from_source(
            'test.c',
            unsaved_files=[('test.c', srccode)],
            options=TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD
            )
        if tu.diagnostics:
            raise Exception(tu.diagnostics[0].spelling)
        parser.read_from_cursor(tu.cursor)
        assert parser.typedefs == exp_typedefs
        assert parser.structs == (exp_structs or {})
        assert parser.macro_locs == (exp_macro_locs or {})
        assert parser.funcs == (exp_funcs or {})
        assert parser.vars == (exp_vars or {})
        assert parser.implementations == (exp_impls or set())

    def assert_parses_as_type(self, srccode, exp_cobj_type):
        self.assert_parses('extern ' + srccode + ';',
                           exp_vars={'x': exp_cobj_type})

    def test_readFromCursor_onEmptyFile_addsNoEntries(self):
        self.assert_parses('', {})

    def test_readFromCursor_onCommentsOnly_addsNoEntries(self):
        self.assert_parses('/* comment1 */ // comment2', {})

    def test_readFromCursor_varDef_ok(self):
        self.assert_parses('extern int varname;',
                           exp_vars={'varname': bd.int})

    def test_readFromCursor_multipleVarDefs_ok(self):
        self.assert_parses('extern int var1, var2;'
                              'extern short var3;',
                           exp_vars={'var1': bd.int,
                                        'var2': bd.int,
                                        'var3': bd.short})

    def test_readFromCursor_nonExternVarDef_addsToImplementations(self):
        self.assert_parses('int varname;',
                           exp_vars={'varname': bd.int},
                           exp_impls={'varname'})

    def test_readFromCursor_onMixedExternAndNonExternVarDef_addsToImplementations(self):
        self.assert_parses(
            'extern int varname;'
            'int varname;'
            'extern int varname;',
            exp_vars={'varname': bd.int},
            exp_impls={'varname'})

    def test_convertTypeFromCursor_onTwoWordType_ok(self):
        self.assert_parses_as_type('unsigned int x', bd.unsigned_int)

    def test_readFromCursor_onConstInt_setConstFlag(self):
        self.assert_parses_as_type('const int x', bd.int.with_attr('const'))

    def test_readFromCursor_onVolatileVar_setIsVolatileFlag(self):
        self.assert_parses_as_type('volatile int x',
                                   bd.int.with_attr('volatile'))

    def test_convertTypeFromCursor_onPointerType_ok(self):
        self.assert_parses_as_type('int * x', bd.int.ptr)

    def test_readFromCursor_onConstPtr_setIsConstFlag(self):
        self.assert_parses_as_type('int * const x',
                                   bd.int.ptr.with_attr('const'))

    def test_convertTypeFromCursor_onRecursivePointerType_ok(self):
        self.assert_parses_as_type('int ** * x', bd.int.ptr.ptr.ptr)

    def test_convertTypeFromCursor_onArrayType_ok(self):
        self.assert_parses_as_type('int x[10]', bd.int[10])

    def test_convertTypeFromCursor_onSimpleFuncPtr_ok(self):
        self.assert_parses_as_type('void (*x)()', CFunc.typedef().ptr)

    def test_convertTypeFromCursor_onFuncPtrWithVoidParam_ok(self):
        self.assert_parses_as_type('void (*x)(void)', CFunc.typedef().ptr)

    def test_convertTypeFromCursor_onFuncPtrWithMultiplePtrs_ok(self):
        self.assert_parses_as_type('void (*x)(int a, char)',
                                   CFunc.typedef(bd.int, bd.char).ptr)

    def test_convertTypeFromCursor_onFuncPtrWithNonVoidResult_ok(self):
        self.assert_parses_as_type('int (*x)()',
                                   CFunc.typedef(returns=bd.int).ptr)

    def test_convertTypeFromCursor_onFuncPtrPtr_ok(self):
        self.assert_parses_as_type('int (**x)()',
                                   CFunc.typedef(returns=bd.int).ptr.ptr)

    def test_readFromCursor_onStaticVarDef_ignoresDef(self):
        self.assert_parses('static int varname;')

    def test_readFromCursor_onStructEmptyDef_ok(self):
        struct_def = CStruct.typedef('strctname')
        self.assert_parses('struct strctname {};',
                           exp_structs={'strctname': struct_def})

    def test_readFromCursor_onStructWithMembersDef_ok(self):
        struct_def = CStruct.typedef(
            'strctname', ('a', bd.int), ('b', bd.char), ('c', bd.char))
        self.assert_parses('struct strctname { int a; char b, c; };',
                           exp_structs={'strctname': struct_def})

    def test_readFromCursor_onAnonymousStructInTypeDef_ok(self):
        struct_def = CStruct.typedef(None, ('a', bd.int))
        self.assert_parses('typedef struct { int a; } typename;',
                           exp_typedefs={'typename': struct_def})

    def test_readFromCursor_onVarDefOfTypeStruct_ok(self):
        struct_def = CStruct.typedef('structname')
        self.assert_parses('struct strctname { };'
                           'extern struct strctname varname;',
                           exp_structs={'strctname': struct_def},
                           exp_vars={'varname': struct_def})

    def test_readFromCursor_onVarDefOfAnonymousStruct_ok(self):
        struct_def = CStruct.typedef(None, ('a', bd.int))
        self.assert_parses('extern struct { int a; } varname;',
                           exp_vars={'varname': struct_def})

    def test_readFromCursor_onMultipleAnonymousStructs_ok(self):
        struct1_def = CStruct.typedef(None, ('a', bd.int))
        struct2_def = CStruct.typedef(None, ('b', struct1_def))
        struct3_def = CStruct.typedef(None, ('c', bd.int))
        self.assert_parses('typedef struct { struct { int a; } b; } varname1;\n'
                           'typedef struct { int c; } varname2;\n',
                           exp_typedefs={'varname1': struct2_def,
                                         'varname2': struct3_def})

    def test_readFromCursor_onStructDefWithVarDef_ok(self):
        struct_def = CStruct.typedef('structname', ('a', bd.int))
        self.assert_parses('extern struct strctname { int a; } varname;',
                           exp_structs={'strctname': struct_def},
                           exp_vars={'varname': struct_def})

    def test_readFromCursor_onAnonymousStructDef_ok(self):
        struct_def = CStruct.typedef(None, ('a', bd.int))
        self.assert_parses('extern struct { int a; } varname;',
                           exp_vars={'varname': struct_def})

    def test_readFromCursor_onNestedStructDef_ok(self):
        inner_struct = CStruct.typedef('inner')
        outer_struct = CStruct.typedef(None, ('a', inner_struct))
        self.assert_parses('extern struct { struct inner {} a; } varname;',
                           exp_vars={'varname': outer_struct},
                           exp_structs={'inner': inner_struct})

    def test_readFromCursor_onForwardRefOnly_ok(self):
        struct_def = CStruct.typedef('strctname')
        self.assert_parses('struct strctname;',
                           exp_structs={'strctname': struct_def})

    def test_readFromCursor_onForwardRefDeclaredDelayed_ok(self):
        struct_def = CStruct.typedef('strctname')
        struct_def.delayed_def(('a', struct_def.ptr))
        self.assert_parses('struct strctname;'
                           'struct strctname { struct strctname * a; };',
                           exp_structs={'strctname': struct_def})

    def test_readFromCursor_onDelayedStructDefWithMemberTypeDefinedAfterFirstReference_ok(self):
        struct_def = CStruct.typedef('strctname', ('member', bd.int))
        self.assert_parses('struct strctname;\n'
                           'typedef int newtype;\n'
                           'struct strctname {\n'
                           '    newtype member;\n'
                           '} ;',
                           exp_structs={'strctname': struct_def},
                           exp_typedefs={'newtype': bd.int})

    def test_readFromCursor_onStructWithFlexibleArrayMember_addsArrayOfLen0(self):
        struct_def = CStruct.typedef('strctname',
                                     ('a', bd.int), ('b', bd.short[0]))
        self.assert_parses('struct strctname { int a; short b[]; };',
                           exp_structs={'strctname': struct_def})

    def test_readFromCursor_onPackingSet_ok(self):
        struct_def = CStruct.typedef('strctname')
        self.assert_parses('#pragma pack(1)\n'
                           'struct strctname { };',
                           exp_structs={'strctname': struct_def})

    def test_readFromCursor_onEnum_ok(self):
        self.assert_parses('extern enum enumname { a, b } varname;',
                           exp_structs={'enumname': CEnum},
                           exp_vars={'varname': CEnum})

    def test_readFromCursor_onEnumInTypeDef_ok(self):
        self.assert_parses('typedef enum enumname { a, b } typename;',
                           exp_structs={'enumname': CEnum},
                           exp_typedefs={'typename': CEnum})

    def test_readFromCursor_onAnonymousEnumInTypeDef_ok(self):
        self.assert_parses('typedef enum { a, b } typename;',
                           exp_typedefs={'typename': CEnum})

    def test_readFromCursor_onDefineCustomType_returnsTypedef(self):
        self.assert_parses('typedef int newtype;',
                           exp_typedefs={'newtype': bd.int})

    def test_readFromCursor_onApplyCustomType_returnsResolvedType(self):
        self.assert_parses('typedef int newtype;\n'
                           'extern newtype varname;',
                           exp_typedefs={'newtype': bd.int},
                           exp_vars={'varname': bd.int})

    def test_readFromCursor_onSimpleFuncProto_ok(self):
        self.assert_parses('void funcname();',
                           exp_funcs={'funcname': CFunc.typedef()})

    def test_readFromCursor_onFuncProtoArgsAndResult_ok(self):
        func_def = CFunc.typedef(bd.int, bd.char, returns=bd.int)
        self.assert_parses('int funcname(int, char a);',
                           exp_funcs={'funcname': func_def})

    def test_readFromCursor_onExternFunc_ok(self):
        self.assert_parses('extern void funcname();',
                           exp_funcs={'funcname': CFunc.typedef()})

    def test_readFromCursor_onDllImport_ignore(self):
        self.assert_parses('void __attribute__((dllimport)) funcname(void);')

    def test_readFromCursor_onStaticFunc_ignore(self):
        self.assert_parses('static void funcname();')

    def test_readFromCursor_onImplFunc_ok(self):
        self.assert_parses('void funcname() { return; }',
                           exp_funcs={'funcname': CFunc.typedef()},
                           exp_impls={'funcname'})

    def test_readFromCursor_onMacro_returnsSourceLocation(self):
        src = '#define MACRONAME               '
        macro_loc = ('test.c', src.find('MACRONAME'), len(src.rstrip()))
        self.assert_parses(src, exp_macro_locs={'MACRONAME': macro_loc})

    def test_readFromCursor_onMacroWithCommentsAndSpace_returnsOnlySpacesAndCommentsInMacro(self):
        src = (' // some commant\n'
               ' # define MACRONAME  /* IN MACROCOMMENT */ 2 /* comment */ //comment\n'
               ' // some commant')
        macro_loc = ('test.c', src.find('MACRONAME'), src.find('2')+1)
        self.assert_parses(src, exp_macro_locs={'MACRONAME': macro_loc})

    def test_readFromCursor_onMultipleMacros_returnsAllDefs(self):
        src = ('#define MACRONAME1\n'
               '#define MACRONAME2')
        self.assert_parses(src, exp_macro_locs={
            'MACRONAME1': ('test.c', src.rfind('MACRONAME1'), src.find('\n')),
            'MACRONAME2': ('test.c', src.rfind('MACRONAME2'), len(src))})

    def test_readFromCursor_onMultipleMacrosWithSameName_returnsOnlyLastDef(self):
        src = ('#define MACRONAME\n'
               '#define MACRONAME')
        macro_loc = ('test.c', src.rfind('MACRONAME'), len(src))
        self.assert_parses(src, exp_macro_locs={'MACRONAME': macro_loc})

    def test_readFromCursor_onParametrizedMacro_ok(self):
        src = ('#define MACRONAME(p1, p2) p1 + p2')
        macro_loc = ('test.c', src.rfind('MACRONAME'), len(src))
        self.assert_parses(src, exp_macro_locs={'MACRONAME': macro_loc})

    def test_read_onNotExistinFile_raisesFileNotFoundError(self):
        with pytest.raises(FileNotFoundError):
            parser = CParser()
            parser.read('not_existing_file.c')

    def test_read_onNotExistingFile_raisesFileNotFoundError(self):
        parser = CParser()
        with pytest.raises(FileNotFoundError):
            parser.read('invalid-file-name')

    @classmethod
    def parse(cls, content, patches=None, sys_include_dirs=None,
              **predef_macros):
        parser = CParser(predef_macros, sys_include_dirs)
        fileobj = NamedTemporaryFile(suffix='.c', delete=False, mode='w+t')
        try:
            fileobj.write(content)
            fileobj.close()
            parser.read(fileobj.name, patches)
        finally:
            os.remove(fileobj.name)
        return parser

    def test_read_onErrorInFile_raisesParseErrorWithErrors(self):
        try:
            parser = self.parse('#error My error text')
        except ParseError as exc:
            assert len(exc.errors) == 1
            assert 'My error text' in exc.errors[0][0]
            assert exc.errors[0][1].endswith('.c')  # check filename
            assert exc.errors[0][2] == 1  # check linenumber
        else:
            raise AssertionError('Expected ParseError')

    def test_read_onWarningInFile_ignore(self):
        parser = self.parse('var_decl_without_typespec;')

    def test_read_onValidFile_readsDefs(self):
        parser = self.parse('int v; typedef char t; void f(void);')
        assert parser.vars == {'v': bd.int}
        assert parser.typedefs['t'] == bd.char
        assert parser.funcs == {'f': CFunc.typedef()}

    def test_read_onMacro_returnsParsedMacro(self):
        parser = self.parse('\n\n#define MACRO 3')
        assert parser.macros['MACRO'] \
               == MacroDef('MACRO', compile('3', '<string>', 'eval'))

    def test_read_onIncludes_addsIncludeFileNamesToSourceFiles(self):
        with TemporaryDirectory() as temp_dir:
            c_filename = os.path.join(temp_dir, 'source.c')
            h1_filename = os.path.join(temp_dir, 'include_1.h')
            h2_filename = os.path.join(temp_dir, 'include_2.h')
            open(c_filename, 'wt').write('#include "include_1.h"')
            open(h1_filename, 'wt').write('#include "include_2.h"')
            open(h2_filename, 'wt').write('')
            parser = CParser()
            parser.read(c_filename)
            assert parser.source_files == {c_filename, h1_filename, h2_filename}

    def test_read_onAdditionalIncludeDirs_searchIncludeDirs(self):
        with TemporaryDirectory() as temp_dir:
            header_dir = os.path.join(temp_dir, 'subdir', 'dir with space')
            h_fname = os.path.join(header_dir, 'test.h')
            c_fname = os.path.join(temp_dir, 'test.c')
            os.makedirs(header_dir)
            open(h_fname, 'wt').write('int func(void);')
            open(c_fname, 'wt').write('#include "test.h"')
            parser = CParser(include_dirs=[header_dir])
            parser.read(c_fname)
            assert 'func' in parser.funcs
            assert 'func' not in parser.implementations

    def test_read_onSystemIncludeDirs_searchPassedSysIncludeDirsAndIgnoreFuncsAndSourceFiles(self):
        with TemporaryDirectory() as temp_dir:
            header_dir = os.path.join(temp_dir, 'subdir', 'dir with space')
            h_fname = os.path.join(header_dir, 'test.h')
            c_fname = os.path.join(temp_dir, 'test.c')
            os.makedirs(header_dir)
            open(h_fname, 'wt').write('int func(void);')
            open(c_fname, 'wt').write('#include <test.h>')
            parser = CParser(sys_include_dirs=[header_dir])
            parser.read(c_fname)
            assert 'func' not in parser.funcs
            assert h_fname not in parser.source_files

    def test_read_onAdditionalDefines_passesDefinesToParser(self):
        parser = self.parse('int PRE_DEF_MACRO;', PRE_DEF_MACRO='var')
        assert list(parser.vars) == ['var']

    def test_read_onPredefinedMacros_makeThemAvailableLikeUsualMacros(self):
        parser = self.parse('', MACRO='a')
        code_obj = compile("self.a", '<string>', 'eval')
        assert parser.macros['MACRO'] \
               == MacroDef('MACRO', code_obj)

    def test_read_onNonStrPredefinedMacro_implicitlyConvertToStr(self):
        parser = self.parse('', MACRO=1)
        code_obj = compile("1", '<string>', 'eval')
        assert parser.macros['MACRO'] \
               == MacroDef('MACRO', code_obj)

    @pytest.mark.parametrize('inline_keyword',
                             ['inline', 'forceinline', '__inline', '__forceinline'])
    def test_read_onInlineFunc_ignore(self, inline_keyword):
        parser = self.parse(inline_keyword + ' void funcname() { return; }')
        assert parser.funcs == {}

    def test_readFromCursor_onCDeclFunc_returnsFuncWithCDeclAttr(self):
        parser = self.parse('void __cdecl funcname();')
        assert parser.funcs == {'funcname': CFunc.typedef().with_attr('cdecl')}

    def test_read_withPatchedFile(self):
        fileobj = NamedTemporaryFile(suffix='.h', delete=False, mode='w+t')
        try:
            fileobj.write('#error original content')
            fileobj.close()
            parser = self.parse(f'#include "{fileobj.name}"\n',
                                patches={fileobj.name: b'#define MACRO'})
            assert 'MACRO' in parser.macros
        finally:
            os.remove(fileobj.name)

    def test_read_onRedefinedFunctionAsInline_deletesAlreadyRegisteredFunc(self):
        parser = self.parse('void funcname(void);\n'
                            '__inline void funcname(void) { return; }')
        assert parser.funcs == {}
