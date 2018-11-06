import pytest
import ctypes as ct
from unittest.mock import patch, Mock, MagicMock, ANY

import headlock.c_data_model as cdm



class CMyType(cdm.PtrArrFactoryMixIn, cdm.CProxyType): pass

@pytest.fixture
def ctype():
    return CMyType(ct.c_int)


class TestCProxyType:

    def test_withAttr_createsDerivedTypeWithSameMembersPlusAttrSet(self, ctype):
        ctype.derived_member = 123
        attr_ctype = ctype.with_attr('attr')
        assert attr_ctype.c_attributes == {'attr'}
        assert attr_ctype.derived_member == 123

    def test_withAttr_onAttrAlreadySet_raiseTypeError(self, ctype):
        with pytest.raises(ValueError):
            ctype.with_attr('attr').with_attr('attr')

    def test_withAttr_callTwiceWithDifferentAttrs_mergesAttributes(self, ctype):
        attr_ctype = ctype.with_attr('attr1').with_attr('attr2')
        assert attr_ctype.c_attributes == {'attr1', 'attr2'}

    def test_hasAttr_onAttrNotSet_returnsFalse(self, ctype):
        assert not ctype.has_attr('attr')

    def test_hasAttr_onAttrSet_returnsTrue(self, ctype):
        attr_test_int32_type = ctype.with_attr('attr')
        assert attr_test_int32_type.has_attr('attr')

    def test_call_createsAssignedObj(self, ctype):
        ctype.CPROXY_CLASS = cproxy_cls = Mock()
        init_val = Mock()
        depends_on = Mock()
        cproxy = ctype(init_val, depends_on)
        assert cproxy is cproxy_cls.return_value
        cproxy_cls.assert_called_once_with(ctype, init_val, depends_on)

    def test_call_onNoParams_createsAssignedCProxyWithNone(self, ctype):
        ctype.CPROXY_CLASS = cproxy_cls = Mock()
        cproxy = ctype()
        cproxy_cls.assert_called_once_with(ctype, None, None)

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
        ctype1 = cdm.CProxyType(ct.c_void_p).with_attr('a').with_attr('b')
        ctype2 = cdm.CProxyType(ct.c_void_p).with_attr('b').with_attr('a')
        assert ctype1 == ctype2
        assert not ctype1 != ctype2

    def test_eq_onDifferentAttributes_returnsFalse(self):
        ctype1 = cdm.CProxyType(ct.c_void_p).with_attr('a').with_attr('c')
        ctype2 = cdm.CProxyType(ct.c_void_p).with_attr('a').with_attr('b')
        assert not ctype1 == ctype2
        assert ctype1 != ctype2

    def test_eq_onDifferentTypes_returnsFalse(self):
        ctype = cdm.CProxyType(ct.c_void_p)
        assert ctype != "test"

    @patch.object(cdm, 'CArrayType')
    def test_array_onLength_returnsArrayTypeOfGivenSize(self, CArrayType, ctype):
        array_type = ctype.array(10)
        assert array_type is CArrayType.return_value
        CArrayType.assert_called_once_with(ctype, 10)

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
        CPointerType.assert_called_once_with(ctype)

    @patch.object(cdm, 'CPointerType')
    def test_ptr_onCalledMoreThanOnce_returnsCachedPtrType(self, CPointerType, ctype):
        retval1 = ctype.ptr
        retval2 = ctype.ptr
        CPointerType.assert_called_once()
        assert retval1 is retval2

    @patch.object(CMyType, 'alloc_array')
    @patch.object(CMyType, 'ptr')
    def test_allocPtr_onInt_createArrayObjReturnPointerToIt(self, ptr, alloc_array, ctype):
        cptr_obj = ctype.alloc_ptr(123)
        alloc_array.assert_called_once_with(123)
        ptr.assert_called_once_with(alloc_array.return_value.adr,
                                    _depends_on_=alloc_array.return_value)
        assert cptr_obj == ptr.return_value

    def test_cDecorateCDef_onAttrs_returnsAttrs(self, ctype):
        attr_ctype = ctype.with_attr('volatile').with_attr('other')
        assert attr_ctype._decorate_c_definition('*') == 'other volatile *'


class TestCProxy:

    def test_init_fromCTypesObj_createsWrapperForTypesObj(self, ctype):
        ctypes_obj = ct.c_uint32(999)
        cproxy = cdm.CProxy(ctype, ctypes_obj, None)
        assert cproxy.ctypes_obj is ctypes_obj
        assert cproxy.ctype is ctype

    @patch.object(cdm.CProxy, 'val')
    def test_init_fromPyObj_returnsCProxyInitializedBySetVal(self, val, ctype):
        init_val = 'python-object'
        cint = cdm.CProxy(ctype, init_val, None)
        assert isinstance(cint.ctypes_obj, ctype.ctypes_type)
        assert cint.val is init_val

    @patch.object(cdm.CProxy, 'val')
    @patch.object(cdm.CProxyType, 'null_val')
    def test_init_fromNone_returnsCProxyWithNullVal(self, null_val, val, ctype):
        cproxy = cdm.CProxy(ctype, None, None)
        assert cproxy.val is null_val

    def test_init_fromCProxy_returnsCastedObj(self, ctype):
        cproxy = cdm.CProxy(ctype, ct.c_uint32(), None)
        class CastedCProxy(cdm.CProxy):
            _cast_from = Mock()
        _ = CastedCProxy(ctype, cproxy, None)
        CastedCProxy._cast_from.assert_called_once_with(cproxy)

    @patch.object(cdm.CProxy, 'val')
    @patch.object(cdm.CProxyType, '__repr__', return_value='name_of_ctype')
    def test_repr_returnsCNameAndValue(self, repr_func, val_prop, ctype):
        cproxy = cdm.CProxy(ctype, 123, None)
        assert repr(cproxy) == 'name_of_ctype(123)'

    @patch.object(CMyType, 'ptr')
    def test_getAdr_returnsPointerObjToSelfDependingOnSelf(self, ptr, ctype):
        cproxy_obj = cdm.CProxy(ctype, ct.c_uint32(), None)
        cptr_obj = cproxy_obj.adr
        ptr.ctypes_type.assert_called_once_with(cproxy_obj.ctypes_obj)
        ptr.assert_called_once_with(ptr.ctypes_type.return_value,
                                    _depends_on_=cproxy_obj)
        assert cptr_obj is ptr.return_value

    @patch.object(cdm.CProxyType, 'sizeof')
    def test_sizeof_forwardsToCProxyType(self, sizeof, ctype):
        cproxy_obj = cdm.CProxy(ctype, ct.c_uint32(), None)
        assert cproxy_obj.sizeof is sizeof

    @patch.object(cdm.CProxy, 'val', 123)
    def test_repr_returnsCProxyTypeReprPlusCallParentheses(self, ctype):
        ctype = MagicMock()
        ctype.__repr__ = Mock(return_value='ts.xyz')
        cproxy_obj = cdm.CProxy(ctype, ct.c_int(999))
        assert repr(cproxy_obj) == 'ts.xyz(123)'


