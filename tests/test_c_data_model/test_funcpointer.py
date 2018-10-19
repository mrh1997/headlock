import pytest
import ctypes as ct

import headlock.c_data_model as cdm



class TestCFuncPointerType:

    def test_init_setsCTypesTypeToCFuncPointer(self, cfunc_type):
        cfuncptr_type = cdm.CFuncPointerType(cfunc_type)
        assert cfuncptr_type.base_type == cfunc_type
        assert cfuncptr_type.ctypes_type == cfunc_type.ctypes_type

    def test_sizeof_onFuncPtr_returnsMachineWordSize(self, cfunc_type):
        cfunc_obj = cfunc_type.ptr
        assert cfunc_obj.sizeof == ct.sizeof(ct.POINTER(ct.c_int))

    def test_getPtr_returnsCPointer(self, cfunc_type):
        cfuncptr_type = cfunc_type.ptr
        cfuncptrptr_type = cfuncptr_type.ptr
        assert isinstance(cfuncptrptr_type, cdm.CPointerType)

    def test_cDefinition_withFuncName_returnsFuncNameWithStarInBrackets(self):
        func_ptr = cdm.CFuncType().ptr
        assert func_ptr.c_definition('f') == 'void (*f)(void)'

    def test_cDefinition_withoutFuncName_returnsOnlyStar(self):
        func_ptr = cdm.CFuncType().ptr
        assert func_ptr.c_definition() == 'void (*)(void)'


class TestCFuncPointer:

    def test_init_fromPyCallable_returnPyCallbackFuncPtrAndAddsRefToIt(self, cfunc_type):
        callback_was_called = False
        def py_callback():
            nonlocal callback_was_called
            callback_was_called = True
        cfuncptr_obj = cfunc_type.ptr(py_callback)
        del py_callback
        cfuncptr_obj.ref.ctypes_obj()
        assert callback_was_called

    def test_create_fromPyCallable_setsDependsOn(self):
        cfuncptr_type = cdm.CFuncType().ptr
        cfuncptr_obj = cfuncptr_type(lambda:None)
        assert cfuncptr_obj._depends_on_.language == 'PYTHON'

    def test_ref_onCFuncPtr_returnsObjOfTypeCFunc(self, cfunc_obj):
        cfuncptr_obj = cfunc_obj.adr
        assert isinstance(cfuncptr_obj.ref, cdm.CFunc)

    def test_call_onCCode_runsCCode(self, abs_cfunc_obj):
        cfuncptr_obj = abs_cfunc_obj.adr
        assert cfuncptr_obj(-3) == 3

    def test_call_onPyCallback_runsPythonCode(self, cint_type):
        @cdm.CFuncType(cint_type)
        def cfunc_obj():
            return 123
        cfuncptr_obj = cfunc_obj.adr
        assert cfuncptr_obj() == 123

    def test_call_repeatedlyOnPyCallback_preservesReference(self, cfunc_type):
        def py_func(): pass
        cfuncptr_type = cfunc_type.ptr
        cfuncptr_obj = cfuncptr_type(py_func)
        for c in range(100):
            cfuncptr_obj()
