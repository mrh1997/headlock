import pytest
import ctypes as ct
from unittest.mock import patch, Mock

import headlock.c_data_model as cdm



class TestCFuncType:

    def test_init_setsAttributes(self, cint_type, cint16_type):
        cfunc_type = cdm.CFuncType(cint_type, [cint_type, cint16_type])
        assert cfunc_type.returns == cint_type
        assert cfunc_type.args == [cint_type, cint16_type]
        assert cfunc_type.ctypes_returns == ct.c_int
        assert cfunc_type.ctypes_args == (ct.c_int, ct.c_int16)
        assert cfunc_type.ctypes_type._restype_ == ct.c_int
        assert cfunc_type.ctypes_type._argtypes_ == (ct.c_int, ct.c_int16)

    def test_eq_onSameFunc_returnsTrue(self, cint_type):
        assert cdm.CFuncType(cint_type, [cint_type]) \
               == cdm.CFuncType(cint_type, [cint_type])

    def test_eq_onBothReturnNone_returnsTrue(self):
        assert cdm.CFuncType(None, []) == cdm.CFuncType(None, [])

    def test_eq_onDifferentRetVal_returnsFalse(self, cint_type, cint16_type):
        assert cdm.CFuncType(cint_type, [cint_type]) \
               != cdm.CFuncType(cint16_type, [cint_type])

    def test_eq_onNoneRetVal_returnsFalse(self, cint_type):
        retnone_cfunc_type = cdm.CFuncType(None, [cint_type])
        retint_cfunc_type = cdm.CFuncType(cint_type, [cint_type])
        assert retnone_cfunc_type != retint_cfunc_type
        assert retint_cfunc_type != retnone_cfunc_type

    def test_eq_onDifferentArgs_returnsFalse(self, cint_type, cint16_type):
        assert cdm.CFuncType(cint_type, [cint_type]) \
               != cdm.CFuncType(cint16_type, [cint_type, cint_type])

    def test_sizeof_raisesTypeError(self, cfunc_type):
        with pytest.raises(TypeError):
            _ = cfunc_type.sizeof()

    def test_nullValue_raisesTypeError(self, cfunc_type):
        with pytest.raises(TypeError):
            _ = cfunc_type.null_val

    def test_cDefinition_onNoneRetValAndEmptyParams_returnsVoidFunc(self):
        void_cfunc_type = cdm.CFuncType(None, [])
        assert void_cfunc_type.c_definition('voidfunc') == 'void voidfunc(void)'

    def test_cDefinition_onNoReferringDefParam_raiseTypeError(self):
        cfunc_type = cdm.CFuncType(None, [])
        with pytest.raises(TypeError):
            _ = cfunc_type.c_definition()

    def test_cDefinition_onParamsAndReturnVal_ok(self, cint_type, cint16_type):
        cfunc_type = cdm.CFuncType(cint_type,
                                   [cint_type, cint16_type])
        assert cfunc_type.c_definition('func_name') == \
               'typename func_name(typename p0, i16 p1)'

    def test_cDefintition_onAttr_ok(self):
        cdecl_cfunc_type = cdm.CFuncType().with_attr('__cdecl')
        assert cdecl_cfunc_type.c_definition('f') \
               == 'void __cdecl f(void)'

    def test_shallowIterSubTypes_onBasicFunc_returnsNothing(self):
        test_func = cdm.CFuncType()
        assert list(test_func.shallow_iter_subtypes()) == []

    def test_shallowIterSubTypes_onReturnValue_yieldsReturnType(self, cint_type):
        test_func = cdm.CFuncType(cint_type)
        assert list(test_func.shallow_iter_subtypes()) == [cint_type]

    def test_shallowIterSubTypes_onNonParams_returnsParamTypes(self, cint_type, cint16_type):
        test_func = cdm.CFuncType(None, [cint_type, cint16_type])
        assert list(test_func.shallow_iter_subtypes()) \
               == [cint_type, cint16_type]

    @patch.object(cdm, 'CFuncPointerType')
    def test_getPtr_createsNewCFuncPtrType(self, CFuncPointerType, cfunc_type):
        cfuncptr_type = cfunc_type.ptr
        assert cfuncptr_type == CFuncPointerType.return_value
        CFuncPointerType.assert_called_with(cfunc_type)

    def test_repr_ok(self, cint_type, cint16_type):
        cint1_type = cdm.CIntType('int1', 8, True, ct.c_char)
        cint2_type = cdm.CIntType('int2',16, True, ct.c_short)
        cfunc_type = cdm.CFuncType(cint1_type, [cint1_type, cint2_type])
        assert repr(cfunc_type) == 'CFuncType(ts.int1, [ts.int1, ts.int2])'

    def test_repr_withAttr_addsAttrCall(self):
        cfunc_type = cdm.CFuncType().with_attr('attrB').with_attr('attrA')
        assert repr(cfunc_type) \
               == "CFuncType(None, []).with_attr('attrA').with_attr('attrB')"

    @patch.object(cdm.CFuncType, 'CPROXY_CLASS')
    def test_call_withLoggerKeyword_passesLoggerToCFunc(self, CPROXY_CLASS):
        cfunc_type = cdm.CFuncType()
        logger = Mock()
        func = Mock()
        cfunc_obj = cfunc_type(func, logger=logger)
        assert cfunc_obj is CPROXY_CLASS.return_value
        CPROXY_CLASS.assert_called_with(cfunc_type, func, None, logger=logger)


