import pytest
from unittest.mock import patch, Mock, MagicMock, ANY

import headlock.c_data_model as cdm
import headlock.c_data_model.core as core



class CMyType(cdm.PtrArrFactoryMixIn, cdm.CProxyType): pass

@pytest.fixture
def ctype():
    return CMyType(1)


class TestCProxyType:

    def test_withAttr_createsDerivedTypeWithSameMembersPlusAttrSet(self, ctype):
        ctype.derived_member = 123
        attr_ctype = ctype.with_attr('attr')
        assert attr_ctype.__c_attribs__ == {'attr'}
        assert attr_ctype.derived_member == 123

    def test_withAttr_onAttrAlreadySet_raiseTypeError(self, ctype):
        with pytest.raises(ValueError):
            ctype.with_attr('attr').with_attr('attr')

    def test_withAttr_callTwiceWithDifferentAttrs_mergesAttributes(self, ctype):
        attr_ctype = ctype.with_attr('attr1').with_attr('attr2')
        assert attr_ctype.__c_attribs__ == {'attr1', 'attr2'}

    def test_hasAttr_onAttrNotSet_returnsFalse(self, ctype):
        assert not ctype.has_attr('attr')

    def test_hasAttr_onAttrSet_returnsTrue(self, ctype):
        attr_test_int32_type = ctype.with_attr('attr')
        assert attr_test_int32_type.has_attr('attr')

    def test_bind_createsShallowCopyWithAddrSpace(self, ctype):
        addrspace = Mock()
        bound_ctype = ctype.bind(addrspace)
        assert ctype.__addrspace__ is None
        assert bound_ctype.__addrspace__ is not None

    def test_bind_onAlreadyBoundObj_raisesValueError(self, ctype):
        bound_ctype = ctype.bind(Mock())
        with pytest.raises(ValueError):
            bound_ctype.bind(Mock())

    def test_bind_onSameAddressSpace_returnsIdenticalObject(self, ctype, addrspace):
        bound_ctype = ctype.bind(addrspace)
        assert bound_ctype.bind(addrspace) is bound_ctype

    def test_descriptor_onContainingObject_bindsToParentsAddressSpaceAttribute(self, ctype):
        ctype.bind = Mock()
        class Dummy:
            attr = ctype
        dummy_obj = Dummy()
        dummy_obj.__addrspace__ = Mock()
        assert dummy_obj.attr is ctype.bind.return_value
        ctype.bind.assert_called_once_with(dummy_obj.__addrspace__)

    def test_descriptor_onContainingClass_returnsSelf(self, ctype):
        class Dummy:
            attr = ctype
        assert Dummy.attr is ctype

    def test_createCProxyFor_instaniatesCProxyClass(self):
        class CDummyType(cdm.CProxyType): CPROXY_CLASS = Mock()
        cdummy_type = CDummyType(size=1)
        assert cdummy_type.create_cproxy_for(1234) \
               == CDummyType.CPROXY_CLASS.return_value
        CDummyType.CPROXY_CLASS.assert_called_with(cdummy_type, 1234)


    def test_call_onUnboundObj_raisesNoAddrSpaceBoundError(self, ctype):
        ctype.CPROXY_CLASS = Mock()
        with pytest.raises(cdm.InvalidAddressSpaceError):
            ctype(Mock())

    def test_call_createsObj(self, ctype, addrspace):
        next_alloc_addr = len(addrspace.content)
        bound_ctype = ctype.bind(addrspace)
        bound_ctype.CPROXY_CLASS = Mock()
        bound_ctype.convert_to_c_repr = Mock()
        addrspace.write_memory = Mock()
        init_val = Mock()
        cproxy = bound_ctype(init_val)
        assert cproxy is bound_ctype.CPROXY_CLASS.return_value
        bound_ctype.convert_to_c_repr.assert_called_once_with(init_val)
        addrspace.write_memory.assert_called_once_with(
            next_alloc_addr,
            bound_ctype.convert_to_c_repr.return_value)
        bound_ctype.CPROXY_CLASS.assert_called_once_with(
            bound_ctype, next_alloc_addr)

    def test_call_onConstAttr_writesInitVal(self, ctype, addrspace):
        bound_ctype = ctype.with_attr('const').bind(addrspace)
        bound_ctype.CPROXY_CLASS = Mock()
        bound_ctype.convert_to_c_repr = Mock()
        addrspace.write_memory = Mock()
        init_val = Mock()
        assert bound_ctype(init_val) is bound_ctype.CPROXY_CLASS.return_value
        addrspace.write_memory.assert_called_once()

    def derive_convert_to_c_repr(self, ctype, exp_val):
        orig_convert_to_c_repr = ctype.convert_to_c_repr
        ret_val = Mock()
        def convert_to_c_repr_mock(val):
            if val is exp_val:
                return ret_val
            else:
                return orig_convert_to_c_repr(val)
        ctype.convert_to_c_repr = convert_to_c_repr_mock
        return ret_val

    @patch.object(CMyType, 'null_val')
    def test_convertToCRepr_onNone_returnsNullVal(self, null_val, ctype):
        ret_val = self.derive_convert_to_c_repr(ctype, None)
        assert ctype.convert_to_c_repr(None) == ret_val

    def test_convertToCRepr_onCProxy_returnsValAttr(self, ctype):
        cobj = Mock(spec=cdm.CProxy)
        ret_val = self.derive_convert_to_c_repr(ctype, cobj.val)
        assert ctype.convert_to_c_repr(cobj) is ret_val

    def test_iterSubType_onNoSubTypes_yieldsSelfOnly(self, ctype):
        ctype.shallow_iter_subtypes = MagicMock()
        assert list(ctype.iter_subtypes()) == [ctype]
        ctype.shallow_iter_subtypes.assert_called_with()

    def test_iterSubType_onFlatObj_forwardsToShallowIterSubType(self, ctype):
        ctype.shallow_iter_subtypes = MagicMock()
        assert list(ctype.iter_subtypes(True)) \
               == [ctype]
        ctype.shallow_iter_subtypes.assert_called_with()

    def test_iterSubType_onRecusiveSubTypes_yieldsFlattenedSubTypes(self, ctype):
        subsubmock = MagicMock()
        submock = Mock()
        submock.iter_subtypes.return_value = iter([submock, subsubmock])
        ctype.shallow_iter_subtypes = Mock(return_value=iter([submock]))
        assert list(ctype.iter_subtypes()) \
                == [ctype, submock, subsubmock]

    def test_iterSubType_onTopLevelFirstIsTrue_reordersElements(self, ctype):
        submock1, submock2 = MagicMock(), MagicMock()
        submock1.iter_subtypes = Mock(return_value=iter([submock1]))
        submock2.iter_subtypes = Mock(return_value=iter([submock2]))
        ctype.shallow_iter_subtypes = Mock(return_value=iter([submock1,
                                                                  submock2]))
        assert list(ctype.iter_subtypes(top_level_last=True)) \
                == [submock1, submock2, ctype]
        submock1.iter_subtypes.assert_called_with(True, ANY, ANY, ANY)

    def test_iterSubType_onFilterIsSetAndFilterReturnsFalse_skipsSubType(self, ctype):
        filter_func = Mock(return_value=False)
        assert list(ctype.iter_subtypes(filter=filter_func)) == []
        filter_func.assert_called_with(ctype, None)

    def test_iterSubType_onFilterIsSetAndFilterReturnsFalse_doesNotSkipSubType(self, ctype):
        filter_func = Mock(return_value=True)
        assert list(ctype.iter_subtypes(filter=filter_func)) == [ctype]

    def test_iterSubType_onFilterIsSet_passesParentToFilterAndSubType(self, ctype):
        sub_type = MagicMock()
        ctype.shallow_iter_subtypes = Mock(return_value=[sub_type])
        filter_func = Mock(return_value=True)
        parent=Mock()
        _ = list(ctype.iter_subtypes(filter=filter_func, parent=parent))
        filter_func.assert_any_call(ctype, parent)
        sub_type.iter_subtypes.assert_called_with(ANY, filter_func, ctype,
                                                  ANY)

    def test_iter_iteratesSubTypes(self, ctype):
        assert list(iter(ctype)) == []

    def test_eq_onSameAttributes_returnsTrue(self):
        ctype1 = cdm.CProxyType(1).with_attr('a').with_attr('b')
        ctype2 = cdm.CProxyType(1).with_attr('b').with_attr('a')
        assert ctype1 == ctype2
        assert not ctype1 != ctype2

    def test_eq_onDifferentAttributes_returnsFalse(self):
        ctype1 = cdm.CProxyType(1).with_attr('a').with_attr('c')
        ctype2 = cdm.CProxyType(1).with_attr('a').with_attr('b')
        assert not ctype1 == ctype2
        assert ctype1 != ctype2

    def test_eq_onDifferentBoundObj_returnsFalse(self, ctype):
        bound_ctype = ctype.bind(Mock())
        assert bound_ctype != ctype

    def test_eq_onDifferentSizedTypes_returnsFalse(self):
        assert cdm.CProxyType(2) != cdm.CProxyType(1)

    def test_cDecorateCDef_onAttrs_returnsAttrs(self, ctype):
        attr_ctype = ctype.with_attr('volatile').with_attr('other')
        assert attr_ctype._decorate_c_definition('*') == 'other volatile *'

    @pytest.mark.parametrize('size', [1, 2])
    def test_sizeof_returnsSize(self, size):
        ctype = cdm.CProxyType(size)
        assert ctype.sizeof == size


