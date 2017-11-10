import pytest
from headlock.testsetup import TestSetup, CMakeList, MethodNotMockedError, \
    BuildError, CompileError
import os
import subprocess
from unittest.mock import patch, Mock
import tempfile
from headlock.c_data_model import CStruct, CEnum, CInt


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


class TestCMakeList:

    def test_init_withNewFilename_initializesMembersWithDefaults(self):
        new_filename = os.path.join(os.path.dirname(__file__), 'dummy')
        cmakelist = CMakeList(new_filename)
        assert not os.path.exists(new_filename)
        assert cmakelist.filename == new_filename
        assert all(l.startswith('#') for l in cmakelist.content.splitlines())
        assert cmakelist.cur_content is None

    def test_init_withExistingFilename_initializesMembersFromFile(self, tmpdir):
        filename = tmpdir.join('test.c')
        content = '#some dummycontent'
        filename.write_text(content, encoding='utf8')
        cmakelist = CMakeList(str(filename))
        assert cmakelist.filename == filename
        assert cmakelist.content == content
        assert cmakelist.cur_content == content

    def createCMakeListFrom(self, content):
        with tempfile.TemporaryDirectory() as dirname:
            filename = os.path.join(dirname, 'CMakeList.txt')
            open(filename, 'wt').write(content)
            cmakelist = CMakeList(filename)
        return cmakelist

    def test_set_onNotExistingEntry_addsEntry(self):
        cmakelist = self.createCMakeListFrom('#headcomment')
        cmakelist.set('cmdname', 'first parameter')
        assert cmakelist.content == '#headcomment\n' \
                                    'cmdname(first parameter)\n\n'

    def test_set_onExistingEntry_replacesEntry(self):
        cmakelist = self.createCMakeListFrom('cmdname(old_name)')
        cmakelist.set('cmdname', 'new_name')
        assert cmakelist.content == 'cmdname(new_name)\n\n'

    def test_set_onExistingEntryWithEmptyLines_replacesEntry(self):
        cmakelist = self.createCMakeListFrom('\n\n\ncmdname(old_name)\n\n\n')
        cmakelist.set('cmdname', 'new_name')
        assert cmakelist.content == '\n\n\ncmdname(new_name)\n\n\n'

    def test_set_onExistingEntryInMiddle_replacesEntry(self):
        cmakelist = self.createCMakeListFrom('#headcomment\n'
                                             'cmdname(old_name)\n'
                                             '#tailcomment')
        cmakelist.set('cmdname', 'new_name')
        assert cmakelist.content == '#headcomment\n' \
                                    'cmdname(new_name)\n\n' \
                                    '#tailcomment'

    def test_set_onMultipleExistingEntries_replacesFirstEntryAndRemovesOthers(self):
        cmakelist = self.createCMakeListFrom('cmdname(old_name1)\n'
                                             '#middlecomment\n'
                                             'cmdname(old_name2)\n')
        cmakelist.set('cmdname', 'new_name')
        assert cmakelist.content == 'cmdname(new_name)\n\n' \
                                    '#middlecomment\n'

    def test_set_onExistingEntryWithKeyParam_replacesEntry(self):
        cmakelist = self.createCMakeListFrom('cmdname(keyparam old value)')
        cmakelist.set('cmdname', key_param='keyparam', params='new value')
        assert cmakelist.content == 'cmdname(keyparam new value)\n\n'

    def test_set_onExistingEntryWithQuotes_detectCorrectly(self):
        cmakelist = self.createCMakeListFrom('cmdname(a "b c" d "e \\" f" g)')
        cmakelist.set('cmdname', 'replace_val')
        assert cmakelist.content == 'cmdname(replace_val)\n\n'

    def test_set_onExistingFile_keepsCurContent(self):
        cmakelist = self.createCMakeListFrom('')
        cmakelist.set('cmdname', 'value')
        assert cmakelist.cur_content == ''

    def test_escape_onNoParensAndQuotes_doesNotQuote(self):
        unquoted_text = 'Test .*! Text'
        assert CMakeList.escape(unquoted_text) == unquoted_text

    def test_escape_onParens_setsInQuotes(self):
        unquoted_text = 'Prefix (Abc) Postfix'
        assert CMakeList.escape(unquoted_text) == '"' + unquoted_text + '"'

    def test_escape_onQuotes_setsInQuotesAndEscapesExistingQuotes(self):
        assert CMakeList.escape('Prefix "Abc" Postfix') \
               == r'"Prefix \"Abc\" Postfix"'

    def test_update_onNoModification_doesNotTouchFile(self):
        cmakelist = self.createCMakeListFrom('cmdname(value)')
        # ensure that directory of CMakeList.txt is already deleted
        # => if .update() would write an error would be generated
        assert not os.path.exists(os.path.dirname(cmakelist.filename))
        assert not cmakelist.update()

    def test_update_onModification_updatesFile(self, tmpdir):
        filename = tmpdir.join('CMakeList.txt')
        filename.write_text('cmdname(value)', encoding='utf8')
        cmakelist = CMakeList(str(filename))
        cmakelist.set('cmdname', 'newvalue')
        assert cmakelist.update()
        assert filename.read_text(encoding='utf8') == 'cmdname(newvalue)\n\n'


