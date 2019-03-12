import ctypes as ct
import pytest
import sys
import headlock.c_data_model as cdm
from headlock.address_space.virtual import VirtualAddressSpace


@pytest.fixture
def addrspace():
    return VirtualAddressSpace(b'abcdefgh')

@pytest.fixture
def unbound_cint_type():
    return cdm.CIntType('cint', 32, True, cdm.ENDIANESS, None)

@pytest.fixture
def unbound_cint16_type(addrspace):
    return cdm.CIntType('cint16', 16, True, cdm.ENDIANESS, None)

@pytest.fixture
def unbound_cuint64_type(addrspace):
    return cdm.CIntType('cuint64', 64, False, cdm.ENDIANESS, None)

@pytest.fixture
def cint_type(addrspace):
    return cdm.CIntType('cint', 32, True, cdm.ENDIANESS, addrspace)

@pytest.fixture
def cint16_type(addrspace):
    return cdm.CIntType('cint16', 16, True, cdm.ENDIANESS, addrspace)

@pytest.fixture
def cuint64_type(addrspace):
    return cdm.CIntType('cuint64', 64, False, cdm.ENDIANESS, addrspace)

@pytest.fixture
def cfunc_type(addrspace):
    return cdm.CFuncType(addrspace=addrspace)

@pytest.fixture
def cfunc_obj(cfunc_type):
    return cfunc_type(lambda:None)
