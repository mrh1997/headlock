import pytest
import ctypes as ct
from unittest.mock import patch, Mock
import gc

import headlock.c_data_model as cdm
from headlock.address_space.inprocess import InprocessAddressSpace, \
    MACHINE_WORDSIZE, ENDIANESS
from headlock.c_data_model.function import map_to_ct


@pytest.fixture
def inproc_addrspace():
    return InprocessAddressSpace([])


@pytest.fixture
def inproc_cint_type(unbound_cint_type, inproc_addrspace):
    return unbound_cint_type.bind(inproc_addrspace)


class TestMapCTypeToCtType:

    def test_int_ok(self):
        uint8_t = cdm.CIntType('i', 8, False, ENDIANESS)
        assert map_to_ct(uint8_t) == ct.c_uint8
        int64_t = cdm.CIntType('i', 64, True, ENDIANESS)
        assert map_to_ct(int64_t) == ct.c_int64

    def test_pointer_returnsCtVoidP(self, unbound_cint16_type):
        int16_ptr = cdm.CPointerType(unbound_cint16_type,
                                     MACHINE_WORDSIZE, ENDIANESS)
        assert map_to_ct(int16_ptr) == ct.c_void_p

    def test_voidPtr_ok(self):
        cvoidptr = cdm.CVoidType().ptr
        assert map_to_ct(cvoidptr) == ct.c_void_p
    
    def test_func_onSimpleCase_ok(self, cfunc_type):
        assert map_to_ct(cfunc_type) == ct.CFUNCTYPE(None)

    def test_func_onReturnValAndParams_ok(self):
        uint8_t = cdm.CIntType('i', 8, False, ENDIANESS)
        uint16_t = cdm.CIntType('i', 16, False, ENDIANESS)
        cfunc_type = cdm.CFuncType(uint8_t, [uint16_t, uint8_t])
        assert map_to_ct(cfunc_type) == ct.CFUNCTYPE(ct.c_uint8,
                                                     ct.c_uint16, ct.c_uint8)

    def test_funcPtr_ok(self):
        cfuncptr_type = cdm.CFuncType().ptr
        assert map_to_ct(cfuncptr_type) == ct.CFUNCTYPE(None)

    def test_array_ok(self, unbound_cint16_type):
        int16_array = cdm.CArrayType(unbound_cint16_type, 123)
        assert map_to_ct(int16_array) == ct.c_int16 * 123

    def test_struct_ok(self, unbound_cint16_type, unbound_cint_type):
        cstruct_type = cdm.CStructType('name_of_strct',
                                       [('member1', unbound_cint_type),
                                        ('member2', unbound_cint16_type)],
                                       2)
        ct_struct = map_to_ct(cstruct_type)
        assert ct_struct.__name__ == 'name_of_strct'
        assert ct_struct._fields_ == [('member1', ct.c_int),
                                      ('member2', ct.c_int16)]
        assert ct_struct._pack_ == 2

    def test_struct_onCallTwiceOnSameStruct_returnCachedType(self, unbound_cint_type):
        cstruct_type = cdm.CStructType('s', [('m', unbound_cint_type)])
        assert map_to_ct(cstruct_type) is map_to_ct(cstruct_type)

    def test_struct_onRecursiveStruct_ok(self):
        cstruct_type = cdm.CStructType('s')
        cstructptr_type = cdm.CPointerType(cstruct_type,
                                           MACHINE_WORDSIZE, ENDIANESS)
        cstruct_type.delayed_def([('member', cstructptr_type)])
        ct_struct = map_to_ct(cstruct_type)
        print(repr(ct_struct._fields_[0][1]))
        assert ct_struct._fields_[0][1] == ct.c_void_p


