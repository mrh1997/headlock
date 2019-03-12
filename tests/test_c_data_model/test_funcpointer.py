import pytest
from unittest.mock import Mock

import headlock.c_data_model as cdm



class TestCFuncPointerType:

    def test_convertToCRepr_fromPyCallable_returnsPointerToFuncAdr(self, addrspace, cfunc_type):
        callback = Mock()
        bridge_adr_buf = cfunc_type.ptr.convert_to_c_repr(callback)
        bridge_adr = int.from_bytes(bridge_adr_buf, cdm.ENDIANESS)
        addrspace.invoke_c_code(bridge_adr, cfunc_type.sig_id, 0, 0)
        callback.assert_called_once()


class TestCFuncPointer:

    def test_call_forwardsToCFunc(self, cfunc_type):
        callback = Mock()
        cfuncptr = cfunc_type.ptr(callback)
        cfuncptr()
        callback.assert_called_once()