class TestCFunc:

    def test_init_fromPyCallable_ok(self, cfunc_type):
        py_callable = Mock()
        cfunc_obj = cfunc_type(py_callable)
        assert cfunc_obj.pyfunc == py_callable
        assert cfunc_obj.language == 'PYTHON'
        py_callable.assert_not_called()
        cfunc_obj.ctypes_obj()
        py_callable.assert_called()

    def test_init_withLogger_createsWrappedFuncThatWritesToLogger(self, cfunc_type):
        logger = Mock()
        cfunc_obj = cfunc_type(Mock(), logger=logger)
        assert cfunc_obj.logger is logger
        logger.write.assert_not_called()
        cfunc_obj.ctypes_obj()
        logger.write.assert_called()

    def test_init_fromCtypesObj_ok(self, abs_cfunc_obj, libc):
        assert abs_cfunc_obj.pyfunc is None
        assert abs_cfunc_obj.ctypes_obj is libc.abs
        assert abs_cfunc_obj.language == 'C'

    def test_init_fromNoParam_raisesValueError(self, cfunc_type):
        with pytest.raises(ValueError):
            cfunc_type()

    def test_getVal_raisesValueError(self, cfunc_obj):
        with pytest.raises(TypeError):
            _ = cfunc_obj.val

    def test_setVal_raisesAttributeError(self, cfunc_obj):
        with pytest.raises(TypeError):
            cfunc_obj.val = 0

    def test_getName_onPyCallback_returnsNameOfPyFuncObj(self, cfunc_type):
        @cfunc_type
        def py_cfunc_obj(*args):
            pass
        assert py_cfunc_obj.name == 'py_cfunc_obj'

    def test_getName_onCFunc_returnsNameOfCFunc(self, abs_cfunc_obj):
        assert abs_cfunc_obj.name == 'abs'

    def test_getName_onCFuncWithoutName_returnsNone(self, cfunc_type, cfunc_obj):
        unknownname_cfunc_obj = cfunc_type(cfunc_obj.ctypes_obj)
        assert unknownname_cfunc_obj.name is None

    def test_call_onPyCallable_callsPyCallable(self, cfunc_type):
        py_callable = Mock()
        cfunc_obj = cfunc_type(py_callable)
        cfunc_obj()
        py_callable.assert_called_once()

    def test_call_onCProxys_ok(self, cint_type, cint16_type):
        @cdm.CFuncType(None, [cint_type, cint16_type])
        def cfunc_obj(*args):
            assert args == (12, 34)
        cfunc_obj(cint_type(12), cint16_type(34))

    def test_call_onPyObjs_convertsArgsToCProxy(self, cint_type, cint16_type):
        @cdm.CFuncType(None, [cint_type, cint16_type])
        def cfunc_obj(p1, p2):
            assert p1.ctype.bits == 32 and p2.ctype.bits == 16
            assert p1.val == 12 and  p2.val == 34
        cfunc_obj(12, 34)

    def test_call_onResult_returnsCProxy(self, cint_type):
        @cdm.CFuncType(cint_type)
        def cfunc_obj():
            return 123
        assert cfunc_obj().val == 123

    @pytest.mark.parametrize('wrong_param_count', [[], [1, 2]])
    def test_call_onWrongParamCount_raisesTypeError(self, cint_type, wrong_param_count):
        @cdm.CFuncType(None, [cint_type])
        def cfunc_obj(param):
            pass
        with pytest.raises(TypeError):
            cfunc_obj(*wrong_param_count)

    def test_call_onInvalidReturnValueType_raisesValueError(self, cint_type):
        @cdm.CFuncType(cint_type)
        def cfunc_obj(*args):
            return "test"
        with pytest.raises(ValueError):
            cfunc_obj()

    def test_call_onReturnTypeVoid_returnsNone(self):
        @cdm.CFuncType(None)
        def void_cfunc_obj():
            pass
        assert void_cfunc_obj() is None

    def test_call_onRaisesException_forwardsException(self):
        @cdm.CFuncType()
        def raise_cfunc_obj():
            raise NotImplementedError()
        with pytest.raises(NotImplementedError):
            raise_cfunc_obj()

    def test_call_onCFunc_returnsOk(self, abs_cfunc_obj):
        assert abs_cfunc_obj(-9).val == 9

    def test_repr_onNameSpecified_returnsName(self, cfunc_type):
        def py_callable(*args): return 0
        cfunc_obj = cfunc_type(py_callable, 'othername')
        assert repr(cfunc_obj) == "<CFunc of Python Callable 'othername'>"

    def test_repr_onPyCallbackWithName_returnsNameOfCallback(self, cfunc_type):
        def py_callable(*args): return 0
        cfunc_obj = cfunc_type(py_callable)
        assert repr(cfunc_obj) == "<CFunc of Python Callable 'py_callable'>"

    def test_repr_onCFunc_returnsNameOfCFunc(self, abs_cfunc_obj):
        assert repr(abs_cfunc_obj) == "<CFunc of C Function 'abs'>"

    @patch.object(cdm, 'CFuncPointerType')
    def test_getAdr_onPyCallback_createsCFuncPointer(self, CFuncPointerType, cfunc_obj):
        cfuncptr_type = CFuncPointerType.return_value
        cfuncptr_obj = cfunc_obj.adr
        assert cfuncptr_obj == cfuncptr_type.return_value
        ptr_size_int = ct.c_uint64 if ct.sizeof(ct.c_void_p)==8 else ct.c_uint32
        ctypes_ptr = ct.cast(ct.pointer(cfunc_obj.ctypes_obj),
                             ct.POINTER(ptr_size_int))
        cfuncptr_type.assert_called_with(ctypes_ptr.contents.value,
                                         _depends_on_=cfunc_obj)

    @patch.object(cdm, 'CFuncPointerType')
    def test_getAdr_onCFunc_returnsCFuncPointer(self, CFuncPointerType, abs_cfunc_obj):
        cfuncptr_type = CFuncPointerType.return_value
        cfuncptr_obj = abs_cfunc_obj.adr
        assert cfuncptr_obj == cfuncptr_type.return_value
        ptr_size_int = ct.c_uint64 if ct.sizeof(ct.c_void_p)==8 else ct.c_uint32
        ctypes_ptr = ct.cast(ct.pointer(abs_cfunc_obj.ctypes_obj),
                             ct.POINTER(ptr_size_int))
        cfuncptr_type.assert_called_with(ctypes_ptr.contents.value,
                                         _depends_on_=abs_cfunc_obj)
