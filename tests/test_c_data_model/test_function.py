import pytest
from unittest.mock import patch, Mock

import headlock.c_data_model as cdm
import headlock.c_data_model.function
from headlock.address_space.inprocess import MACHINE_WORDSIZE, ENDIANESS


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
        assert cfunc_type.c_definition() == 'void f(void)'

    def test_cDefinition_onParamsAndReturnVal_ok(self, unbound_cint_type, unbound_cint16_type):
        cfunc_type = cdm.CFuncType(unbound_cint_type,
                                   [unbound_cint_type, unbound_cint16_type])
        assert cfunc_type.c_definition('func_name') == \
               'cint func_name(cint p0, cint16 p1)'

    def test_cDefintition_onAttr_ok(self):
        cdecl_cfunc_type = cdm.CFuncType().with_attr('__cdecl')
        assert cdecl_cfunc_type.c_definition('func') \
               == 'void __cdecl func(void)'

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
    def test_call_onInt_callsConstructorWithFuncAdrOnly(self, CPROXY_CLASS, addrspace):
        cfunc_type = cdm.CFuncType(addrspace=addrspace)
        assert cfunc_type(123) is CPROXY_CLASS.return_value
        CPROXY_CLASS.assert_called_once_with(cfunc_type, 123)

    @patch.object(cdm.CFuncType, 'CPROXY_CLASS')
    def test_call_onStr_retrievesAdrOfSymbolAndPassesItToContructor(self, CPROXY_CLASS, addrspace, cfunc_type):
        func_adr = addrspace.simulate_symbol('funcname', Mock())
        assert cfunc_type('funcname') is CPROXY_CLASS.return_value
        CPROXY_CLASS.assert_called_once_with(cfunc_type, func_adr)

    @patch.object(cdm.CFuncType, 'CPROXY_CLASS')
    def test_call_onCallable_bridgesCallable(self, CPROXY_CLASS, cint_type, addrspace):
        cfunc_type = cdm.CFuncType(cint_type, [cint_type, cint_type], addrspace)
        callback = Mock(return_value=0xAABBCCDD)
        cfunc_obj = cfunc_type(callback)
        _, bridge_adr = CPROXY_CLASS.call_args[0]
        result_adr = addrspace.alloc_memory(4)
        param_adr = addrspace.alloc_memory(8)
        addrspace.write_memory(param_adr, b'\x44\x33\x22\x11\x99\x88\x77\x66')
        c_sig = 'cint f(cint p0, cint p1)'
        addrspace.invoke_c_func(bridge_adr, c_sig, param_adr, result_adr)
        assert addrspace.read_memory(result_adr, 4) == b'\xDD\xCC\xBB\xAA'
        callback.assert_called_once_with(0x11223344, 0x66778899)
        assert isinstance(callback.call_args[0][0], cdm.CInt)
        assert cfunc_obj is CPROXY_CLASS.return_value

    @patch.object(cdm.CFuncType, 'CPROXY_CLASS')
    def test_call_onCFunc_returnsNewCFunc(self, CPROXY_CLASS, cint_type, addrspace):
        cfunc_type = cdm.CFuncType(None, addrspace=addrspace)
        cfunc_type2 = cdm.CFuncType(cint_type, [], addrspace)
        cfunc_obj = cdm.CFunc(cfunc_type, 123)
        cfunc_type2(cfunc_obj)
        CPROXY_CLASS.assert_called_once_with(cfunc_type2, 123)

    def test_sigId_isCDefinitionWithReferrerF(self, cfunc_type):
        assert cfunc_type.c_sig == cfunc_type.c_definition('f')


