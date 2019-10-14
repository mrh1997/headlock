"""
Run this script to rerun only the last failed test.

In contrary to the pytest builtin "--lf" option it reruns the last failed test
until the next regular test-run (no matter if the test fails or succeeds).

That means if you rerun a failed test and it succeeds "--lf" does NOT rerun
the test again, while this script reruns the test again.
This is especially useful for debugging purposes.
"""
import os
import sys
from pathlib import Path

import pytest
from headlock.buildsys_drvs import mingw

from .common import PYTEST_HEADLOCK_DIR


class DummyToolChain(mingw.get_default_builddesc_cls()):
    """
    This toolchain is a placeholder for an actual toolchain.
    It is used for debugging, where the .DLL is build by the IDE and shall
    not be overwritten by the python script
    """

    def exe_path(self):
        return self.build_dir / '__headlock_dbg__.dll'

    def build(self, additonal_c_sources=None):
        pass


def get_root_dir(root_dir=None):
    if root_dir is None:
        root_dir = Path.cwd()
    elif isinstance(root_dir, str):
        root_dir = Path(root_dir)
    while not (root_dir / PYTEST_HEADLOCK_DIR).exists():
        if root_dir.parent == root_dir:
            raise IOError("no test-run from within {Path.cwd()} was found!")
        root_dir = root_dir.parent
    return root_dir


def main(cur_dir=None):
    mingw.get_default_builddesc_cls = lambda: DummyToolChain

    print()
    print()


    try:
        root_dir = get_root_dir(cur_dir)
        with (root_dir/PYTEST_HEADLOCK_DIR/'CMakeLists.txt').open() as cmlist:
            cmlist.readline()
            cmlist.readline()
            run_test = cmlist.readline()[1:].strip()
    except (IOError, IndexError):
        print("%"*79)
        print("% there were no failed tests in last run or "
              "there was no testrun at all")
        print("%"*79)
        sys.exit(-1)
    else:
        try:
            os.chdir(root_dir)
            sys.path.insert(0, str(root_dir))
            pytest.main(['--keep-first-failed-pytest', '-v', run_test])
        except Exception as e:
            print("failure on running test: ", str(e))
            sys.exit(-2)


if __name__ == '__main__':
    main()
