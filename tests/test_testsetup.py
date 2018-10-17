import contextlib
import sys
import os
from pathlib import Path
from unittest.mock import patch, Mock, MagicMock, call, ANY
import pytest

from .helpers import build_tree
from headlock.testsetup import TestSetup, MethodNotMockedError, \
    BuildError, CompileError, CModuleDecoratorBase, CModule, TransUnit
from headlock.c_data_model import CStructType, CEnumType, CIntType


@pytest.fixture
def TSDummy(tmpdir):
    saved_sys_path = sys.path[:]
    sys.path.append(str(tmpdir))
    tmpdir.join('testsetup_dummy.py').write(
        'class Container:\n'
        '    class TSDummy:\n'
        '        @classmethod\n'
        '        def __extend_by_transunit__(cls, transunit):\n'
        '            pass\n'
        '        @classmethod\n'
        '        def __extend_by_lib_search_params__(cls, req_libs,lib_dirs):\n'
        '            pass\n')
    from testsetup_dummy import Container
    sys.path = saved_sys_path
    yield Container.TSDummy
    del sys.modules['testsetup_dummy']


@contextlib.contextmanager
def sim_tsdummy_tree(base_dir, tree):
    """
    Simulate, that TSDummy is located in 'base_dir' and 'tree' is the file
    structure below this directory.
    """
    global __file__
    base_path = build_tree(base_dir, tree)
    saved_file = __file__
    __file__ = str(base_dir.join('test_testsetup.py'))
    try:
        yield base_path
    finally:
        __file__ = saved_file


class TestBuildError:

    def test_getStr_withMsgOnlyParam_returnsStrWithTestSetupClassName(self):
        exc = BuildError('error abc')
        assert str(exc) == 'error abc'

    def test_getStr_withTestSetupPassed_returnsStrWithTestSetupClassName(self):
        filepath = Path('c_files/empty.c')
        exc = BuildError('cannot do xyz', filepath)
        assert str(exc) == f'building {filepath} failed: cannot do xyz'


class TestCompileError:

    def test_getStr_returnsNumberOfErrors(self):
        exc = CompileError([('err 1', 'file1.c', 3),
                            ('err 2', 'file2.h', 3)],
                           Path('test.c'))
        assert str(exc) == 'building test.c failed: 2 compile errors'

    def test_iter_iteratesErrors(self):
        errlist = [('err 1', 'file1.c', 3), ('err 2', 'file2.h', 3)]
        exc = CompileError(errlist)
        assert list(exc) == errlist


class TestCModuleDecoratorBase:

    def test_call_onCls_returnsDerivedClassWithSameNameAndModule(self, TSDummy):
        c_mod_decorator = CModuleDecoratorBase()
        TSDecorated = c_mod_decorator(TSDummy)
        assert issubclass(TSDecorated, TSDummy) \
               and TSDecorated is not TSDummy
        assert TSDecorated.__name__ == 'TSDummy'
        assert TSDecorated.__qualname__ == 'Container.TSDummy'
        assert TSDecorated.__module__ == 'testsetup_dummy'

    def test_call_onCls_createsDerivedCls(self, TSDummy):
        deco = CModuleDecoratorBase()
        TSDerived = deco(TSDummy)
        assert issubclass(TSDerived, TSDummy)

    def test_call_onCls_callsExtendByTransUnit(self, TSDummy):
        with patch.object(TSDummy, '__extend_by_transunit__'):
            deco = CModuleDecoratorBase()
            tu1, tu2 = Mock(), Mock()
            deco.iter_transunits = Mock(return_value=iter([tu1, tu2]))
            deco(TSDummy)
            assert TSDummy.__extend_by_transunit__.call_args_list \
                   == [call(tu1), call(tu2)]

    def test_call_onCls_extendsLibrSearchParams(self, TSDummy):
        with patch.object(TSDummy, '__extend_by_lib_search_params__'):
            deco = CModuleDecoratorBase()
            deco.iter_transunits = MagicMock()
            deco.get_lib_search_params = Mock(return_value=([Path('dir')],
                                                            ['lib']))
            deco(TSDummy)
            TSDummy.__extend_by_lib_search_params__.assert_called_once_with(
                [Path('dir')], ['lib'])


