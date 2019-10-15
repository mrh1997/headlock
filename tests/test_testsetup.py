import contextlib
import sys
from pathlib import Path
from unittest.mock import patch, Mock, call
import pytest
from threading import Thread
from time import sleep

from .helpers import build_tree
from headlock.testsetup import TestSetup, MethodNotMockedError, \
    CProxyDescriptor, CProxyTypeDescriptor, BuildError, CompileError, CModule
from headlock.buildsys_drvs import default
from headlock.buildsys_drvs.gcc import GccBuildDescription, \
    Gcc32BuildDescription
import headlock.c_data_model as cdm


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


class TestCProxyTypeDescriptor:

    @pytest.fixture
    def Dummy(self):
        class Dummy:
            attr = CProxyTypeDescriptor(cdm.BuildInDefs.int)
        return Dummy

    def test_get_onClass_returnsCProxyType(self, Dummy):
        assert Dummy.attr is cdm.BuildInDefs.int

    def test_get_onInstance_returnsCProxyWithAddrspace(self, Dummy):
        dummy = Dummy()
        dummy.__addrspace__ = Mock()
        assert isinstance(dummy.attr, cdm.CIntType)
        assert dummy.attr.__addrspace__ == dummy.__addrspace__

    def test_set_onInstance_raisesAttributeError(self, Dummy):
        with pytest.raises(AttributeError):
            Dummy().attr = 99


class TestCProxyDescriptor:

    @pytest.fixture
    def Dummy(self):
        class Dummy:
            attr = CProxyDescriptor("attr", cdm.BuildInDefs.int)
        return Dummy

    def test_get_onClass_returnsCProxyType(self, Dummy):
        assert Dummy.attr is cdm.BuildInDefs.int

    def test_get_onInstance_returnsCProxyWithAddrspace(self, Dummy):
        dummy = Dummy()
        dummy.__addrspace__ = Mock()
        assert isinstance(dummy.attr, cdm.CInt)
        assert dummy.attr.ctype.__addrspace__ == dummy.__addrspace__

    def test_set_onInstance_raisesAttributeError(self, Dummy):
        with pytest.raises(AttributeError):
            Dummy().attr = 99


