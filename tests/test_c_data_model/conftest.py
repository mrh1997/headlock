import ctypes as ct
import pytest
import sys
import headlock.c_data_model as cdm
from headlock.address_space.virtual import VirtualAddressSpace
from headlock.address_space.inprocess import InprocessAddressSpace


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
def cfunc_type():
    return cdm.CFuncType(addrspace=InprocessAddressSpace([]))

@pytest.fixture
def cfunc_obj(cfunc_type):
    return cfunc_type(lambda:None)

@pytest.fixture
def libc():
    return ct.cdll.msvcrt if sys.platform == 'win32' else ct.CDLL('libc.so.6')

@pytest.fixture
def abs_cfunc_obj(cint_type, libc, unbound_cint_type):
    addrspace = InprocessAddressSpace([libc])
    cint_type = unbound_cint_type.bind(addrspace)
    abs_cfunc_type = cdm.CFuncType(cint_type, [cint_type], addrspace=addrspace)
    return abs_cfunc_type("abs")