class TestTestSetup(object):

    @staticmethod
    def c_mixin_from(tmpdir, src, filename, base=TestSetup, **macros):
        sourcefile = tmpdir.join(filename)
        sourcefile.write_binary(src)
        return base.c_mixin(str(sourcefile), **macros)

    class TSDummy(TestSetup):
        pass

    def test_cMixin_createsClassDerivedFromTestSetup(self, tmpdir):
        mixin = self.c_mixin_from(tmpdir, b'', 'empty.c')
        assert issubclass(mixin, TestSetup)

    def test_cMixin_onCalledTwice_createsTwoDifferentClasses(self, tmpdir):
        mixin1 = self.c_mixin_from(tmpdir, b'', filename='srcfile1.c')
        mixin2 = self.c_mixin_from(tmpdir, b'', filename='srcfile1.c')
        assert mixin1 is not mixin2

    def test_cMixin_createsClassWithNameOfFirstSourceFile(self, tmpdir):
        main_fn = tmpdir.join('main_file.c')
        main_fn.write_binary(b'')
        second_fn = tmpdir.join('second_file.c')
        second_fn.write_binary(b'')
        assert TestSetup.c_mixin(main_fn, second_fn).__name__ \
               == 'Main_file'

    def test_cMixin_callsAddSourceFile(self, tmpdir):
        sourcefile = tmpdir.join('sourcefile.c')
        sourcefile.write_binary(b'')
        with patch('headlock.testsetup.TestSetup.__add_source_file__') as mock:
            TestSetup.c_mixin(str(sourcefile))
        mock.assert_called_with(str(sourcefile))

    def test_cMixin_callsAddMacro(self, tmpdir):
        with patch('headlock.testsetup.TestSetup.__add_macro__') as mock:
            self.c_mixin_from(tmpdir, b'', 'predef_macro.c', A=1, B='')
        mock.assert_any_call('A', 1)
        mock.assert_any_call('B', '')

    def test_cMixin_onValidSource_ok(self, tmpdir):
        self.c_mixin_from(tmpdir, b'/* valid C source code */', 'comment.c')

    @pytest.mark.parametrize('exp_exc',
                             [subprocess.CalledProcessError(1, 'x'),
                              FileNotFoundError()])
    def test_cMixin_onFailedCallCMake_raisesBuildErrorDuringInstanciation(self, exp_exc, tmpdir):
        cls = self.c_mixin_from(tmpdir, b'', 'cmake_err.c')
        with patch('subprocess.Popen', Mock(side_effect=exp_exc)):
            with pytest.raises(BuildError):
                cls()

    def test_cMixin_onInvalidSourceCode_raisesCompileErrorDuringInstanciation(self, tmpdir):
        cls = self.c_mixin_from(tmpdir, b'#error p', 'compile_err_mixin.c')
        try:
            cls()
        except CompileError as exc:
            assert exc.testsetup == cls
            assert len(exc.errors) == 1
        else:
            raise AssertionError('Expected to raise CompileError')

    def test_cMixin_onNotDelayedErrorReporting_raisesCompileErrorDuringClassCreation(self, tmpdir):
        class TSDelayErrors(TestSetup):
            DELAYED_PARSEERROR_REPORTING = False
        with pytest.raises(CompileError):
            self.c_mixin_from(tmpdir, b'#error p',
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
        assert self.TSDummy.get_ts_abspath() \
               == os.path.join(os.path.abspath(from_parent_dir),
                               'test_testsetup.py')

    def test_getSrcDir_returnsAbsDirOfFile(self, from_parent_dir):
        assert self.TSDummy.get_src_dir() == os.path.abspath(from_parent_dir)

    def test_getBuildDir_returnsAbsBuildSubDir(self, from_parent_dir):
        assert self.TSDummy.get_build_dir() \
               == os.path.join(os.path.abspath(from_parent_dir),
                               self.TSDummy._BUILD_DIR_)

    def test_getTsName_returnFirstCFileNamePlusClassName(self, tmpdir):
        files = list(map(tmpdir.join, ['hdr.h', 'src1.c', 'src2.c']))
        for f in files:
            f.write_binary(b'')
        class TSClassName(TestSetup.c_mixin(*map(str, files))): pass
        assert TSClassName.get_ts_name() == 'src1_TSClassName'

    def test_getTsName_onOnlyHeader_returnsHFileNamePlusClassName(self, tmpdir):
        files = list(map(tmpdir.join, ['hdr1.h', 'hdr2.h']))
        for f in files:
            f.write_binary(b'')
        class TSClassName(TestSetup.c_mixin(*map(str, files))): pass
        assert TSClassName.get_ts_name() == 'hdr1_TSClassName'

    def test_getTsName_onNoSourceFiles_returnsClassNameOnly(self, tmpdir):
        class TSClassName(TestSetup.c_mixin()): pass
        assert TSClassName.get_ts_name() == 'TSClassName'

    def test_macroWrapper_ok(self, tmpdir):
        TS = self.c_mixin_from(tmpdir, b'#define MACRONAME   123', 'macro.c')
        assert TS.MACRONAME == 123

    def test_macroWrapper_onNotConvertableMacros_raisesValueError(self, tmpdir):
        cls = self.c_mixin_from(tmpdir, b'#define MACRONAME   (int[]) 3',
                                'invalid_macro.c')
        ts = cls()
        with pytest.raises(ValueError):
            _ = ts.MACRONAME

    @patch('headlock.testsetup.TestSetup.__load__')
    @patch('headlock.testsetup.TestSetup.__unload__')
    def test_execute_onCompilableCCode_callsLoadAndUnload(self, __load__, __unload__, tmpdir):
        TSMock = self.c_mixin_from(tmpdir, b'', 'execute.c')
        ts = TSMock()
        with ts.__execute__() as returned_obj:
            assert returned_obj == ts
            ts.__load__.assert_called_once()
            ts.__unload__.assert_not_called()
        ts.__load__.assert_called_once()
        ts.__unload__.assert_called_once()

    def test_funcWrapper_ok(self, tmpdir):
        TSMock = self.c_mixin_from(tmpdir,
                                   b'int func(int a, int b) { return a + b; }',
                                   'func.c')
        ts = TSMock()
        with ts.__execute__():
            assert ts.func(11, 22) == 33

    def test_varWrapper_ok(self, tmpdir):
        TSMock = self.c_mixin_from(tmpdir, b'int var;', 'var.c')
        ts = TSMock()
        with ts.__execute__():
            ts.var.val = 11
            assert ts.var.val == 11

    def test_typedefWrapper_storesTypeDefInTypedefCls(self, tmpdir):
        TSMock = self.c_mixin_from(tmpdir, b'typedef int td_t;', 'typedef.c')
        ts = TSMock()
        with ts.__execute__():
            assert issubclass(ts.td_t, CInt)

    def test_structWrapper_storesStructDefInStructCls(self, tmpdir):
        TSMock = self.c_mixin_from(tmpdir, b'struct strct_t { };', 'struct.c')
        ts = TSMock()
        with ts.__execute__():
            assert issubclass(ts.struct.strct_t, CStruct)

    def test_enumWrapper_storesEnumDefInEnumCls(self, tmpdir):
        TSMock = self.c_mixin_from(tmpdir, b'enum enum_t { a };', 'enum.c')
        ts = TSMock()
        with ts.__execute__():
            assert issubclass(ts.enum.enum_t, CEnum)

    def test_mockVarWrapper_ok(self, tmpdir):
        TSMock = self.c_mixin_from(tmpdir, b'extern int var;', 'mocked_var.c')
        ts = TSMock()
        with ts.__execute__():
            ts.var.val = 11
            assert ts.var.val == 11

    def test_mockFuncWrapper_ok(self, tmpdir):
        class TSMock(self.c_mixin_from(tmpdir, b'int func(int * a, int * b);',
                                       'mocked_func.c')):
            func_mock = Mock(return_value=33)
        ts = TSMock()
        with ts.__execute__():
            assert ts.func(11, 22) == 33
            TSMock.func_mock.assert_called_with(ts.int.ptr(11), ts.int.ptr(22))

    def test_mockFuncWrapper_onNotExistingMockFunc_forwardsToMockFallbackFunc(self, tmpdir):
        class TSMock(self.c_mixin_from(tmpdir, b'int func(int * a, int * b);',
                                       'mocked_func_fallback.c')):
            mock_fallback = Mock(return_value=33)
        ts = TSMock()
        with ts.__execute__():
            assert ts.func(11, 22) == 33
            TSMock.mock_fallback.assert_called_with('func', ts.int.ptr(11),
                                                    ts.int.ptr(22))

    def test_mockFuncWrapper_createsCWrapperCode(self, tmpdir):
        class TSMock(self.c_mixin_from(tmpdir,
                                       b'int mocked_func(int p);'
                                       b'int func(int p) { '
                                       b'   return mocked_func(p); }',
                                       'mocked_func_cwrapper.c')):
            mocked_func_mock = Mock(return_value=22)
        ts = TSMock()
        with ts.__execute__():
            assert ts.func(11) == 22
            TSMock.mocked_func_mock.assert_called_once_with(11)

    def test_mockFuncWrapper_onUnmockedFunc_raisesMethodNotMockedError(self, tmpdir):
        class TSMock(self.c_mixin_from(tmpdir, b'void unmocked_func();',
                                       'mocked_func_error.c')):
            pass
        ts = TSMock()
        with ts.__execute__():
            with pytest.raises(MethodNotMockedError) as excinfo:
                assert ts.mock_fallback('unmocked_func', 11, 22)
            assert "unmocked_func" in str(excinfo.value)

    def test_onCompilationError_raisesBuildError(self, tmpdir):
        TS = self.c_mixin_from(tmpdir, b'void func(void) { undefined_FUNC(); }',
                               'undefined_symbol.c')
        try:
            TS()
        except BuildError as e:
            assert 'undefined_FUNC' in str(e)
        else:
            raise AssertionError()

    def test_registerUnloadEvent_onRegisteredEvent_isCalledOnUnload(self):
        ts = self.TSDummy()
        with ts.__execute__():
            def on_unload():
                calls.append('unloaded')
            ts.register_unload_event(on_unload)
            calls = []
        assert calls == ['unloaded']

    def test_registerUnloadEvent_onParams_arePassedWhenUnloaded(self):
        ts = self.TSDummy()
        with ts.__execute__():
            def on_unload(p1, p2):
                assert p1 == 'PARAM1' and p2 == 2
            ts.register_unload_event(on_unload, "PARAM1", 2)

    def test_registerUnloadEvent_onMultipleEvents_areCalledInReversedOrder(self):
        ts = self.TSDummy()
        with ts.__execute__():
            def on_unload(p):
                calls.append(p)
            ts.register_unload_event(on_unload, 1)
            ts.register_unload_event(on_unload, 2)
            ts.register_unload_event(on_unload, 3)
            calls = []
        assert calls == [3, 2, 1]