class TestTestSetup(object):
    """
    This is an integration test, that tests the testsetup class and the
    collaboration of the headlock components
    """

    def abs_dir(self):
        return (Path(__file__).parent / 'c_files').resolve()

    def extend_builddesc(self, builddesc:GccBuildDescription,
                         source_code, filename):
        abs_filename = self.abs_dir() / filename
        abs_filename.write_bytes(source_code)
        builddesc.add_c_source(abs_filename)

    def create_builddesc(self, source_code, filename, *, unique_name=True,
                         **macros):
        builddesc = default.BUILDDESC_CLS(
            Path(filename).name,
            self.abs_dir() / (filename + '.build'),
            unique_name)
        builddesc.add_predef_macros(macros)
        self.extend_builddesc(builddesc, source_code, filename)
        return builddesc

    def cls_from_ccode(self, src, filename,
                       src_2=None, filename_2=None, **macros):
        builddesc = self.create_builddesc(src, filename, **macros)
        if src_2 is not None:
            self.extend_builddesc(builddesc, src_2, filename_2)
        class TSDummy(TestSetup): pass
        TSDummy.__set_builddesc__(builddesc)
        return TSDummy

    @pytest.fixture
    def ts_dummy(self):
        return self.cls_from_ccode(b'', 'test.c')

    class TSBuildDescFactory(TestSetup): pass

    def test_builddescFactory_returnsBuildDescWithGlobalBuildDirAndName(self):
        builddesc = self.TSBuildDescFactory.__builddesc_factory__()
        assert builddesc.name == 'TSBuildDescFactory.TestTestSetup'
        assert builddesc.build_dir \
               == Path(__file__).parent.resolve() / \
                    '.headlock/test_testsetup' / builddesc.name

    def test_builddescFactory_onLocalTestSetupDefinition_returnsBuildDescWithHashInBuilDir(self):
        class TSBuildDescFactory(TestSetup): pass
        builddesc = TSBuildDescFactory.__builddesc_factory__()
        int(builddesc.build_dir.name[-8:], 16)   # expect hexnumber at the end
        assert builddesc.build_dir.name[-9] == '_'

    def test_builddescFactory_onDynamicGeneratedTSClsWithSameParams_returnsBuildDescWithSameBuildDir(self):
        builddesc1 = self.create_builddesc(b'', 'test.c', unique_name=False,
                                           MACRO=1)
        builddesc2 = self.create_builddesc(b'', 'test.c', unique_name=False,
                                           MACRO=1)
        assert builddesc1.build_dir == builddesc2.build_dir

    def test_builddescFactory_onDynamicGeneratedTSClsWithDifferentParams_returnsBuildDescWithDifferentBuildDir(self):
        builddesc1 = self.create_builddesc(b'', 'test.c', unique_name=False,
                                           A=1, B=222, C=3)
        builddesc2 = self.create_builddesc(b'', 'test.c', unique_name=False,
                                           A=1, B=2, C=3)
        assert builddesc1.build_dir != builddesc2.build_dir

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

    def test_build_onMultipleFilesWithReferences_ok(self):
        TSMock = self.cls_from_ccode(
            b'void callee(void) { return; }', 'prev.c',
            b'void callee(void); void caller(void) { callee(); }', 'refprev.c')
        TSMock()

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
    def test_unload_onStarted_callsShutdown(self, __shutdown__):
        TS = self.cls_from_ccode(b'int var;', 'unload_calls_shutdown.c')
        ts = TS()
        ts.__startup__()
        ts.__unload__()
        __shutdown__.assert_called_once()

    @patch('headlock.testsetup.TestSetup.__shutdown__')
    def test_unload_onNotStarted_doesNotCallsShutdown(self, __shutdown__):
        TS = self.cls_from_ccode(b'int var;', 'unload_calls_shutdown.c')
        ts = TS()
        ts.__unload__()
        __shutdown__.assert_not_called()

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

    def test_funcWrapper_onNotInstantiatedTestSetup_returnsCProxyType(self):
        TSMock = self.cls_from_ccode(b'int func(int a, int b) { return a+b; }',
                                     'func_not_inst.c')
        assert isinstance(TSMock.func, cdm.CFuncType)
        assert isinstance(TSMock.func.returns, cdm.CIntType)

    def test_funcWrapper_ok(self):
        TSMock = self.cls_from_ccode(
            b'short func(char a, int *b) { return a + *b; }', 'func.c')
        with TSMock() as ts:
            assert ts.func(11, ts.int(22).adr) == 33

    def test_funcWrapper_onMultipleUniqueSignatures_ok(self):
        TSMock = self.cls_from_ccode(
            b'int func1(int a) { return 11; }'
            b'int func2(int a, int b) { return 22; }'
            b'int func3(int a, int b, int c) { return 33; }'
            b'int func4(int a, int b, int c, int d) { return 44; }',
            'func_multi_unique_sig.c')
        with TSMock() as ts:
            assert ts.func1(0) == 11
            assert ts.func2(0, 0) == 22
            assert ts.func3(0, 0, 0) == 33
            assert ts.func4(0, 0, 0, 0) == 44

    def test_funcWrapper_onMultipleIdenticalSignatures_ok(self):
        TSMock = self.cls_from_ccode(
            b'int func1(int a) { return 11; }'
            b'int func2(int a) { return 22; }',
            'func_multi_identical_sig.c')
        with TSMock() as ts:
            assert ts.func1(0) == 11
            assert ts.func2(0) == 22

    def test_funcWrapper_onStructAsParamAndReturnsValue_ok(self):
        TSMock = self.cls_from_ccode(
            b'struct param { int m1, m2; };\n'
            b'struct result { int m1, m2; };\n'
            b'struct result func(struct param p) {\n'
            b'    struct result r = {p.m1+1, p.m2+1};\n'
            b'    return r;\n'
            b'}',
            'func_with_struct.c')
        with TSMock() as ts:
            param = ts.struct.param(100, 200)
            assert ts.func(param) == dict(m1=101, m2=201)

    def test_funcPtrWrapper_ok(self):
        TSMock = self.cls_from_ccode(b'typedef int (* func_ptr_t)(int);\n'
                                     b'func_ptr_t func_ptr;\n'
                                     b'int call_func_ptr(int param) {\n'
                                     b'    return (*func_ptr)(param);\n'
                                     b'}',
                                     'funcptr.c')
        with TSMock() as ts:
            pyfunc = Mock(return_value=111)
            ts.func_ptr.val = ts.func_ptr_t(pyfunc)
            ts.call_func_ptr(2222)
            pyfunc.assert_called_once_with(2222)

    def test_funcPtrWrapper_requiringStruct_ok(self):
        TSMock = self.cls_from_ccode(b'typedef struct { int m1, m2; } strct;\n'
                                     b'typedef int (* func_ptr_t)(strct);\n'
                                     b'func_ptr_t func_ptr;',
                                     'funcptr_with_struct.c')
        with TSMock() as ts:
            def pyfunc(strct):
                assert strct.m1 == 1111
                assert strct.m2 == 2222
            ts.func_ptr.val = ts.func_ptr_t(pyfunc)
            ts.func_ptr(ts.strct(1111, 2222))

    def test_varWrapper_onNotInstantiatedTestSetup_returnsCProxyType(self):
        TSMock = self.cls_from_ccode(b'short var = 1;',
                                     'var_not_inst.c')
        assert isinstance(TSMock.var, cdm.CIntType)
        assert TSMock.var.sizeof == 2

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

    def test_mockFuncWrapper_createsCWrapperCode(self):
        TSMock = self.cls_from_ccode(
            b'int mocked_func(int p);'
            b'int func(int p) { return mocked_func(p) + 33; }',
            'mocked_func_cwrapper.c')
        with TSMock() as ts:
            ts.mocked_func_mock = Mock(return_value=22)
            assert ts.func(11) == 22 + 33
            ts.mocked_func_mock.assert_called_once_with(11)

    def test_mockFuncWrapper_onOverwriteStack_keepsCProxyVal(self):
        TSMock = self.cls_from_ccode(
            b'void f(int val);\n'
            b'void call_3_times(void) { f(1111); f(2222); f(3333); return; }',
            'multicalled_mock.c')
        with TSMock() as ts:
            call_params = []
            ts.f_mock = lambda param: call_params.append(param)
            ts.call_3_times()
            assert call_params == [1111, 2222, 3333]

    def test_headerFileOnly_createsMockOnly(self):
        TSMock = self.cls_from_ccode(b'int func();', 'header.h')
        with TSMock() as ts:
            ts.func_mock = Mock(return_value=123)
            assert ts.func().val == 123

    def test_mockFuncWrapper_onNotExistingMockFunc_forwardsToMockFallbackFunc(self):
        TSMock = self.cls_from_ccode(b'int func(int * a, int * b);',
                                     'mocked_func_fallback.c')
        with TSMock() as ts:
            ts.mock_fallback = Mock(return_value=33)
            assert ts.func(11, 22) == 33
            ts.mock_fallback.assert_called_with('func', ts.int.ptr(11),
                                                ts.int.ptr(22))

    def test_mockFuncWrapper_onUnmockedFunc_raisesMethodNotMockedError(self):
        TSMock = self.cls_from_ccode(b'void unmocked_func();',
                                     'mocked_func_error.c')
        with TSMock() as ts:
            with pytest.raises(MethodNotMockedError) as excinfo:
                assert ts.mock_fallback('unmocked_func', 11, 22)
            assert "unmocked_func" in str(excinfo.value)

    def test_mockFuncWrapper_onRaisesException_forwardsExcImmediatelyToCallingPyCode(self):
        TSMock = self.cls_from_ccode(b'void exc_func();\n'
                                     b'void func() { exc_func(); exc_func(); }',
                                     'exc_forwarder.c')
        with TSMock() as ts:
            ts.exc_func_mock = Mock(side_effect=ValueError)
            with pytest.raises(ValueError):
                ts.func()
            assert ts.exc_func_mock.call_count == 1

    def test_mockFuncWrapper_onRaisesException_forwardsExcOverMultipleBridges(self):
        TSMock = self.cls_from_ccode(b'void inner_py();\n'
                                     b'void outer_py();\n'
                                     b'void inner_c() { while(1) inner_py();}\n'
                                     b'void outer_c() { while(1) outer_py();}',
                                     'multibridged_exc_forwarder.c')
        with TSMock() as ts:
            ts.outer_py_mock = lambda: ts.inner_c()
            ts.inner_py_mock = Mock(side_effect=KeyError)
            with pytest.raises(KeyError):
                ts.outer_c()

    def test_mockFuncWrapper_onRaisesExceptionsInMultipleThreads_handlesEveryThreadSeparately(self):
        TSMock = self.cls_from_ccode(b'void exc_func(int tid);\n'
                                     b'void func(int tid) {exc_func(tid);}',
                                     'multithreaded_exc_forwarder.c')
        with TSMock() as ts:
            def exc_func(tid):
                sleep(0.030)
                raise ValueError(str(tid))
            ts.exc_func_mock = exc_func
            def thread_func(tid):
                with pytest.raises(ValueError, match=str(tid)):
                    ts.func(tid)
            threads = [Thread(target=thread_func, args=[tid])
                       for tid in range(5)]
            for thread in threads:
                thread.start()
                sleep(0.005)
            for thread in threads:
                thread.join()

    def test_typedefWrapper_storesTypeDefInTypedefCls(self):
        TSMock = self.cls_from_ccode(b'typedef int td_t;', 'typedef.c')
        with TSMock() as ts:
            assert ts.td_t == ts.int

    def test_typedefWrapper_instanciate_ok(self):
        TSMock = self.cls_from_ccode(b'typedef int i;', 'instantiate_typedef.c')
        with TSMock() as ts:
            assert ts.i(33) == 33

    def test_structWrapper_storesStructDefInStructCls(self):
        TSMock = self.cls_from_ccode(b'struct strct_t { };', 'struct.c')
        with TSMock() as ts:
            assert isinstance(ts.struct.strct_t, cdm.CStructType)

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
            assert ts.var.ctype == ts.struct.strct

    def test_structWrapper_onVarFromAnonymousStruct_ok(self):
        TSMock = self.cls_from_ccode(b'struct { int a; } var;',
                                     'anonymous_structs_var.c')
        with TSMock() as ts:
            assert isinstance(ts.var.ctype, cdm.CStructType)

    def test_structWrapper_onTypedefFromAnonymousStruct_renamesStructToMakeItUsableAsParameter(self):
        TSMock = self.cls_from_ccode(b'typedef struct { int a; } t;\n'
                                     b'void func(t * a);',
                                     'anonymous_structs_typedef.c')
        with TSMock() as ts:
            anon_cstruct_type = getattr(ts.struct, '__anonymousfromtypedef__t')
            assert not anon_cstruct_type.is_anonymous_struct()

    def test_structWrapper_onInstanciate_bindsAddrSpace(self):
        TSMock = self.cls_from_ccode(b'struct s_t { int a; };',
                                     'instanciated_struct.c')
        with TSMock() as ts:
            assert ts.struct.s_t(44) == dict(a=44)

    def test_enumWrapper_storesEnumDefInEnumCls(self):
        TSMock = self.cls_from_ccode(b'enum enum_t { a };', 'enum.c')
        with TSMock() as ts:
            assert isinstance(ts.enum.enum_t, cdm.CEnumType)

    def test_onSameStructWithAnonymousChildInDifferentModules_generateCorrectMockWrapper(self):
        TSDummy = self.cls_from_ccode(
            b'struct s { struct { int mm; } m; };\n'
            b'int func1(struct s p);\n', 'anonymstruct_mod1.c',
            b'struct s { struct { int mm; } m; };\n'
            b'int func2(struct s p);\n', 'anonymstruct_mod2.c')
        with TSDummy() as ts:
            pass

    def test_onPointerToArrayOfStruct_generatesCorrectMockWrapper(self):
        TSDummy = self.cls_from_ccode(b'typedef struct strct {} (*type)[1];\n'
                                      b'void func(type param);',
                                      'ptr_to_arr_of_strct.c')
        with TSDummy() as ts:
            pass

    def test_onConstStruct_ok(self):
        TSDummy = self.cls_from_ccode(b'const struct s {} x;',
                                      'const_strct.c')
        with TSDummy() as ts:
            pass

    def test_onTwoTestsetups_haveDifferentStructCollections(self):
        TS1 = self.cls_from_ccode(b'struct s { int a; };', 'struct1.c')
        TS2 = self.cls_from_ccode(b'struct s { int b; };', 'struct2.c')
        assert hasattr(TS1.struct.s, 'a')
        assert hasattr(TS2.struct.s, 'b')

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

    @pytest.mark.skipif(sys.platform != 'win32',
                        reason='Currently there is not Linux '
                               'equivalent to __cdecl')
    def test_attributeAnnotationSupport_onStdIntIncluded_ok(self):
        TSDummy = self.cls_from_ccode(b'#include <stdint.h>\n'
                                      b'int __cdecl cdecl_func(void);',
                                      'attr_annotation_support.c')
        with TSDummy() as ts:
            assert '__cdecl' in ts.cdecl_func.ctype.__c_attribs__


