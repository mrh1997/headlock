import contextlib

import pytest
from headlock.testsetup import TestSetup, MethodNotMockedError, \
    BuildError, CompileError, CModuleDecoratorBase, CModule, TransUnit
import os
import subprocess
from unittest.mock import patch, Mock, MagicMock, call
from headlock.c_data_model import CStruct, CEnum, CInt
from pathlib import Path


class TSDummy:
    pass

def build_dir(base_dir, content):
    for sub_name, sub_content in content.items():
        if isinstance(sub_content, dict):
            base_dir.mkdir(sub_name)
            build_dir(base_dir.join(sub_name), sub_content)
        else:
            base_dir.join(sub_name).write_binary(sub_content)

@contextlib.contextmanager
def sim_tsdummy_dir(base_dir, content):
    global __file__
    build_dir(base_dir, content)
    saved_file = __file__
    __file__ = str(base_dir.join('test_testsetup.py'))
    try:
        yield
    finally:
        __file__ = saved_file


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
        def __extend_by_transunit__(cls, transunit): pass

    def test_call_onCls_returnsDerivedClassWithSameNameAndModule(self):
        c_mod_decorator = CModuleDecoratorBase()
        TSDecorated = c_mod_decorator(self.TSDummy)
        assert issubclass(TSDecorated, self.TSDummy) \
               and TSDecorated is not self.TSDummy
        assert TSDecorated.__name__ == 'TSDummy'
        assert TSDecorated.__qualname__ == 'TestCModuleDecoratorBase.TSDummy'
        assert TSDecorated.__module__ == self.TSDummy.__module__

    @patch.object(TSDummy, '__extend_by_transunit__')
    def test_call_onCls_calls(self, __extend_by_transunit__):
        deco = CModuleDecoratorBase()
        tu1, tu2 = Mock(), Mock()
        deco.iter_transunits = Mock(return_value=[tu1, tu2])
        TSDecorated = deco(self.TSDummy)
        assert __extend_by_transunit__.call_args_list == [call(tu1), call(tu2)]


