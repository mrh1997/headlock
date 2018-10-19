import ctypes as ct
import pytest
import headlock.c_data_model as cdm


@pytest.fixture
def cint_type():
    return cdm.CIntType('typename', 32, True, ct.c_int32)

@pytest.fixture
def cint16_type():
    return cdm.CIntType('i16', 16, True, ct.c_int16)

@pytest.fixture
def cfunc_type():
    return cdm.CFuncType()

@pytest.fixture
def cfunc_obj(cfunc_type):
    return cfunc_type(lambda:None)

@pytest.fixture
def abs_cfunc_obj(cint_type):
    abs_cfunc_type = cdm.CFuncType(cint_type, [cint_type])
    return abs_cfunc_type(ct.cdll.msvcrt.abs)