class TestCFuncType:

    def test_init_setsAttributes(self, unbound_cint_type, unbound_cint16_type):
        cfunc_type = cdm.CFuncType(unbound_cint_type,
                                   [unbound_cint_type, unbound_cint16_type])
        assert cfunc_type.returns == unbound_cint_type
        assert cfunc_type.args == [unbound_cint_type, unbound_cint16_type]

    def test_init_onReturnTypeHasDifferentAddrSpace_raiseInvalidAddrSpaceError(self, cint_type):
        with pytest.raises(cdm.InvalidAddressSpaceError):
            _ = cdm.CFuncType(cint_type)

    def test_init_onParameterTypeHasDifferentAddrSpace_raiseInvalidAddrSpaceError(self, cint_type):
        with pytest.raises(cdm.InvalidAddressSpaceError):
            _ = cdm.CFuncType(None, [cint_type])

    def test_bind_bindsReturnTypeAndParameterTypes(self, unbound_cint_type, unbound_cint16_type, addrspace):
        cfunc_type = cdm.CFuncType(unbound_cint_type, [unbound_cint16_type])
        bound_cfunc_type = cfunc_type.bind(addrspace)
        assert bound_cfunc_type.returns.__addrspace__ is addrspace
        assert all(arg.__addrspace__ == addrspace
                   for arg in bound_cfunc_type.args)

    def test_eq_onSameFunc_returnsTrue(self, unbound_cint_type):
        assert cdm.CFuncType(unbound_cint_type, [unbound_cint_type]) \
               == cdm.CFuncType(unbound_cint_type, [unbound_cint_type])

    def test_eq_onBothReturnNone_returnsTrue(self):
        assert cdm.CFuncType(None, []) == cdm.CFuncType(None, [])

    def test_eq_onDifferentRetVal_returnsFalse(self, unbound_cint_type, unbound_cint16_type):
        assert cdm.CFuncType(unbound_cint_type, [unbound_cint_type]) \
               != cdm.CFuncType(unbound_cint16_type, [unbound_cint_type])

    def test_eq_onNoneRetVal_returnsFalse(self, unbound_cint_type):
        retnone_cfunc_type = cdm.CFuncType(None, [unbound_cint_type])
        retint_cfunc_type = cdm.CFuncType(unbound_cint_type,[unbound_cint_type])
        assert retnone_cfunc_type != retint_cfunc_type
        assert retint_cfunc_type != retnone_cfunc_type

    def test_eq_onDifferentArgs_returnsFalse(self, unbound_cint_type, unbound_cint16_type):
        assert cdm.CFuncType(unbound_cint_type, [unbound_cint_type]) \
               != cdm.CFuncType(unbound_cint16_type,
                                [unbound_cint_type, unbound_cint_type])

    def test_sizeof_raisesTypeError(self):
        cfunc_type = cdm.CFuncType()
        with pytest.raises(TypeError):
            _ = cfunc_type.sizeof()

    def test_nullValue_raisesTypeError(self):
        cfunc_type = cdm.CFuncType()
        with pytest.raises(TypeError):
            _ = cfunc_type.null_val

    def test_cDefinition_onNoneRetValAndEmptyParams_returnsVoidFunc(self):
        void_cfunc_type = cdm.CFuncType(None, [])
        assert void_cfunc_type.c_definition('voidfunc') == 'void voidfunc(void)'

    def test_cDefinition_onNoReferringDefParam_raiseTypeError(self):
        cfunc_type = cdm.CFuncType(None, [])
        with pytest.raises(TypeError):
            _ = cfunc_type.c_definition()

    def test_cDefinition_onParamsAndReturnVal_ok(self, unbound_cint_type, unbound_cint16_type):
        cfunc_type = cdm.CFuncType(unbound_cint_type,
                                   [unbound_cint_type, unbound_cint16_type])
        assert cfunc_type.c_definition('func_name') == \
               'cint func_name(cint p0, cint16 p1)'

    def test_cDefintition_onAttr_ok(self):
        cdecl_cfunc_type = cdm.CFuncType().with_attr('__cdecl')
        assert cdecl_cfunc_type.c_definition('f') \
               == 'void __cdecl f(void)'

    def test_shallowIterSubTypes_onBasicFunc_returnsNothing(self):
        test_func = cdm.CFuncType()
        assert list(test_func.shallow_iter_subtypes()) == []

    def test_shallowIterSubTypes_onReturnValue_yieldsReturnType(self, unbound_cint_type):
        test_func = cdm.CFuncType(unbound_cint_type)
        assert list(test_func.shallow_iter_subtypes()) == [unbound_cint_type]

    def test_shallowIterSubTypes_onNonParams_returnsParamTypes(self, unbound_cint_type, unbound_cint16_type):
        test_func = cdm.CFuncType(None, [unbound_cint_type,unbound_cint16_type])
        assert list(test_func.shallow_iter_subtypes()) \
               == [unbound_cint_type, unbound_cint16_type]

    @patch.object(cdm, 'CFuncPointerType')
    def test_getPtr_createsNewCFuncPtrType(self, CFuncPointerType, addrspace):
        cfunc_type = cdm.CFuncType(addrspace=addrspace)
        cfuncptr_type = cfunc_type.ptr
        assert cfuncptr_type == CFuncPointerType.return_value
        CFuncPointerType.assert_called_with(
            cfunc_type, MACHINE_WORDSIZE, ENDIANESS, addrspace)

    def test_repr_ok(self, unbound_cint_type, unbound_cint16_type):
        cfunc_type = cdm.CFuncType(unbound_cint_type, [unbound_cint_type, unbound_cint16_type])
        assert repr(cfunc_type) == 'CFuncType(ts.cint, [ts.cint, ts.cint16])'

    def test_repr_withAttr_addsAttrCall(self):
        cfunc_type = cdm.CFuncType().with_attr('attrB').with_attr('attrA')
        assert repr(cfunc_type) \
               == "CFuncType(None, []).with_attr('attrA').with_attr('attrB')"

    def test_call_withoutAddressSpace_raisesInvalidAddressSpaceError(self):
        cfunc_type = cdm.CFuncType()
        with pytest.raises(cdm.InvalidAddressSpaceError):
            cfunc_type(0)

    @patch.object(cdm.CFuncType, 'CPROXY_CLASS')
    def test_call_onInt_callsConstructorWithFuncAdrOnly(self, CPROXY_CLASS, inproc_addrspace):
        cfunc_type = cdm.CFuncType(addrspace=inproc_addrspace)
        assert cfunc_type(123) is CPROXY_CLASS.return_value
        CPROXY_CLASS.assert_called_once_with(cfunc_type, 123)

    @patch.object(cdm.CFuncType, 'CPROXY_CLASS')
    def test_call_onStr_retrievesAdrOfSymbolAndPassesItToContructor(self, CPROXY_CLASS):
        inproc_addrspace.get_symbol_adr = Mock(return_value=678)
        cfunc_type = cdm.CFuncType(addrspace=inproc_addrspace)
        assert cfunc_type('funcname') is CPROXY_CLASS.return_value
        inproc_addrspace.get_symbol_adr.assert_called_once_with('funcname')
        CPROXY_CLASS.assert_called_once_with(cfunc_type, 678)

    @patch.object(cdm.CFuncType, 'CPROXY_CLASS')
    def test_call_onCallable_bridgesCallable(self, CPROXY_CLASS, inproc_cint_type, inproc_addrspace):
        cfunc_type = cdm.CFuncType(inproc_cint_type,
                                   [inproc_cint_type], inproc_addrspace)
        callback = Mock(return_value=123)
        assert cfunc_type(callback) is CPROXY_CLASS.return_value
        ct_func_type = ct.CFUNCTYPE(ct.c_int, ct.c_int)
        bridge_adr = CPROXY_CLASS.call_args[0][1]
        ct_func_obj = ct_func_type(bridge_adr)
        assert ct_func_obj(456) == 123
        callback.assert_called_once_with(456)
        assert isinstance(callback.call_args[0][0], cdm.CInt)

    @patch.object(cdm.CFuncType, 'CPROXY_CLASS')
    def test_call_onCallable_ensuresBridgeIsReferencedPermanently(self, CPROXY_CLASS, inproc_cint_type, inproc_addrspace):
        cfunc_type = cdm.CFuncType(inproc_cint_type, [], inproc_addrspace)
        cfunc_type(Mock(return_value=123))
        gc.collect()
        ct_func_type = ct.CFUNCTYPE(ct.c_int)
        bridge_adr = CPROXY_CLASS.call_args[0][1]
        ct_func_obj = ct_func_type(bridge_adr)
        assert ct_func_obj() == 123

    @patch.object(cdm.CFuncType, 'CPROXY_CLASS')
    def test_call_onCFunc_returnsNewCFunc(self, CPROXY_CLASS, inproc_cint_type, inproc_addrspace):
        cfunc_type = cdm.CFuncType(None, addrspace=inproc_addrspace)
        cfunc_type2 = cdm.CFuncType(inproc_cint_type, [], inproc_addrspace)
        cfunc_obj = cdm.CFunc(cfunc_type, 123)
        cfunc_type2(cfunc_obj)
        CPROXY_CLASS.assert_called_once_with(cfunc_type2, 123)


