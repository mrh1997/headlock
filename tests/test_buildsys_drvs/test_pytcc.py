import pytest

from headlock.buildsys_drvs.pytcc import PyTccBuildDescription
import os
from ctypes import CDLL

class TestPyTccBuildDescription:

    @pytest.fixture
    def test_c_file(self, tmp_path):
        return tmp_path / "test.c"

    def test_build_onBasicScenario_ok(self, tmp_path, test_c_file):
        test_c_file.write_text("extern int test_func(void) { return 99; }")
        build_desc = PyTccBuildDescription(
            "TD", tmp_path,
            c_sources=[test_c_file])
        build_desc.build()
        cdll = CDLL(os.fspath(build_desc.exe_path()))
        assert cdll.test_func() == 99

    def test_build_onPassMacro_ok(self, tmp_path, test_c_file):
        test_c_file.write_text("#if ! defined(TESTMACRO)\n  #error X\n  #endif")
        build_desc = PyTccBuildDescription(
            "TD", tmp_path,
            c_sources=[test_c_file],
            predef_macros=dict(TESTMACRO="1"))
        build_desc.build()

    def test_build_onPassIncludeDir_ok(self, tmp_path, test_c_file):
        test_c_file.write_text('#include "test.h"')
        incl_dir = tmp_path / "subdir"
        incl_dir.mkdir()
        (incl_dir / "test.h").write_text("//header file")
        build_desc = PyTccBuildDescription(
            "TD", tmp_path,
            c_sources=[test_c_file],
            incl_dirs=[incl_dir])
        build_desc.build()

    def test_build_onMultipleSourceFiles_ok(self, tmp_path, test_c_file):
        test_c_file.write_text('extern int a; int func(void) { a=9; }')
        test2_c_file = tmp_path / "test2.c"
        test2_c_file.write_text("int a = 9;")
        build_desc = PyTccBuildDescription(
            "TD", tmp_path,
            c_sources=[test_c_file, test2_c_file])
        build_desc.build()

    def test_build_onAdditionalCFiles_ok(self, tmp_path, test_c_file):
        test_c_file.write_text('extern int a; int func(void) { a=9; }')
        test2_c_file = tmp_path / "test2.c"
        test2_c_file.write_text("int a = 9;")
        build_desc = PyTccBuildDescription(
            "TD", tmp_path,
            c_sources=[test_c_file])
        build_desc.build([test2_c_file])
