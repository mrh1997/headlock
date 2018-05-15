import pytest
from headlock.testsetup import TestSetup, MethodNotMockedError, \
    BuildError, CompileError, CModuleDecoratorBase, CModule
import os
import subprocess
from unittest.mock import patch, Mock
import tempfile
from headlock.c_data_model import CStruct, CEnum, CInt
from pathlib import Path


class TSDummy(TestSetup): pass


class TestBuildError:

    def test_getStr_withMsgOnlyParam_returnsStrWithTestSetupClassName(self):
        exc = BuildError('error abc')
        assert str(exc) == 'error abc'

    def test_getStr_withTestSetupPassed_returnsStrWithTestSetupClassName(self):
        exc = BuildError('cannot do xyz', TSDummy)
        assert str(exc) == 'building TSDummy failed: cannot do xyz'


class TestCompileError:

    def test_getStr_returnsNumberOfErrors(self):
        exc = CompileError([('err 1', 'file1.c', 3),
                            ('err 2', 'file2.h', 3)],
                           TSDummy)
        assert str(exc) == 'building TSDummy failed: 2 compile errors'

    def test_iter_iteratesErrors(self):
        errlist = [('err 1', 'file1.c', 3), ('err 2', 'file2.h', 3)]
        exc = CompileError(errlist)
        assert list(exc) == errlist


class TestCModuleDecoratorBase:

    class TSDummy:
        @classmethod
        def _init_subclass_impl_(cls): pass
        @classmethod
        def __get_c_modules__(cls): return iter([])

    @patch.object(CModuleDecoratorBase, 'iter_compile_params')
    def test_call_onCls_returnsDerivedClassWithSameNameAndModule(self, iter_comp_param):
        c_mod_decorator = CModuleDecoratorBase()
        TSDecorated = c_mod_decorator(self.TSDummy)
        assert issubclass(TSDecorated, self.TSDummy) \
               and TSDecorated is not self.TSDummy
        assert TSDecorated.__name__ == 'TSDummy'
        assert TSDecorated.__qualname__ == 'TestCModuleDecoratorBase.TSDummy'
        assert TSDecorated.__module__ == self.TSDummy.__module__

    @patch.object(CModuleDecoratorBase, 'iter_compile_params',
                  side_effect=[[111], [222, 333]])
    def test_call_onMultipleDecorations_makeGetCModuleReturnMultipleCModCompileParams(self, iter_comp_param):
        deco1 = CModuleDecoratorBase()
        deco2 = CModuleDecoratorBase()
        TSDecorated = deco1(deco2(self.TSDummy))
        assert set(TSDecorated.__get_c_modules__()) == {111, 222, 333}


class TestCModule:

    class TSDummy: pass

    @patch.object(CModule, 'resolve_path', return_value=Path('/absdir'))
    def test_iterCompileParams_resolvesSrcFilename(self, res_path):
        c_mod = CModule('test.c')
        [comp_param] = c_mod.iter_compile_params(self.TSDummy)
        assert comp_param.abs_src_filename == res_path.return_value
        res_path.assert_called_with(Path('test.c'), self.TSDummy)

    @patch.object(CModule, 'resolve_path')
    def test_iterCompileParams_setsSubsysName(self, res_path):
        c_mod = CModule('test1.c', 'test2.c', 'test3.c')
        [comp_param, *_] = c_mod.iter_compile_params(self.TSDummy)
        assert comp_param.subsys_name \
               == 'test1.TSDummy.TestCModule.test_testsetup'

    @patch.object(CModule, 'resolve_path', return_value=Path('/absdir'))
    @patch.object(CModule, 'get_incl_dirs',return_value=[Path('d1'),Path('d2')])
    def test_iterCompileParams_retrievesAndResolvesIncludeDirs(self, get_incl_patch, reslv_patch):
        c_mod = CModule('test.c')
        [comp_param] = c_mod.iter_compile_params(self.TSDummy)
        assert comp_param.abs_incl_dirs == [reslv_patch.return_value] * 2
        reslv_patch.assert_any_call(Path('d1'), self.TSDummy)
        reslv_patch.assert_any_call(Path('d2'), self.TSDummy)

    @patch.object(CModule, 'resolve_path')
    def test_iterCompileParams_createsOneCompileParamPerSrcFilename(self, reslv_patch):
        c_mod = CModule('test1.c', 'test2.c')
        assert len(list(c_mod.iter_compile_params(self.TSDummy))) == 2
        reslv_patch.assert_any_call(Path('test1.c'), self.TSDummy)
        reslv_patch.assert_any_call(Path('test2.c'), self.TSDummy)

    @patch.object(CModule, 'resolve_path')
    def test_iterCompileParams_onPredefMacros_passesMacrosToCompParams(self, reslv_patch):
        c_mod = CModule('test.c', MACRO1=11, MACRO2=22)
        [comp_param] = c_mod.iter_compile_params(self.TSDummy)
        assert comp_param.predef_macros == {'MACRO1':11, 'MACRO2':22}
    
    def test_resolvePath_onAbsPath_returnsPathAsIs(self, tmpdir):
        c_mod = CModule()
        assert c_mod.resolve_path(Path(tmpdir), self.TSDummy) \
               == Path(tmpdir)

    def test_resolvePath_onRelPath_returnsModPathJoinedWithPath(self):
        c_mod = CModule(Path('c_files/empty.c'))
        assert c_mod.resolve_path(Path('c_files/empty.c'), self.TSDummy) \
               == Path(__file__).parent / 'c_files' / 'empty.c'