class TestCModule:

    def test_iterTransunits_onRelSrcFilename_resolves(self, tmpdir):
        with sim_tsdummy_tree(tmpdir, {'dir': {'src': b''}}) as base_dir:
            c_mod = CModule('dir/src')
            [transunit] = c_mod.iter_transunits(TSDummy)
            assert transunit.abs_src_filename == base_dir / 'dir/src'

    def test_iterTransunits_onAbsSrcFilename_resolves(self, tmpdir):
        base_dir = build_tree(tmpdir, {'dir': {'src': b''}})
        abs_path = str(base_dir /  'dir/src')
        c_mod = CModule(abs_path)
        [transunit] = c_mod.iter_transunits(TSDummy)
        assert transunit.abs_src_filename == Path(abs_path)

    class TSSubClass:
        pass

    def test_iterTransunits_setsSubsysName(self, tmpdir):
        with sim_tsdummy_tree(tmpdir, {'t1.c': b'', 't2.c': b''}):
            c_mod = CModule('t1.c', 't2.c')
            [transunit, *_] = c_mod.iter_transunits(self.TSSubClass)
            assert transunit.subsys_name == 't1'

    def test_iterTransunits_retrievesAndResolvesIncludeDirs(self, tmpdir):
        with sim_tsdummy_tree(tmpdir, {'src': b'', 'd1': {}, 'd2': {}}) \
                as base_dir:
            c_mod = CModule('src', include_dirs=['d1', 'd2'])
            [transunit] = c_mod.iter_transunits(TSDummy)
            assert transunit.abs_incl_dirs == [base_dir / 'd1', base_dir / 'd2']

    def test_iterTransunits_createsOneUnitTestPerSrcFilename(self, tmpdir):
        with sim_tsdummy_tree(tmpdir, {'t1.c': b'', 't2.c': b''}) as base_dir:
            c_mod = CModule('t1.c', 't2.c')
            assert [tu.abs_src_filename
                    for tu in c_mod.iter_transunits(TSDummy)] \
                    == [base_dir / 't1.c', base_dir / 't2.c']

    def test_iterTransunits_onPredefMacros_passesMacrosToCompParams(self, tmpdir):
        with sim_tsdummy_tree(tmpdir, {'src': b''}):
            c_mod = CModule('src', MACRO1=11, MACRO2=22)
            [transunit] = c_mod.iter_transunits(TSDummy)
            assert transunit.predef_macros == {'MACRO1':11, 'MACRO2':22}

    def test_iterTransunits_onInvalidPath_raiseIOError(self):
        c_mod = CModule('test_invalid.c')
        with pytest.raises(IOError):
            list(c_mod.iter_transunits(TSDummy))

    def test_getLibSearchParams_retrievesAndResolvesLibsDirs(self, tmpdir, TSDummy):
        with sim_tsdummy_tree(tmpdir, {'src':b'', 'd1':{}, 'd2':{}}) \
                as base_dir:
            c_mod = CModule('src', library_dirs=['d1', 'd2'])
            [_, lib_dirs] = c_mod.get_lib_search_params(TSDummy)
            assert lib_dirs == [base_dir / 'd1', base_dir / 'd2']

    def test_iterTransunits_retrievesRequiredLibs(self, tmpdir, TSDummy):
        with sim_tsdummy_tree(tmpdir, {'src': b''}) as base_dir:
            c_mod = CModule('src', required_libs=['lib1', 'lib2'])
            [req_libs, _] = c_mod.get_lib_search_params(TSDummy)
            assert req_libs == ['lib1', 'lib2']

    def test_resolvePath_onRelativeFileAndRelativeModulePath_returnsAbsolutePath(self, TSDummy, tmpdir):
        module = sys.modules[TSDummy.__module__]
        with build_tree(tmpdir, {'file.py': b'', 'file.c': b''}) as dir:
            os.chdir(dir)
            with patch.object(module, '__file__', 'file.py'):
                assert CModule.resolve_path('file.c', TSDummy) == dir / 'file.c'


