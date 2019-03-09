import pytest
from unittest.mock import Mock, patch
import ctypes as ct

import headlock.c_data_model as cdm



class TestCFuncPointerType:

    @pytest.mark.skip
    def test_init_onNonFuncType_raisesTypeError(self, cint_type):
        with pytest.raises(TypeError):
            cdm.CFuncPointerType(cint_type, 16, 'big')

    def test_convertToCRepr_fromPyCallable_returnsPointerToFuncAdr(self, cfunc_type):
        callback = Mock()
        bridge_adr = cfunc_type.ptr.convert_to_c_repr(callback)
        ct_func_type = ct.CFUNCTYPE(ct.c_int)
        ct_func_obj = ct_func_type(int.from_bytes(bridge_adr, cdm.ENDIANESS))
        ct_func_obj()
        callback.assert_called_once()


class TestCFuncPointer:

    def test_call_forwardsToCFunc(self, cfunc_type):
        callback = Mock()
        cfuncptr = cfunc_type.ptr(callback)
        cfuncptr()
        callback.assert_called_once()