class TestPtrArrFactory:

    @patch.object(cdm, 'CArrayType')
    def test_array_returnsArrayTypeOfGivenSize(self, CArrayType, ctype):
        array_type = ctype.array(10)
        assert array_type is CArrayType.return_value
        CArrayType.assert_called_once_with(ctype, 10, None)

    @patch.object(CMyType, 'array')
    def test_allocArray_onLength_returnsArrayInstanceOfGivenSize(self, array, ctype):
        carray_obj = ctype.alloc_array(123)
        array.assert_called_once_with(123)
        assert carray_obj is array.return_value.return_value

    @pytest.mark.parametrize('initval', [[1, 2, 3, 4], iter([1, 2, 3, 4])])
    def test_allocArray_onPyCollection_returnsArrayInstanceInitializedWithPyColl(self, initval, cint_type):
        array = cint_type.alloc_array(initval)
        assert array == [1, 2, 3, 4]

    @pytest.mark.parametrize('initval', [b'\x01\x02\x03\x04',
                                         '\x01\x02\x03\x04'])
    def test_allocArray_onPyStr_returnsArrayInstanceInitializedWithZeroTerminatedByStr(self, initval, cint_type):
        array = cint_type.alloc_array(initval)
        assert array == [1, 2, 3, 4, 0]

    @patch.object(cdm, 'CPointerType')
    def test_ptr_returnsCPointerToSelf(self, CPointerType, ctype):
        assert ctype.ptr is CPointerType.return_value
        CPointerType.assert_called_once_with(
            ctype, cdm.MACHINE_WORDSIZE, cdm.ENDIANESS, None)

    @patch.object(cdm, 'CFuncPointerType')
    def test_ptr_onFuncType_returnsCFFuncPointerToSelf(self, CFuncPointerType, cfunc_type):
        assert cfunc_type.ptr is CFuncPointerType.return_value

    @patch.object(cdm, 'CPointerType')
    def test_ptr_onCalledMoreThanOnce_returnsCachedPtrType(self, CPointerType, ctype):
        retval1 = ctype.ptr
        retval2 = ctype.ptr
        CPointerType.assert_called_once()
        assert retval1 is retval2

    def test_ptr_onAfterBind_recreatesCache(self, ctype, addrspace):
        bound_ctype = ctype.bind(addrspace)
        with patch.object(cdm, 'CPointerType') as CPointerType:
            assert bound_ctype.ptr is CPointerType.return_value
            CPointerType.assert_called_once_with(
                bound_ctype, cdm.MACHINE_WORDSIZE, cdm.ENDIANESS, addrspace)

    @patch.object(CMyType, 'alloc_array')
    @patch.object(CMyType, 'ptr')
    def test_allocPtr_onInt_createArrayObjReturnPointerToIt(self, ptr, alloc_array, ctype):
        cptr_obj = ctype.alloc_ptr(123)
        alloc_array.assert_called_once_with(123)
        ptr.assert_called_once_with(alloc_array.return_value.adr)
        assert cptr_obj == ptr.return_value

    @patch.object(cdm.CIntType, 'bind')
    def test_allocPtr_withIterableOnVoid_forwardsToIntAllocPtr(self, bind, addrspace):
        cvoid_type = cdm.CVoidType(addrspace)
        bound = bind.return_value
        assert cvoid_type.alloc_ptr([1, 2, 3]) is bound.alloc_ptr.return_value
        bind.assert_called_once_with(addrspace)
        bound.alloc_ptr.assert_called_once_with([1, 2, 3])