class TestTestSetup(object):

    def extend_by_ccode(self, cls, src, filename, **macros):
        sourcefile = (Path(__file__).parent / 'c_files' / filename).absolute()
        sourcefile.write_bytes(src)
        transunit = TransUnit('test_tu', sourcefile, [], macros)
        cls.__extend_by_transunit__(transunit)

    def cls_from_ccode(self, src, filename, **macros):
        class TSDummy(TestSetup): pass
        self.extend_by_ccode(TSDummy, src, filename, **macros)
        return TSDummy

    @pytest.fixture
    def ts_dummy(self):
        TSDummy = self.cls_from_ccode(b'', 'test.c')
        return TSDummy

    def test_extendByTransunit_addsModulesToGetCModules(self):
        class TSDummy(TestSetup):
            __parser_factory__ = MagicMock()
        transunits = [MagicMock(), MagicMock()]
        TSDummy.__extend_by_transunit__(transunits[0])
        TSDummy.__extend_by_transunit__(transunits[1])
        assert TSDummy.__transunits__ == frozenset(transunits)

    def test_extendByTransunit_doesNotModifyParentCls(self):
        transunits = [MagicMock(), MagicMock()]
        class TSParent(TestSetup):
            __parser_factory__ = MagicMock()
        TSParent.__extend_by_transunit__(transunits[0])
        class TSChild(TSParent):
            pass
        TSChild.__extend_by_transunit__(transunits[1])
        assert list(TSParent.__transunits__) == transunits[:1]
        assert TSChild.__transunits__ == set(transunits[:2])

    def test_extendByTransunit_onInvalidSourceCode_raisesCompileErrorDuringParsing(self):
        with pytest.raises(CompileError) as comp_err:
            self.cls_from_ccode(b'#error invalid c src', 'compile_err.c')
        assert len(comp_err.value.errors) == 1
        assert comp_err.value.path.name == 'compile_err.c'

    def test_getTsAbspath_returnsAbsPathOfFile(self):
        TSDummy = self.cls_from_ccode(b'', 'test.c')
        assert TSDummy.get_ts_abspath() == Path(__file__).resolve()

    def test_getSrcDir_returnsAbsDirOfFile(self):
        TSDummy = self.cls_from_ccode(b'', 'test.c')
        assert TSDummy.get_src_dir() == Path(__file__).resolve().parent

    class TSEmpty(TestSetup):
        __transunits__ = frozenset([
            TransUnit('empty', Path(__file__, 'c_files/empty.c'), [], {})])

    def test_getTsName_onStaticTSCls_returnsReversedQualifiedClassName(self):
        assert self.TSEmpty.get_ts_name() == 'TSEmpty.TestTestSetup'

    def test_getTsName_onDynamicGeneratedTSCls_returnsReversedQualifiedClassNameAndUid(self):
        TSDummy = self.cls_from_ccode(b'', 'test.c')
        assert TSDummy.get_ts_name()[:-8] \
               == 'TSDummy.cls_from_ccode.TestTestSetup_'
        int(str(TSDummy.get_ts_name())[-8:], 16)  # expect hexnumber at the end

    def test_getTsName_onDynamicGeneratedTSClsWithSameParams_returnsSameStr(self):
        TSDummy1 = self.cls_from_ccode(b'', 'test.c', MACRO=1)
        TSDummy2 = self.cls_from_ccode(b'', 'test.c', MACRO=1)
        assert TSDummy1.get_ts_name() == TSDummy2.get_ts_name()

    def test_getTsName_onDynamicGeneratedTSClsWithDifferentParams_returnsDifferentStr(self):
        TSDummy1 = self.cls_from_ccode(b'', 'test.c', A=1, B=222, C=3)
        TSDummy2 = self.cls_from_ccode(b'', 'test.c', A=1, B=2, C=3)
        assert TSDummy1.get_ts_name() != TSDummy2.get_ts_name()

    def test_getBuildDir_returnsCorrectPath(self, ts_dummy):
        this_file = Path(__file__).resolve()
        assert ts_dummy.get_build_dir() \
               == this_file.parent / TestSetup._BUILD_DIR_ / this_file.stem \
                  / ts_dummy.get_ts_name()

    def test_macroWrapper_ok(self):
        TS = self.cls_from_ccode(b'#define MACRONAME   123', 'macro.c')
        assert TS.MACRONAME == 123

    def test_macroWrapper_onNotConvertableMacros_raisesValueError(self):
        cls = self.cls_from_ccode(b'#define MACRONAME   (int[]) 3',
                                  'invalid_macro.c')
        ts = cls()
        with pytest.raises(ValueError):
            _ = ts.MACRONAME

    def test_create_onPredefinedMacro_providesMacroAsMember(self):
        TSMock = self.cls_from_ccode(b'', 'create_predef.c',
                                     A=None, B=1, C='')
        with TSMock() as ts:
            assert ts.A is None
            assert ts.B == 1
            assert ts.C is None

    def test_init_onValidSource_ok(self):
        TS = self.cls_from_ccode(b'/* valid C source code */', 'comment_only.c')
        ts = TS()
        ts.__unload__()

    @patch('headlock.testsetup.TestSetup.__unload__')
    @patch('headlock.testsetup.TestSetup.__load__')
    @patch('headlock.testsetup.TestSetup.__build__')
    def test_init_callsBuild(self, __build__, __load__, __unload__):
        TS = self.cls_from_ccode(b'', 'init_does_build.c')
        ts = TS()
        __build__.assert_called()

    @patch('headlock.testsetup.TestSetup.__load__')
    @patch('headlock.testsetup.TestSetup.__unload__')
    def test_init_callsLoad(self, __unload__, __load__):
        TS = self.cls_from_ccode(b'', 'init_calls_load.c')
        ts = TS()
        __load__.assert_called_once()

    @patch('headlock.testsetup.TestSetup.__startup__')
    def test_init_doesNotCallStartup(self, __startup__):
        TS = self.cls_from_ccode(b'', 'init_on_nostartup.c')
        ts = TS()
        __startup__.assert_not_called()
        ts.__unload__()

    def test_build_onPredefinedMacros_passesMacrosToCompiler(self):
        TSMock = self.cls_from_ccode(b'int a = A;\n'
                                     b'int b = B 22;\n'
                                     b'#if defined(C)\n'
                                     b'int c = 33;\n'
                                     b'#endif',
                                     'build_predef.c',
                                     A=11, B='', C=None)
        with TSMock() as ts:
            assert ts.a.val == 11
            assert ts.b.val == 22
            assert ts.c.val == 33

    def test_build_onExtendByLibsSearchParams_passesMergedLibsAndSearchDirectories(self):
        class TSChkLibDirs(TestSetup):
            __TOOLCHAIN__ = Mock()
            __load__ = __unload__ = Mock()
        TSChkLibDirs.__extend_by_lib_search_params__(['lib1'], [Path('dir1')], )
        TSChkLibDirs.__extend_by_lib_search_params__(['lib2'], [Path('dir2')])
        ts = TSChkLibDirs()
        TSChkLibDirs.__TOOLCHAIN__.build.assert_called_once_with(
            ANY, ANY, ANY, ['lib1', 'lib2'], [Path('dir1'), Path('dir2')])

    def test_build_onExtendByLibsSearchParams_doesNotModifyParentCls(self):
        class TSChkLibDirs(TestSetup):
            __TOOLCHAIN__ = Mock()
            __load__ = __unload__ = Mock()
        class TSChkLibDirsChild(TSChkLibDirs):
            pass
        TSChkLibDirsChild.__extend_by_lib_search_params__(['l'], [Path('d')])
        TSChkLibDirs()
        TSChkLibDirs.__TOOLCHAIN__.build.assert_called_once_with(
            ANY, ANY, ANY, [], [])

    @patch('headlock.testsetup.TestSetup.__shutdown__')
    def test_unload_onStarted_callsShutdown(self, __shutdown__):
        TS = self.cls_from_ccode(b'int var;', 'unload_calls_shutdown.c')
        ts = TS()
        ts.__startup__()
        ts.__unload__()
        ts.__shutdown__.assert_called_once()

    @patch('headlock.testsetup.TestSetup.__shutdown__')
    def test_unload_onNotStarted_doesNotCallsShutdown(self, __shutdown__):
        TS = self.cls_from_ccode(b'int var;', 'unload_calls_shutdown.c')
        ts = TS()
        ts.__unload__()
        ts.__shutdown__.assert_not_called()

    def test_unload_calledTwice_ignoresSecondCall(self):
        TS = self.cls_from_ccode(b'', 'unload_run_twice.c')
        ts = TS()
        ts.__unload__()
        ts.__shutdown__ = Mock()
        ts.__unload__()
        ts.__shutdown__.assert_not_called()

    @patch('headlock.testsetup.TestSetup.__load__')
    @patch('headlock.testsetup.TestSetup.__unload__')
    def test_del_doesImplicitShutdown(self, __unload__, __load__):
        TS = self.cls_from_ccode(b'', 'unload_run_twice.c')
        ts = TS()
        __unload__.assert_not_called()
        del ts
        __unload__.assert_called()

    @patch('headlock.testsetup.TestSetup.__load__')
    @patch('headlock.testsetup.TestSetup.__unload__', side_effect=KeyError)
    def test_del_onErrorDuringUnload_ignore(self, __unload__, __load__):
        TS = self.cls_from_ccode(b'', 'unload_with_error_during_del.c')
        ts = TS()
        del ts

    def test_enter_onNotStarted_callsStartup(self):
        TSMock = self.cls_from_ccode(b'', 'contextmgr_on_enter.c')
        ts = TSMock()
        with patch.object(ts, '__startup__') as startup:
            ts.__enter__()
            startup.assert_called_once()
        ts.__unload__()

    def test_enter_onAlreadyStarted_doesNotCallStartup(self):
        TSMock = self.cls_from_ccode(b'', 'contextmgr_enter_on_started.c')
        ts = TSMock()
        ts.__startup__()
        with patch.object(ts, '__startup__') as startup:
            ts.__enter__()
            startup.assert_not_called()
        ts.__unload__()

    def test_exit_callsUnload(self):
        TSMock = self.cls_from_ccode(b'', 'contextmgr_on_exit.c')
        ts = TSMock()
        ts.__enter__()
        with patch.object(ts, '__unload__', wraps=ts.__unload__):
            ts.__exit__(None, None, None)
            ts.__unload__.assert_called_once()

    def test_funcWrapper_ok(self):
        TSMock = self.cls_from_ccode(b'int func(int a, int b) { return a+b; }',
                                     'func.c')
        with TSMock() as ts:
            assert ts.func(11, 22) == 33

    def test_varWrapper_ok(self):
        TSMock = self.cls_from_ccode(b'int var = 11;', 'var.c')
        with TSMock() as ts:
            assert ts.var.val == 11
            ts.var.val = 22
            assert ts.var.val == 22

    def test_mockVarWrapper_ok(self):
        TSMock = self.cls_from_ccode(b'extern int var;', 'mocked_var.c')
        with TSMock() as ts:
            assert ts.var.val == 0
            ts.var.val = 11
            assert ts.var.val == 11

    def test_headerFileOnly_createsMockOnly(self):
        TSMock = self.cls_from_ccode(b'int func();', 'header.h')
        with TSMock() as ts:
            ts.func_mock = Mock(return_value=123)
            assert ts.func() == 123

    def test_mockFuncWrapper_ok(self):
        class TSMock(TestSetup):
            func_mock = Mock(return_value=33)
        self.extend_by_ccode(TSMock, b'int func(int * a, int * b);', 'mocked.c')
        with TSMock() as ts:
            assert ts.func(11, 22) == 33
            TSMock.func_mock.assert_called_with(ts.int.ptr(11), ts.int.ptr(22))

    def test_mockFuncWrapper_onNotExistingMockFunc_forwardsToMockFallbackFunc(self):
        class TSMock(TestSetup):
            mock_fallback = Mock(return_value=33)
        self.extend_by_ccode(TSMock, b'int func(int * a, int * b);',
                             'mocked_func_fallback.c')
        with TSMock() as ts:
            assert ts.func(11, 22) == 33
            TSMock.mock_fallback.assert_called_with('func', ts.int.ptr(11),
                                                    ts.int.ptr(22))

    def test_mockFuncWrapper_createsCWrapperCode(self):
        class TSMock(TestSetup):
            mocked_func_mock = Mock(return_value=22)
        self.extend_by_ccode(TSMock, b'int mocked_func(int p);'
                                     b'int func(int p) { '
                                     b'   return mocked_func(p); }',
                             'mocked_func_cwrapper.c')
        with TSMock() as ts:
            assert ts.func(11) == 22
            TSMock.mocked_func_mock.assert_called_once_with(11)

    def test_mockFuncWrapper_onUnmockedFunc_raisesMethodNotMockedError(self):
        TSMock = self.cls_from_ccode(b'void unmocked_func();',
                                     'mocked_func_error.c')
        with TSMock() as ts:
            with pytest.raises(MethodNotMockedError) as excinfo:
                assert ts.mock_fallback('unmocked_func', 11, 22)
            assert "unmocked_func" in str(excinfo.value)

    def test_mockFuncWrapper_onRefersToPrevTransUnit_isGenerated(self):
        TSMock = self.cls_from_ccode(b'void callee(void) { return; }',
                                     'prev.c')
        self.extend_by_ccode(TSMock, b'void callee(void); '
                                     b'void caller(void) { callee(); }',
                             'refprev.c')
        TSMock()

    def test_mockFuncWrapper_onRefersToNextTransUnit_isGenerated(self):
        TSMock = self.cls_from_ccode(b'void callee(void);'
                                     b'void caller(void) { callee(); }',
                                     'refnext.c')
        self.extend_by_ccode(TSMock, b'void callee(void) { return; }',
                             'next.c')
        TSMock()

    def test_mockFunc_onLastTransUnitDoesNotReferToMocks_isGenerated(self):
        TSMock = self.cls_from_ccode(b'void mock(void);'
                                     b'void func1(void) { mock(); }',
                                     'first_with_mock.c')
        self.extend_by_ccode(TSMock, b'void func2(void) { return; }',
                             'last_with_no_refererence_to_mock.c')
        TSMock()

    def test_typedefWrapper_storesTypeDefInTypedefCls(self):
        TSMock = self.cls_from_ccode(b'typedef int td_t;', 'typedef.c')
        with TSMock() as ts:
            assert ts.td_t == ts.int

    def test_structWrapper_storesStructDefInStructCls(self):
        TSMock = self.cls_from_ccode(b'struct strct_t { };', 'struct.c')
        with TSMock() as ts:
            assert isinstance(ts.struct.strct_t, CStructType)

    def test_structWrapper_onContainedStruct_ensuresContainedStructDeclaredFirst(self):
        TSMock = self.cls_from_ccode(
            b'struct s2_t { '
            b'     struct s1_t { int m; } s1; '
            b'     struct s3_t { int m; } s3;'
            b'} ;'
            b'void f(struct s2_t);',
            'inorder_defined_structs.c')
        with TSMock(): pass

    def test_structWrapper_onContainedStructPtr_ensuresNonPtrMembersDeclaredFirst(self):
        TSMock = self.cls_from_ccode(
            b'struct outer_t;'
            b'struct inner_t { '
            b'     struct outer_t * outer_ptr;'
            b'} inner_t; '
            b'struct outer_t { '
            b'     struct inner_t inner;'
            b'} outer;'
            b'void f(struct inner_t);',
            'inorder_ptr_structs.c')
        with TSMock(): pass

    def test_structWrapper_onGlobalVarFromStruct_ok(self):
        TSMock = self.cls_from_ccode(b'struct strct { int a; };\n'
                                     b'struct strct var;',
                                     'global_var_from_structs.c')
        with TSMock() as ts:
            assert ts.var.cobj_type == ts.struct.strct

    def test_structWrapper_onVarFromAnonymousStruct_ok(self):
        TSMock = self.cls_from_ccode(b'struct { int a; } var;',
                                     'anonymous_structs_var.c')
        with TSMock() as ts:
            assert [ts.var.cobj_type] == list(ts.struct.__dict__.values())

    def test_structWrapper_onTypedefFromAnonymousStruct_renamesStructToMakeItUsableAsParameter(self):
        TSMock = self.cls_from_ccode(b'typedef struct { int a; } t;\n'
                                     b'void func(t * a);',
                                     'anonymous_structs_typedef.c')
        with TSMock() as ts:
            anon_cstruct_type = getattr(ts.struct, '__anonymousfromtypedef__t')
            assert not anon_cstruct_type.is_anonymous_struct()

    def test_enumWrapper_storesEnumDefInEnumCls(self):
        TSMock = self.cls_from_ccode(b'enum enum_t { a };', 'enum.c')
        with TSMock() as ts:
            assert isinstance(ts.enum.enum_t, CEnumType)

    def test_onTestSetupComposedOfDifferentCModules_parseAndCompileCModulesIndependently(self):
        class TSDummy(TestSetup): pass
        self.extend_by_ccode(TSDummy, b'#if defined(A)\n'
                                      b'#error A not allowed\n'
                                      b'#endif\n'
                                      b'extern int a;'
                                      b'int b = B;',
                             'diff_params_mod_b.c',
                             B=2)
        self.extend_by_ccode(TSDummy, b'#if defined(B)\n'
                                      b'#error B not allowed\n'
                                      b'#endif\n'
                                      b'int a = A;'
                                      b'extern int b;',
                             'diff_params_mod_a.c',
                             A=1)
        with TSDummy() as ts:
            assert ts.a.val == 1
            assert ts.b.val == 2

    def test_onSameStructWithAnonymousChildInDifferentModules_generateCorrectMockWrapper(self):
        class TSDummy(TestSetup): pass
        self.extend_by_ccode(TSDummy, b'struct s { struct { int mm; } m; };\n'
                                      b'int func1(struct s p);\n',
                             'anonymstruct_mod1.c')
        self.extend_by_ccode(TSDummy, b'struct s { struct { int mm; } m; };\n'
                                      b'int func2(struct s p);\n',
                             'anonymstruct_mod2.c')
        with TSDummy() as ts:
            pass

    def test_onPointerToArrayOfStruct_generatesCorrectMockWrapper(self):
        class TSDummy(TestSetup): pass
        self.extend_by_ccode(TSDummy, b'typedef struct strct {} (*type)[1];\n'
                                      b'void func(type param);',
                             'ptr_to_arr_of_strct.c')
        with TSDummy() as ts:
            pass

    def test_registerUnloadEvent_onRegisteredEvent_isCalledOnUnload(self):
        TSDummy = self.cls_from_ccode(b'', 'test_register_unload_ev.c')
        ts = TSDummy()
        on_unload = Mock()
        ts.register_unload_event(on_unload)
        ts.__shutdown__()
        on_unload.assert_not_called()
        ts.__unload__()
        on_unload.assert_called_once()

    def test_registerUnloadEvent_onParams_arePassedWhenUnloaded(self):
        TSDummy = self.cls_from_ccode(b'', 'test2.c')
        with TSDummy() as ts:
            on_unload = Mock()
            ts.register_unload_event(on_unload, "PARAM1", 2)
        on_unload.assert_called_with('PARAM1', 2)

    def test_registerUnloadEvent_onMultipleEvents_areCalledInReversedOrder(self):
        TSDummy = self.cls_from_ccode(b'', 'test3.c')
        with TSDummy() as ts:
            on_unload = Mock()
            ts.register_unload_event(on_unload, 1)
            ts.register_unload_event(on_unload, 2)
            ts.register_unload_event(on_unload, 3)
        assert on_unload.call_args_list == [call(3), call(2), call(1)]

    def test_attributeAnnotationSupport_onStdIntIncluded_ok(self):
        TSDummy = self.cls_from_ccode(b'#include <stdint.h>\n'
                                      b'int __cdecl cdecl_func(void);',
                                      'attr_annotation_support.c')
        with TSDummy() as ts:
            assert '__cdecl' in ts.cdecl_func.cobj_type.c_attributes

    def test_subclassing_addsAttributesToDerivedClassButDoesNotModifyParentClass(self):
        TSDummy = self.cls_from_ccode(b'int func(void);\n'
                                      b'int var;\n'
                                      b'struct strct {};\n'
                                      b'typedef int typedf;',
                                      'parentcls.c')
        class TSDummy2(TSDummy): pass
        self.extend_by_ccode(TSDummy2, b'int func2(void);\n'
                                       b'int var2;\n'
                                       b'struct strct2 {};\n'
                                       b'typedef int typedf2;',
                             'derivedcls.c')
        with TSDummy() as ts:
            assert all(hasattr(ts, attr) for attr in ('func', 'var', 'typedf'))
            assert not any(hasattr(ts, attr)
                           for attr in ('func2', 'var2', 'typedf2'))
            assert hasattr(ts.struct, 'strct')
            assert not hasattr(ts.struct, 'strct2')
        with TSDummy2() as ts:
            assert all(hasattr(ts, attr)
                       for attr in ('func', 'var', 'typedf',
                                    'func2', 'var2', 'typedf2'))
            assert hasattr(ts.struct, 'strct')
            assert hasattr(ts.struct, 'strct2')

    def test_subclassing_onChildClsImplementsMockedMethodFromParentCls_ok(self):
        TSDummy = self.cls_from_ccode(b'int impl_by_subclass_func(void);\n'
                                      b'int not_impl_func(void);',
                                      'mocked_parentcls.c')
        class TSDummy2(TSDummy): pass
        self.extend_by_ccode(TSDummy2,
                             b'int impl_by_subclass_func(void) { return 2; }',
                             'impl_derivedcls.c')
        with TSDummy() as ts:
            with pytest.raises(MethodNotMockedError):
                ts.impl_by_subclass_func()
        with TSDummy2() as ts:
            assert ts.impl_by_subclass_func() == 2
            with pytest.raises(MethodNotMockedError):
                ts.not_impl_func()

    def test_subclassing_onMultipleInheritance_mergesBaseClsItems(self):
        TSParent1 = self.cls_from_ccode(b'void func1(void) { return; }\n'
                                        b'void mock1(void);\n'
                                        b'struct strct1 {};\n'
                                        b'enum enm1 { a };\n'
                                        b'int var1;\n'
                                        b'#define MACRO1\n',
                                        'base1.c')
        TSParent2 = self.cls_from_ccode(b'void func2(void) { return; }\n'
                                        b'void mock2(void);\n'
                                        b'struct strct2 {};\n'
                                        b'enum enm2 { a };\n'
                                        b'int var2;\n'
                                        b'#define MACRO2\n',
                                        'base2.c')
        class TSMerged(TSParent1, TSParent2):
            pass
        with TSMerged() as ts:
            assert hasattr(ts, 'func1') and hasattr(ts, 'func2')
            assert hasattr(ts, 'mock1') and hasattr(ts, 'mock2')
            assert hasattr(ts, 'var1') and hasattr(ts, 'var2')
            assert hasattr(ts, 'MACRO1') and hasattr(ts, 'MACRO2')
            assert hasattr(ts.struct, 'strct1') and hasattr(ts.struct, 'strct2')
            assert hasattr(ts.enum, 'enm1') and hasattr(ts.enum, 'enm2')
