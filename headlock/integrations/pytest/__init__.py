"""PYTEST_DONT_REWRITE"""
import os
from os.path import relpath
import pytest


__all__ = ['testsetup_fixture', 'mem_ptr', 'val_ptr']


def testsetup_fixture(cls):
    """
    A decorator that converts any TestSetup derived class into a pytest fixture.

    Sample:

        @testsetup_fixture
        class ts(TestSetup): ...

        def TS_sample(ts):
            assert isinstance(ts, TestSetup)
    """
    @pytest.yield_fixture
    def ts_fixture(self=None):
        with cls() as ts:
            yield ts
    ts_fixture.type = cls
    return ts_fixture


class mem_ptr:
    """
    This is a wrapper for bytes objects that allows them to be directly
    compared to the raw attribute of an object refered by a headlock pointer.

    It is intentionally created for parameters in Mock.assert_called_*(...).

    Sample:

        c_ptr = ts.void.alloc_ptr(b'1234')
        assert c_ptr == mem_ptr(b'1234')

        # ATTENTION: This will also work, as only 2 bytes are compared:
        assert c_ptr == mem_ptr(b'12')
    """

    def __init__(self, exp_raw):
        self.exp_raw = exp_raw

    def __eq__(self, c_ptr):
        return c_ptr.ref.mem[:len(self.exp_raw)] == self.exp_raw

    def __repr__(self):
        return f"mem_ptr({self.exp_raw!r})"


class val_ptr:
    """
    This is a wrapper for bytes objects that allows them to be directly
    compared to the val attribute of an object refered by a headlock pointer.

    It is intentionally created for parameters in Mock.assert_called_*(...).

    Sample:

        c_ptr = ts.uint16_t(999).ptr
        assert c_ptr == val_ptr(999)
    """

    def __init__(self, exp_val):
        self.exp_val = exp_val

    def __eq__(self, c_ptr):
        return c_ptr.ref.val == self.exp_val

    def __repr__(self):
        return f"val_ptr({self.exp_raw!r})"