class TestCProxy:

    def test_init_setsAttributes(self, ctype, addrspace):
        adr = addrspace.alloc_memory(10)
        bound_ctype = ctype.bind(addrspace)
        cproxy = cdm.CProxy(bound_ctype, adr)
        assert cproxy.ctype is bound_ctype
        assert cproxy.__address__ == adr

    def test_init_onManagedMemoryBlocks(self, ctype, addrspace):
        adr = addrspace.alloc_memory(10)
        bound_ctype = ctype.bind(addrspace)
        cproxy = cdm.CProxy(bound_ctype, adr)

    @pytest.fixture
    def cobj(self, ctype, addrspace):
        bound_ctype = ctype.bind(addrspace)
        adr = addrspace.alloc_memory(10)
        return cdm.CProxy(bound_ctype, adr)

    def test_getVal_returnsConvertedCRepr(self, ctype, addrspace):
        ctype.convert_from_c_repr = convert_from_c_repr = Mock()
        cproxy = cdm.CProxy(ctype.bind(addrspace), 0)
        assert cproxy.val is convert_from_c_repr.return_value
        convert_from_c_repr.assert_called_once_with(addrspace.content[:1])

    def test_setVal_storesConvertedValue(self, cobj, addrspace):
        cobj.ctype.convert_to_c_repr = Mock()
        addrspace.write_memory = Mock()
        set_val = Mock()
        cobj.val = set_val
        cobj.ctype.convert_to_c_repr.assert_called_once_with(set_val)
        addrspace.write_memory.assert_called_once_with(
            cobj.__address__,
            cobj.ctype.convert_to_c_repr.return_value)

    def test_setVal_onConstAttr_raisesWriteProtectError(self, cobj, addrspace):
        cobj.ctype = cobj.ctype.with_attr('const')
        with pytest.raises(cdm.WriteProtectError):
            cobj.val = 1

    @patch.object(cdm.CProxy, 'val', 123)
    @patch.object(cdm.CProxyType, '__repr__', return_value='name_of_ctype')
    def test_repr_returnsCNameAndValue(self, repr_func, cobj):
        assert repr(cobj) == 'name_of_ctype(123)'

    @patch.object(CMyType, 'ptr')
    def test_getAdr_returnsPointerObjToSelfDependingOnSelf(self, ptr, cobj):
        cptr_obj = cobj.adr
        assert cptr_obj is ptr.return_value
        ptr.assert_called_once_with(cobj.__address__)

    def test_sizeof_forwardsToCProxyType(self, cobj):
        cobj.ctype.sizeof = Mock()
        assert cobj.sizeof is cobj.ctype.sizeof

    def test_copy_returnsCopyOfMemoryAndCProxy(self, cint_type):
        cint_obj = cint_type(0x1234)
        copied_obj = cint_obj.copy()
        assert copied_obj.ctype == cint_obj.ctype
        assert copied_obj.val == cint_obj.val
        assert copied_obj.__address__ != cint_obj.__address__

    def test_getMem_returnsCMemoryObject(self, cobj, addrspace):
        mem = cobj.mem
        assert mem.addrspace == addrspace
        assert mem.address == cobj.__address__
        assert mem.max_address == None
        assert not mem.readonly

    def test_getMem_onObjectWithoutManagedMemoryBlock_setsMaxAddrOfCMemoryToNone(self, cobj):
        assert cobj.mem.max_address == None

    def test_getMem_onConstAttr_setsReadonlyFlag(self, ctype, addrspace):
        const_ctype = ctype.with_attr('const').bind(addrspace)
        cobj = cdm.CProxy(const_ctype, 0)
        assert cobj.mem.readonly

    @pytest.mark.parametrize('newval', [b'123', iter(b'123')])
    def test_setMem_onBytesConvertable_setsData(self, cobj, addrspace, newval):
        addrspace.write_memory(cobj.__address__, b'987654')
        cobj.mem = newval
        assert cobj.mem == b'123654'

    def test_getMem_onConstAttr_raisesWriteMemoryError(self, ctype, addrspace):
        const_ctype = ctype.with_attr('const').bind(addrspace)
        cobj = cdm.CProxy(const_ctype, 0)
        with pytest.raises(core.WriteProtectError):
            cobj.mem = b'x'

    def cobj_of_val(self, val):
        static_val_ctype = Mock(convert_from_c_repr=Mock(return_value=val),
                                __addrspace__=Mock(),
                                side_effect=self.cobj_of_val,
                                has_attr=Mock(return_value=False))
        return cdm.CProxy(static_val_ctype, 0)

    def test_eq_onPyObjOfSameValue_returnsTrue(self):
        assert self.cobj_of_val(10) == 10
        assert 10 == self.cobj_of_val(10)

    def test_eq_onPyObjOfDifferentValue_returnsFalse(self):
        assert self.cobj_of_val(10) != 9
        assert 9 != self.cobj_of_val(10)

    def test_eq_onCProxyOfSameValue_returnsTrue(self):
        assert self.cobj_of_val(999) == self.cobj_of_val(999)

    def test_eq_onCProxyOfDifferentValue_returnsFalse(self):
        assert self.cobj_of_val(1000) != self.cobj_of_val(999)

    def test_gtLt_onPyObj_ok(self):
        assert self.cobj_of_val(4) > 3
        assert not self.cobj_of_val(4) < 3
        assert self.cobj_of_val(3) < 4
        assert not self.cobj_of_val(3) > 4

    def test_geLE_onPyObj_ok(self):
        assert self.cobj_of_val(4) >= 3
        assert self.cobj_of_val(4) >= 4
        assert not self.cobj_of_val(4) <= 3
        assert self.cobj_of_val(3) <= 4
        assert self.cobj_of_val(4) <= 4
        assert not self.cobj_of_val(3) >= 4

    def test_add_onPyObj_ok(self):
        cint_obj = self.cobj_of_val(4)
        cint_obj2 = cint_obj + 1
        assert cint_obj.val == 4
        assert cint_obj2.val == 5

    def test_add_onCProxy_ok(self):
        cint_obj = self.cobj_of_val(4)
        cint_obj2 = cint_obj + self.cobj_of_val(1)
        assert cint_obj.val == 4
        assert cint_obj2.val == 5

    def test_radd_onPyObj_ok(self):
        cint_obj = self.cobj_of_val(4)
        cint_obj2 = 1 + cint_obj
        assert cint_obj.val == 4
        assert cint_obj2.val == 5

    def test_iadd_operatesInplace(self):
        cint_obj = self.cobj_of_val(3)
        cint_obj += 4
        cint_obj.ctype.convert_to_c_repr.assert_called_once_with(7)

    def test_sub_onPyObj_ok(self):
        cint_obj = self.cobj_of_val(4)
        cint_obj2 = cint_obj - 1
        assert cint_obj.val == 4
        assert cint_obj2.val == 3

    def test_sub_onCProxy_ok(self):
        cint_obj = self.cobj_of_val(4)
        cint_obj2 = cint_obj - self.cobj_of_val(1)
        assert cint_obj.val == 4
        assert cint_obj2.val == 3

    def test_rsub_onPyObj_ok(self):
        cint_obj = self.cobj_of_val(4)
        cint_obj2 = 5 - cint_obj
        assert cint_obj.val == 4
        assert cint_obj2.val == 1

    def test_isub_operatesInplace(self):
        cint_obj = self.cobj_of_val(7)
        cint_obj -= 3
        cint_obj.ctype.convert_to_c_repr.assert_called_once_with(4)