class TestCModule:

    class TestSetupMock:
        __builddesc__ = None
        @classmethod
        def __builddesc_factory__(cls):
            return Gcc32BuildDescription('', Path(''))
        @classmethod
        def __set_builddesc__(cls, builddesc):
            cls.__builddesc__ = builddesc

    @patch.object(Path, 'is_file', return_value=True)
    def test_call_onSrcPath_derivesBuilddescFactoryToAddAbsSrcPath(self, is_file):
        @CModule('rel_src.c')
        class TSRelSrc(self.TestSetupMock): pass
        abs_c_src = Path(__file__).resolve().parent / 'rel_src.c'
        assert TSRelSrc.__builddesc__.c_sources() == [abs_c_src]
        is_file.assert_called_with(abs_c_src)

    @patch.object(Path, 'is_file', return_value=False)
    def test_call_onInvalidSrcPath_raisesOSError(self, is_file):
        with pytest.raises(OSError):
            @CModule('rel_src.c')
            class TSInvalidSrc(self.TestSetupMock): pass

    @patch.object(Path, 'is_file', return_value=True)
    def test_call_onPredefMacros_derivsBuilddescFactoryToAddPredefMacros(self, is_file):
        @CModule('src.c', MACRO1=1, MACRO2='')
        class TSPredefMacros(self.TestSetupMock): pass
        abs_c_src = Path(__file__).resolve().parent / 'src.c'
        assert TSPredefMacros.__builddesc__.predef_macros() \
               == {abs_c_src: dict(MACRO1='1', MACRO2='')}

    @patch.object(Path, 'is_file', return_value=True)
    @patch.object(Path, 'is_dir', return_value=True)
    def test_call_onInclOrLibDir_derivesBuilddescFactoryToSetAbsDirPath(self, is_dir, is_file):
        @CModule('src.c', include_dirs=['rel/dir'])
        class TSRelDir(self.TestSetupMock): pass
        abs_src = Path(__file__).resolve().parent / 'src.c'
        abs_path = Path(__file__).resolve().parent / 'rel/dir'
        assert TSRelDir.__builddesc__.incl_dirs() == {abs_src: [abs_path]}
        is_dir.assert_called_with(abs_path)

    @patch.object(Path, 'is_file', return_value=True)
    @patch.object(Path, 'is_dir', return_value=False)
    @pytest.mark.parametrize('dir_name', ['library_dirs', 'include_dirs'])
    def test_call_onInvalidInclOrLibDir_raisesOSError(self, is_dir, is_file, dir_name):
        with pytest.raises(OSError):
            @CModule('src.c', **{dir_name: 'invalid/dir'})
            class TSInvalidDir(self.TestSetupMock): pass

    @patch.object(Path, 'is_file', return_value=True)
    def test_call_onDerivedClass_doesNotModifyBaseClassesBuildDesc(self, is_file):
        @CModule('src_base.c')
        class TSBase(self.TestSetupMock): pass
        @CModule('src_derived.c')
        class TSDerived(TSBase): pass
        assert {p.name for p in TSBase.__builddesc__.c_sources()} \
               == {'src_base.c'}
        assert {p.name for p in TSDerived.__builddesc__.c_sources()} \
               == {'src_base.c', 'src_derived.c'}