def cmod_from_ccode(src, filename, **macros):
    sourcefile = Path(__file__).parent / 'c_files' / filename
    sourcefile.write_bytes(src)
    return CModule(sourcefile, **macros)


class TestTestSetup(object):

    def cls_from_c_str(self, src, filename, **macros):
        @cmod_from_ccode(src, filename, **macros)
        class TSDummy(TestSetup): pass
        return TSDummy

    @CModule('c_files/empty.c')
    class TSEmpty(TestSetup):
        @classmethod
        def _init_subclass_impl_(cls):
            """
            This is a dummy, that requires no compiling.
            By avoiding compiling any bugs in build step will not result in
            fail collecting all tests.
            """

    @pytest.fixture
    def ts_dummy(self):
        TSDummy = self.cls_from_c_str(b'', 'test.c')
        return TSDummy

    @pytest.mark.skip
    def test_cMixin_onValidSource_ok(self):
        self.c_mixin_from(b'/* valid C source code */', 'comment.c')

    @pytest.mark.skip
    @pytest.mark.parametrize('exp_exc',
                             [subprocess.CalledProcessError(1, 'x'),
                              FileNotFoundError()])
    def test_cMixin_onFailedCallCMake_raisesBuildErrorDuringInstanciation(self, exp_exc):
        cls = self.c_mixin_from(b'', 'cmake_err.c')
        with patch('subprocess.Popen', Mock(side_effect=exp_exc)):
            with pytest.raises(BuildError):
                cls()

    @pytest.mark.skip
    def test_cMixin_onInvalidSourceCode_raisesCompileErrorDuringInstanciation(self):
        cls = self.c_mixin_from(b'#error p', 'compile_err_mixin.c')
        try:
            cls()
        except CompileError as exc:
            assert exc.testsetup == cls
            assert len(exc.errors) == 1
        else:
            raise AssertionError('Expected to raise CompileError')

    @pytest.mark.skip
    def test_cMixin_onNotDelayedErrorReporting_raisesCompileErrorDuringClassCreation(self):
        class TSDelayErrors(TestSetup):
            DELAYED_PARSEERROR_REPORTING = False
        with pytest.raises(CompileError):
            self.c_mixin_from(b'#error p',
                              'compile_err_mixin_nodelay.c', base=TSDelayErrors)

    @pytest.yield_fixture
    def from_parent_dir(self):
        saved_cwd = os.getcwd()
        dirname = os.path.dirname(__file__)
        parent_dirname = os.path.dirname(dirname)
        os.chdir(parent_dirname)
        try:
            yield os.path.basename(dirname)
        finally:
            os.chdir(saved_cwd)

    def test_getTsAbspath_returnsAbsPathOfFile(self, from_parent_dir):
        TSDummy = self.cls_from_c_str(b'', 'test.c')
        assert TSDummy.get_ts_abspath() \
               == os.path.join(os.path.abspath(from_parent_dir),
                               'test_testsetup.py')

    def test_getSrcDir_returnsAbsDirOfFile(self, from_parent_dir):
        TSDummy = self.cls_from_c_str(b'', 'test.c')
        assert TSDummy.get_src_dir() == os.path.abspath(from_parent_dir)

    def test_getBuildDir_onStaticTSCls_returnsPathQualName(self, from_parent_dir):
        assert self.TSEmpty.get_build_dir() \
               == os.path.normpath(os.path.join(os.path.abspath(__file__), '..',
                                                TSDummy._BUILD_DIR_,
                                                'TestTestSetup.TSEmpty'))

    def test_getBuildDir_onDynamicGeneratedTSCls_returnsPathWithQualNameAndUid(self, from_parent_dir):
        TSDummy = self.cls_from_c_str(b'', 'test.c')
        assert TSDummy.get_build_dir()[:-32] \
               == os.path.join(os.path.abspath(from_parent_dir),
                               TSDummy._BUILD_DIR_,
                               'TestTestSetup.cls_from_c_str.TSDummy_')
        int(TSDummy.get_build_dir()[-32:], 16)   # expect hexnumber at the end

    def test_getBuildDir_onDynamicGeneratedTSClsWithSameParams_returnsSameDir(self, from_parent_dir):
        TSDummy1 = self.cls_from_c_str(b'', 'test.c')
        TSDummy2 = self.cls_from_c_str(b'', 'test.c')
        assert TSDummy1.get_build_dir() == TSDummy2.get_build_dir()

    def test_getBuildDir_onDynamicGeneratedTSClsWithDifferentParams_returnsDifferentDir(self, from_parent_dir):
        TSDummy1 = self.cls_from_c_str(b'', 'test.c', A=1, B=222, C=3)
        TSDummy2 = self.cls_from_c_str(b'', 'test.c', A=1, B=2, C=3)
        assert TSDummy1.get_build_dir() != TSDummy2.get_build_dir()

    def test_getTsName_returnFirstCFileNamePlusClassName(self):
        @cmod_from_ccode(b'', 'hdr.h')
        @cmod_from_ccode(b'', 'src1.c')
        @cmod_from_ccode(b'', 'src2.c')
        class TSClassName(TestSetup): pass
        assert TSClassName.get_ts_name() == 'src2_TSClassName'

    def test_getTsName_onOnlyHeader_returnsHFileNamePlusClassName(self):
        @cmod_from_ccode(b'', 'hdr1.h')
        @cmod_from_ccode(b'', 'hdr2.h')
        class TSClassName(TestSetup): pass
        assert TSClassName.get_ts_name() == 'hdr2_TSClassName'

    def test_getTsName_onNoSourceFiles_returnsClassNameOnly(self):
        class TSClassName(TestSetup): pass
        assert TSClassName.get_ts_name() == 'TSClassName'

    def test_macroWrapper_ok(self):
        TS = self.cls_from_c_str(b'#define MACRONAME   123', 'macro.c')
        assert TS.MACRONAME == 123

    def test_macroWrapper_onNotConvertableMacros_raisesValueError(self):
        cls = self.cls_from_c_str(b'#define MACRONAME   (int[]) 3',
                                  'invalid_macro.c')
        ts = cls()
        with pytest.raises(ValueError):
            _ = ts.MACRONAME

    def test_create_onPredefinedMacro_providesMacroAsMember(self):
        TSMock = self.cls_from_c_str(b'', 'create_predef.c',
                                     A=None, B=1, C='')
        with TSMock() as ts:
            assert ts.A is None
            assert ts.B == 1
            assert ts.C is None

    @patch('headlock.testsetup.TestSetup.__startup__')
    def test_init_providesBuildAndLoadedButNotStartedDll(self, __startup__):
        TS = self.cls_from_c_str(b'int var;', 'init_calls_load.c')
        ts = TS()
        try:
            __startup__.assert_not_called()
            assert hasattr(ts, 'var')
        finally:
            ts.__unload__()

    def test_build_onPredefinedMacros_passesMacrosToCompiler(self):
        TSMock = self.cls_from_c_str(b'int a = A;\n'
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

    @patch('headlock.testsetup.TestSetup.__shutdown__')
    def test_unload_doesAnImplicitShutdown(self, __shutdown__):
        TS = self.cls_from_c_str(b'int var;', 'unload_calls_shutdown.c')
        ts = TS()
        ts.__shutdown__.assert_not_called()
        ts.__unload__()
        ts.__shutdown__.assert_called_once()
        assert not hasattr(ts, 'var')

    def test_startup_doesAnImplicitLoad(self):
        TS = self.cls_from_c_str(b'', 'startup_calls_load.c')
        ts = TS()
        ts.__load__ = Mock()
        ts.__startup__()
        ts.__load__.assert_called_once()

    def test_contextmgr_onCompilableCCode_callsStartupAndShutdown(self):
        TSMock = self.cls_from_c_str(b'', 'contextmgr.c')
        ts = TSMock()
        ts.__startup__ = Mock(side_effect=ts.__startup__)
        ts.__shutdown__ = Mock(side_effect=ts.__shutdown__)
        with ts as ts2:
            assert ts is ts2
            ts.__startup__.assert_called_once()
            ts.__shutdown__.assert_not_called()
        ts.__startup__.assert_called_once()
        ts.__shutdown__.assert_called_once()

    def test_contextmgr_onCompilableCCode_catchesExceptions(self):
        TSMock = self.cls_from_c_str(b'', 'contextmgr_on_exception.c')
        with pytest.raises(ValueError):
            with TSMock() as ts:
                raise ValueError();

    def test_funcWrapper_ok(self):
        TSMock = self.cls_from_c_str(b'int func(int a, int b) { return a+b; }',
                                     'func.c')
        with TSMock() as ts:
            assert ts.func(11, 22) == 33

    def test_varWrapper_ok(self):
        TSMock = self.cls_from_c_str(b'int var = 11;', 'var.c')
        with TSMock() as ts:
            assert ts.var.val == 11
            ts.var.val = 22
            assert ts.var.val == 22

    def test_mockVarWrapper_ok(self):
        TSMock = self.cls_from_c_str(b'extern int var;', 'mocked_var.c')
        with TSMock() as ts:
            assert ts.var.val == 0
            ts.var.val = 11
            assert ts.var.val == 11

    def test_mockFuncWrapper_ok(self):
        @cmod_from_ccode(b'int func(int * a, int * b);', 'mocked_func.c')
        class TSMock(TestSetup):
            func_mock = Mock(return_value=33)
        with TSMock() as ts:
            assert ts.func(11, 22) == 33
            TSMock.func_mock.assert_called_with(ts.int.ptr(11), ts.int.ptr(22))

    def test_mockFuncWrapper_onNotExistingMockFunc_forwardsToMockFallbackFunc(self):
        @cmod_from_ccode(b'int func(int * a, int * b);',
                       'mocked_func_fallback.c')
        class TSMock(TestSetup):
            mock_fallback = Mock(return_value=33)
        with TSMock() as ts:
            assert ts.func(11, 22) == 33
            TSMock.mock_fallback.assert_called_with('func', ts.int.ptr(11),
                                                    ts.int.ptr(22))

    def test_mockFuncWrapper_createsCWrapperCode(self):
        @cmod_from_ccode(b'int mocked_func(int p);'
                       b'int func(int p) { '
                       b'   return mocked_func(p); }',
                       'mocked_func_cwrapper.c')
        class TSMock(TestSetup):
            mocked_func_mock = Mock(return_value=22)
        with TSMock() as ts:
            assert ts.func(11) == 22
            TSMock.mocked_func_mock.assert_called_once_with(11)

    def test_mockFuncWrapper_onUnmockedFunc_raisesMethodNotMockedError(self):
        TSMock = self.cls_from_c_str(b'void unmocked_func();',
                                     'mocked_func_error.c')
        with TSMock() as ts:
            with pytest.raises(MethodNotMockedError) as excinfo:
                assert ts.mock_fallback('unmocked_func', 11, 22)
            assert "unmocked_func" in str(excinfo.value)

    def test_typedefWrapper_storesTypeDefInTypedefCls(self):
        TSMock = self.cls_from_c_str(b'typedef int td_t;', 'typedef.c')
        with TSMock() as ts:
            assert issubclass(ts.td_t, CInt)

    def test_structWrapper_storesStructDefInStructCls(self):
        TSMock = self.cls_from_c_str(b'struct strct_t { };', 'struct.c')
        with TSMock() as ts:
            assert issubclass(ts.struct.strct_t, CStruct)

    def test_structWrapper_onContainedStruct_ensuresContainedStructDeclaredFirst(self):
        TSMock = self.cls_from_c_str(
            b'struct s2_t { '
            b'     struct s1_t { int m; } s1; '
            b'     struct s3_t { int m; } s3;'
            b'} ;'
            b'void f(struct s2_t);',
            'inorder_defined_structs.c')
        with TSMock(): pass

    def test_structWrapper_onContainedStructPtr_ensuresNonPtrMembersDeclaredFirst(self):
        TSMock = self.cls_from_c_str(
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

    def test_structWrapper_onAnonymousStruct_ok(self):
        TSMock = self.cls_from_c_str(b'struct { int a; } var;',
                                     'anonymous_structs.c')
        with TSMock() as ts:
            assert type(ts.var) == list(ts.struct.__dict__.values())[0]

    def test_enumWrapper_storesEnumDefInEnumCls(self):
        TSMock = self.cls_from_c_str(b'enum enum_t { a };', 'enum.c')
        with TSMock() as ts:
            assert issubclass(ts.enum.enum_t, CEnum)

    def test_onTestSetupComposedOfDifferentCModules_parseAndCompileCModulesIndependently(self):
        @cmod_from_ccode(b'#if defined(B)\n'
                         b'#error B not allowed\n'
                         b'#endif\n'
                         b'int a = A;'
                         b'extern int b;',
                         'diff_params_mod_a.c',
                         A=1)
        @cmod_from_ccode(b'#if defined(A)\n'
                         b'#error A not allowed\n'
                         b'#endif\n'
                         b'extern int a;'
                         b'int b = B;',
                         'diff_params_mod_b.c',
                         B=2)
        class TSDummy(TestSetup):
            DELAYED_PARSEERROR_REPORTING = False
        with TSDummy() as ts:
            assert ts.a.val == 1
            assert ts.b.val == 2

    @pytest.mark.skip
    def test_onCompilationError_raisesBuildError(self):
        TS = self.cls_from_c_str(b'void func(void) {undefined_FUNC();}',
                                 'undefined_symbol.c')
        try:
            TS()
        except BuildError as e:
            assert 'undefined_FUNC' in str(e)
        else:
            raise AssertionError()

    def test_registerUnloadEvent_onRegisteredEvent_isCalledOnUnload(self):
        TSDummy = self.cls_from_c_str(b'', 'test1.c')
        with TSDummy() as ts:
            def on_unload():
                calls.append('unloaded')
            ts.register_unload_event(on_unload)
            calls = []
        assert calls == ['unloaded']

    def test_registerUnloadEvent_onParams_arePassedWhenUnloaded(self):
        TSDummy = self.cls_from_c_str(b'', 'test2.c')
        with TSDummy() as ts:
            def on_unload(p1, p2):
                assert p1 == 'PARAM1' and p2 == 2
            ts.register_unload_event(on_unload, "PARAM1", 2)

    def test_registerUnloadEvent_onMultipleEvents_areCalledInReversedOrder(self):
        TSDummy = self.cls_from_c_str(b'', 'test3.c')
        with TSDummy() as ts:
            def on_unload(p):
                calls.append(p)
            ts.register_unload_event(on_unload, 1)
            ts.register_unload_event(on_unload, 2)
            ts.register_unload_event(on_unload, 3)
            calls = []
        assert calls == [3, 2, 1]

    def test_attributeAnnotationSupport_onStdIntIncluded_ok(self):
        TSDummy = self.cls_from_c_str(b'#include <stdint.h>\n'
                                      b'int __cdecl cdecl_func(void);',
                                      'attr_annotation_support.c')
        with TSDummy() as ts:
            assert 'cdecl' in ts.cdecl_func.c_attributes