class TestCFunc:

    def test_getVal_returnsFuncAddress(self, cfunc_type):
        cfunc_obj = cdm.CFunc(cfunc_type, 123)
        assert cfunc_obj.val == 123

    def test_setVal_raisesException(self, cfunc_type):
        cfunc_obj = cdm.CFunc(cfunc_type, 0)
        with pytest.raises(AttributeError):
            cfunc_obj.val = 123

    def test_getName_onPyCallback_returnsNameOfPyFuncObj(self, cfunc_type):
        @cfunc_type
        def py_cfunc_obj(*args):
            pass
        assert py_cfunc_obj.name == 'py_cfunc_obj'

    def test_getName_onCFunc_returnsNameOfCFunc(self, abs_cfunc_obj):
        assert abs_cfunc_obj.name == 'abs'

    def test_getName_onCFuncWithoutName_returnsNone(self, cfunc_type, cfunc_obj):
        unknown_adr_cfunc_obj = cfunc_type(1234)
        assert unknown_adr_cfunc_obj.name is None

    def test_call_onPyCallable_callsPyCallable(self, cfunc_type):
        py_callable = Mock()
        cfunc_obj = cfunc_type(py_callable)
        cfunc_obj()
        py_callable.assert_called_once()

    def test_call_onArgs_passesArgs(self, inproc_cint_type, unbound_cint16_type, inproc_addrspace):
        cint16_type = unbound_cint16_type.bind(inproc_addrspace)
        cfunc_type = cdm.CFuncType(None, [inproc_cint_type, cint16_type],
                                   inproc_addrspace)
        callback = Mock()
        cfunc_obj = cfunc_type(callback)
        cfunc_obj(inproc_cint_type(12), 34)
        callback.assert_called_with(12, 34)
        assert callback.call_args[0][0].ctype == inproc_cint_type
        assert callback.call_args[0][1].ctype == cint16_type

    def test_call_onCallableWhichRaisesException_forwardsException(self, inproc_addrspace):
        cfunc_type = cdm.CFuncType(None, [], inproc_addrspace)
        callback = Mock(side_effect=ValueError('some exception text'))
        cfunc_obj = cfunc_type(callback)
        with pytest.raises(ValueError) as e:
            cfunc_obj()
        assert str(e.value) == 'some exception text'

    def test_call_onSimpleResult_returnsCProxy(self, inproc_cint_type, inproc_addrspace):
        @cdm.CFuncType(inproc_cint_type, addrspace=inproc_addrspace)
        def cfunc_obj():
            return 123
        result = cfunc_obj()
        assert isinstance(result, cdm.CInt)
        assert result == 123

    @pytest.mark.parametrize('wrong_param_count', [[], [1, 2]])
    def test_call_onWrongParamCount_raisesTypeError(self, inproc_cint_type, wrong_param_count, inproc_addrspace):
        @cdm.CFuncType(None, [inproc_cint_type], inproc_addrspace)
        def cfunc_obj(param):
            pass
        with pytest.raises(TypeError):
            cfunc_obj(*wrong_param_count)

    def test_call_onInvalidReturnValueType_raisesValueError(self, inproc_cint_type, inproc_addrspace):
        @cdm.CFuncType(inproc_cint_type, addrspace=inproc_addrspace)
        def cfunc_obj(*args):
            return 4.4
        with pytest.raises(TypeError):
            cfunc_obj()

    def test_call_onReturnTypeVoid_returnsNone(self, inproc_addrspace):
        @cdm.CFuncType(None, addrspace=inproc_addrspace)
        def void_cfunc_obj():
            pass
        assert void_cfunc_obj() is None

    def test_call_onRaisesException_forwardsException(self, inproc_addrspace):
        @cdm.CFuncType(addrspace=inproc_addrspace)
        def raise_cfunc_obj():
            raise NotImplementedError()
        with pytest.raises(NotImplementedError):
            raise_cfunc_obj()

    def test_call_onCFunc_returnsOk(self, abs_cfunc_obj):
        assert abs_cfunc_obj(-9).val == 9

    def test_repr_onPyCallbackWithName_returnsNameOfCallback(self, cfunc_type):
        def py_callable(*args): return 0
        cfunc_obj = cfunc_type(py_callable)
        assert repr(cfunc_obj) == "<CFunc of 'py_callable'>"

    def test_repr_onCFunc_returnsNameOfCFunc(self, abs_cfunc_obj):
        assert repr(abs_cfunc_obj) == "<CFunc of 'abs'>"

    @patch.object(cdm, 'CFuncPointerType')
    def test_getAdr_onPyCallback_createsCFuncPointer(self, CFuncPointerType, cfunc_obj):
        cfunc_type = CFuncPointerType.return_value
        assert cfunc_obj.adr is cfunc_type.return_value
        cfunc_type.assert_called_with(cfunc_obj.__address__)
