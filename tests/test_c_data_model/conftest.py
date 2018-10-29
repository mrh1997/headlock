import ctypes as ct
import sys
import pytest
import headlock.c_data_model as cdm


@pytest.fixture
def cint_type():
    return cdm.CIntType('typename', 32, True, ct.c_int32)

@pytest.fixture
def cint16_type():
    return cdm.CIntType('i16', 16, True, ct.c_int16)

@pytest.fixture
def cuint64_type():
    return cdm.CIntType('u64', 64, False, ct.c_uint64)

@pytest.fixture
def cfunc_type():
    return cdm.CFuncType()

@pytest.fixture
def cfunc_obj(cfunc_type):
    return cfunc_type(lambda:None)

@pytest.fixture
def libc():
    return ct.cdll.msvcrt if sys.platform == 'win32' else ct.CDLL('libc.so.6')


@pytest.fixture
def abs_cfunc_obj(cint_type, libc):
    abs_cfunc_type = cdm.CFuncType(cint_type, [cint_type])
    return abs_cfunc_type(libc.abs)