class TestCFunc:

    def test_getVal_returnsFuncAddress(self, cfunc_type):
        cfunc_obj = cdm.CFunc(cfunc_type, 123)
        assert cfunc_obj.val == 123

    def test_setVal_raisesException(self, cfunc_type):
        cfunc_obj = cdm.CFunc(cfunc_type, 0)
        with pytest.raises(AttributeError):
            cfunc_obj.val = 123

    @pytest.mark.skip
    def test_getName_onPyCallback_returnsNameOfPyFuncObj(self, cfunc_type):
        @cfunc_type
        def py_cfunc_obj(*args):
            pass
        assert py_cfunc_obj.name == 'py_cfunc_obj'

    def test_getName_onCFunc_returnsNameOfCFunc(self, cfunc_type, addrspace):
        addrspace.simulate_symbol('funcname', Mock())
        cfunc_obj = cfunc_type('funcname')
        assert cfunc_obj.name == 'funcname'

    def test_getName_onCCodeWithoutName_returnsNone(self, cfunc_type, cfunc_obj):
        unknown_adr_cfunc_obj = cfunc_type(1234)
        assert unknown_adr_cfunc_obj.name is None

    def test_call_onCCode_runsAddrSpaceInvokeCCode(self, cint_type, addrspace):
        addrspace.simulate_c_code('funcname', 'cint f(void)',
                                  retval=b'\x44\x33\x22\x11')
        func_type = cdm.CFuncType(cint_type, [], addrspace)
        func_obj = func_type('funcname')
        assert func_obj() == 0x11223344

    def test_call_onArgs_passesArgs(self, cint_type, cint16_type, addrspace):
        addrspace.simulate_c_code('func_with_params',
                                  exp_params=b'\x34\x12\x00\x00\x56\x00')
        cfunc_type = cdm.CFuncType(None, [cint_type, cint16_type], addrspace)
        cfunc_obj = cfunc_type('func_with_params')
        cfunc_obj(cint_type(0x1234), 0x56)

    def test_call_onSimpleResult_returnsCProxy(self, cint_type, addrspace):
        cfunc_type = cdm.CFuncType(cint_type, addrspace=addrspace)
        cfunc_obj = cfunc_type(Mock(return_value=123))
        result = cfunc_obj()
        assert isinstance(result, cdm.CInt)
        assert result == 123

    def test_call_onPyCallable_callsPyCallable(self, cfunc_type):
        py_callable = Mock()
        cfunc_obj = cfunc_type(py_callable)
        cfunc_obj2 = cfunc_type(cfunc_obj.__address__)
        cfunc_obj2()
        py_callable.assert_called_once()

    def test_call_onCallableWhichRaisesException_forwardsException(self, cfunc_type, addrspace):
        callback = Mock(side_effect=ValueError('some exception text'))
        cfunc_obj = cfunc_type(callback)
        with pytest.raises(ValueError) as e:
            cfunc_obj()
        assert str(e.value) == 'some exception text'

    @pytest.mark.parametrize('wrong_param_count', [[], [1, 2]])
    def test_call_onWrongParamCount_raisesTypeError(self, cint_type, wrong_param_count, addrspace):
        @cdm.CFuncType(None, [cint_type], addrspace)
        def cfunc_obj(param):
            pass
        with pytest.raises(TypeError):
            cfunc_obj(*wrong_param_count)

    def test_call_onInvalidReturnValueType_raisesValueError(self, cint_type, addrspace):
        cfunc_type = cdm.CFuncType(cint_type, addrspace=addrspace)
        cfunc_obj = cfunc_type(Mock(return_value=4.4))
        with pytest.raises(TypeError):
            cfunc_obj()

    def test_call_onReturnTypeVoid_returnsNone(self, addrspace):
        void_cfunc_type = cdm.CFuncType(None, addrspace=addrspace)
        void_cfunc_obj = void_cfunc_type(Mock())
        assert void_cfunc_obj() is None

    @pytest.mark.skip
    def test_repr_onPyCallbackWithName_returnsNameOfCallback(self, cfunc_type):
        def py_callable(*args): return 0
        cfunc_obj = cfunc_type(py_callable)
        assert repr(cfunc_obj) == "<CFunc of 'py_callable'>"

    def test_repr_onCFunc_returnsNameOfCFunc(self, addrspace, cfunc_type):
        addrspace.simulate_c_code('some_funcname')
        cfunc_obj = cfunc_type('some_funcname')
        assert repr(cfunc_obj) == "<CFunc of 'some_funcname'>"