class TestCModule:

    def test_iterTransunits_onRelSrcFilename_resolves(self, tmpdir):
        with sim_tsdummy_dir(tmpdir, {'dir': {'src': b''}}):
            c_mod = CModule('dir/src')
            [transunit] = c_mod.iter_transunits(TSDummy)
            assert transunit.abs_src_filename == Path(tmpdir.join('dir/src'))

    def test_iterTransunits_onAbsSrcFilename_resolves(self, tmpdir):
        build_dir(tmpdir, {'dir': {'src': b''}})
        abs_path = str(tmpdir.join('dir/src'))
        c_mod = CModule(abs_path)
        [transunit] = c_mod.iter_transunits(TSDummy)
        assert transunit.abs_src_filename == Path(abs_path)

    class TSSubClass:
        pass

    def test_iterTransunits_setsSubsysName(self, tmpdir):
        with sim_tsdummy_dir(tmpdir, {'t1.c': b'', 't2.c': b''}):
            c_mod = CModule('t1.c', 't2.c')
            [transunit, *_] = c_mod.iter_transunits(self.TSSubClass)
            assert transunit.subsys_name \
                   == 't1.TSSubClass.TestCModule.test_testsetup'

    def test_iterTransunits_retrievesAndResolvesIncludeDirs(self, tmpdir):
        with sim_tsdummy_dir(tmpdir, {'src': b'', 'd1': {}, 'd2': {}}):
            c_mod = CModule('src', 'd1', 'd2')
            [transunit] = c_mod.iter_transunits(TSDummy)
            assert transunit.abs_incl_dirs == [Path(tmpdir.join('d1')),
                                               Path(tmpdir.join('d2'))]

    def test_iterTransunits_createsOneUnitTestPerSrcFilename(self, tmpdir):
        with sim_tsdummy_dir(tmpdir, {'t1.c': b'', 't2.c': b''}):
            c_mod = CModule('t1.c', 't2.c')
            assert [tu.abs_src_filename
                    for tu in c_mod.iter_transunits(TSDummy)] \
                    == [Path(tmpdir.join('t1.c')), Path(tmpdir.join('t2.c'))]

    def test_iterTransunits_onPredefMacros_passesMacrosToCompParams(self, tmpdir):
        with sim_tsdummy_dir(tmpdir, {'src': b''}):
            c_mod = CModule('src', MACRO1=11, MACRO2=22)
            [transunit] = c_mod.iter_transunits(TSDummy)
            assert transunit.predef_macros == {'MACRO1':11, 'MACRO2':22}

    def test_iterTransunits_onIncludeDirectories_resolvesDirs(self, tmpdir):
        with sim_tsdummy_dir(tmpdir, {'src': {'main.c': b''}, 'inc': {}}):
            c_mod = CModule('src\main.c', 'inc')
            [transunit] = c_mod.iter_transunits(TSDummy)
            assert transunit.abs_incl_dirs == [Path(tmpdir.join('inc'))]

    def test_iterTransunits_onInvalidPath_raiseIOError(self):
        c_mod = CModule('test_invalid.c')
        with pytest.raises(IOError):
            list(c_mod.iter_transunits(TSDummy))


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
        assert list(TSDummy.__transunits__) == list(transunits)

    def test_extendByTransunit_doesNotModifyParentCls(self):
        transunits = [MagicMock(), MagicMock()]
        class TSParent(TestSetup):
            __parser_factory__ = MagicMock()
        TSParent.__extend_by_transunit__(transunits[0])
        class TSChild(TSParent):
            pass
        TSChild.__extend_by_transunit__(transunits[1])
        assert list(TSParent.__transunits__) == transunits[:1]
        assert list(TSChild.__transunits__) == transunits[:2]

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
        TSDummy = self.cls_from_ccode(b'', 'test.c')
        assert TSDummy.get_ts_abspath() \
               == os.path.join(os.path.abspath(from_parent_dir),
                               'test_testsetup.py')

    def test_getSrcDir_returnsAbsDirOfFile(self, from_parent_dir):
        TSDummy = self.cls_from_ccode(b'', 'test.c')
        assert TSDummy.get_src_dir() == os.path.abspath(from_parent_dir)

    class TSEmpty(TestSetup):
        __transunits__ = [TransUnit('empty', Path(__file__, 'c_files/empty.c'),
                                    [], {})]

    def test_getBuildDir_onStaticTSCls_returnsPathQualName(self, from_parent_dir):
        assert self.TSEmpty.get_build_dir() \
               == os.path.normpath(os.path.join(os.path.abspath(__file__), '..',
                                                TestSetup._BUILD_DIR_,
                                                'TestTestSetup.TSEmpty'))

    def test_getBuildDir_onDynamicGeneratedTSCls_returnsPathWithQualNameAndUid(self, from_parent_dir):
        TSDummy = self.cls_from_ccode(b'', 'test.c')
        assert TSDummy.get_build_dir()[:-32] \
               == os.path.join(os.path.abspath(from_parent_dir),
                               TestSetup._BUILD_DIR_,
                               'TestTestSetup.cls_from_ccode.TSDummy_')
        int(TSDummy.get_build_dir()[-32:], 16)   # expect hexnumber at the end

    def test_getBuildDir_onDynamicGeneratedTSClsWithSameParams_returnsSameDir(self, from_parent_dir):
        TSDummy1 = self.cls_from_ccode(b'', 'test.c')
        TSDummy2 = self.cls_from_ccode(b'', 'test.c')
        assert TSDummy1.get_build_dir() == TSDummy2.get_build_dir()

    def test_getBuildDir_onDynamicGeneratedTSClsWithDifferentParams_returnsDifferentDir(self, from_parent_dir):
        TSDummy1 = self.cls_from_ccode(b'', 'test.c', A=1, B=222, C=3)
        TSDummy2 = self.cls_from_ccode(b'', 'test.c', A=1, B=2, C=3)
        assert TSDummy1.get_build_dir() != TSDummy2.get_build_dir()

    def test_getTsName_returnFirstFileNamePlusClassName(self, tmpdir):
        build_dir(tmpdir, {'dir': {'src1.c': b'', 'src2.c': b''}})
        class TSClassName(TestSetup): pass
        TSClassName.__extend_by_transunit__(
            TransUnit('', Path(tmpdir.join('dir/src1.c')), [], {}))
        TSClassName.__extend_by_transunit__(
            TransUnit('', Path(tmpdir.join('dir/src2.c')), [], {}))
        assert TSClassName.get_ts_name() == 'src2_TSClassName'

    def test_getTsName_onNoSourceFiles_returnsClassNameOnly(self):
        class TSClassName(TestSetup): pass
        assert TSClassName.get_ts_name() == 'TSClassName'

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

    @patch('headlock.testsetup.TestSetup.__startup__')
    def test_init_providesBuildAndLoadedButNotStartedDll(self, __startup__):
        TS = self.cls_from_ccode(b'int var;', 'init_calls_load.c')
        ts = TS()
        try:
            __startup__.assert_not_called()
            assert hasattr(ts, 'var')
        finally:
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

    @patch('headlock.testsetup.TestSetup.__shutdown__')
    def test_unload_doesAnImplicitShutdown(self, __shutdown__):
        TS = self.cls_from_ccode(b'int var;', 'unload_calls_shutdown.c')
        ts = TS()
        ts.__shutdown__.assert_not_called()
        ts.__unload__()
        ts.__shutdown__.assert_called_once()
        assert not hasattr(ts, 'var')

    def test_startup_doesAnImplicitLoad(self):
        TS = self.cls_from_ccode(b'', 'startup_calls_load.c')
        ts = TS()
        ts.__load__ = Mock()
        ts.__startup__()
        ts.__load__.assert_called_once()

    def test_contextmgr_onCompilableCCode_callsStartupAndShutdown(self):
        TSMock = self.cls_from_ccode(b'', 'contextmgr.c')
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
        TSMock = self.cls_from_ccode(b'', 'contextmgr_on_exception.c')
        with pytest.raises(ValueError):
            with TSMock() as ts:
                raise ValueError();

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

    def test_typedefWrapper_storesTypeDefInTypedefCls(self):
        TSMock = self.cls_from_ccode(b'typedef int td_t;', 'typedef.c')
        with TSMock() as ts:
            assert issubclass(ts.td_t, CInt)

    def test_structWrapper_storesStructDefInStructCls(self):
        TSMock = self.cls_from_ccode(b'struct strct_t { };', 'struct.c')
        with TSMock() as ts:
            assert issubclass(ts.struct.strct_t, CStruct)

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

    def test_structWrapper_onAnonymousStruct_ok(self):
        TSMock = self.cls_from_ccode(b'struct { int a; } var;',
                                     'anonymous_structs.c')
        with TSMock() as ts:
            assert type(ts.var) == list(ts.struct.__dict__.values())[0]

    def test_enumWrapper_storesEnumDefInEnumCls(self):
        TSMock = self.cls_from_ccode(b'enum enum_t { a };', 'enum.c')
        with TSMock() as ts:
            assert issubclass(ts.enum.enum_t, CEnum)

    def test_onTestSetupComposedOfDifferentCModules_parseAndCompileCModulesIndependently(self):
        class TSDummy(TestSetup):
            DELAYED_PARSEERROR_REPORTING = False
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

    @pytest.mark.skip
    def test_onCompilationError_raisesBuildError(self):
        TS = self.cls_from_ccode(b'void func(void) {undefined_FUNC();}',
                                 'undefined_symbol.c')
        try:
            TS()
        except BuildError as e:
            assert 'undefined_FUNC' in str(e)
        else:
            raise AssertionError()

    def test_registerUnloadEvent_onRegisteredEvent_isCalledOnUnload(self):
        TSDummy = self.cls_from_ccode(b'', 'test1.c')
        with TSDummy() as ts:
            def on_unload():
                calls.append('unloaded')
            ts.register_unload_event(on_unload)
            calls = []
        assert calls == ['unloaded']

    def test_registerUnloadEvent_onParams_arePassedWhenUnloaded(self):
        TSDummy = self.cls_from_ccode(b'', 'test2.c')
        with TSDummy() as ts:
            def on_unload(p1, p2):
                assert p1 == 'PARAM1' and p2 == 2
            ts.register_unload_event(on_unload, "PARAM1", 2)

    def test_registerUnloadEvent_onMultipleEvents_areCalledInReversedOrder(self):
        TSDummy = self.cls_from_ccode(b'', 'test3.c')
        with TSDummy() as ts:
            def on_unload(p):
                calls.append(p)
            ts.register_unload_event(on_unload, 1)
            ts.register_unload_event(on_unload, 2)
            ts.register_unload_event(on_unload, 3)
            calls = []
        assert calls == [3, 2, 1]

    def test_attributeAnnotationSupport_onStdIntIncluded_ok(self):
        TSDummy = self.cls_from_ccode(b'#include <stdint.h>\n'
                                      b'int __cdecl cdecl_func(void);',
                                      'attr_annotation_support.c')
        with TSDummy() as ts:
            assert 'cdecl' in ts.cdecl_func.c_attributes

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
