"""
This pytest plugin stops immediately, if a test fails, since a testsetup could
not be build
(it is expected  that the following tests will also fail)
"""
from pathlib import Path
import pytest
from _pytest.runner import TestReport
from headlock.testsetup import CompileError, BuildError


stop_testing = False


def report_errors(exc, rootdir):
    resolved_rootdir = Path(rootdir).resolve()
    print()
    if isinstance(exc, CompileError):
        print('==== ERROR IN C SOURCE CODE ===================')
        for text, file, lineno in exc.errors:
            try:
                out_file = Path(rootdir) / \
                           Path(file).relative_to(resolved_rootdir)
            except ValueError:
                out_file = file
            print(f"{out_file}:{lineno}: {text}")
        print('===============================================')
    else:
        print(f"FAILED TO BUILD {exc.path.name}: {exc}")


class TestSetupModule(pytest.Module):

    def _importtestmodule(self):
        try:
            return super()._importtestmodule()
        except BuildError as exc:
            report_errors(exc, self.config.rootdir)
            pytest.exit(1)


def pytest_pycollect_makemodule(path, parent):
    return TestSetupModule(path, parent)


def pytest_runtest_makereport(item, call):
    global stop_testing
    if call.excinfo is not None and isinstance(call.excinfo.value, BuildError):
        exc = call.excinfo.value
        stop_testing = True
        report_errors(exc, item.config.rootdir)
        firstlineno = 0 if not hasattr(item, 'function') \
                      else item.function.__code__.co_firstlineno
        return TestReport(item.nodeid, (item.fspath, firstlineno, str(exc)),
                          None, 'failed', None, call.when)
    if call.when == 'teardown' and stop_testing:
        pytest.exit(1)
