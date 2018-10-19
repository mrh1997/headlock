import pytest
import ctypes as ct
from unittest.mock import patch, Mock, MagicMock, ANY

import headlock.c_data_model as cdm



class CMyType(cdm.PtrArrFactoryMixIn, cdm.CObjType): pass

@pytest.fixture
def cobj_type():
    return CMyType(ct.c_int)


class TestCObjType:

    def test_withAttr_createsDerivedTypeWithSameMembersPlusAttrSet(self, cobj_type):
        cobj_type.derived_member = 123
        attr_cobj_type = cobj_type.with_attr('attr')
        assert attr_cobj_type.c_attributes == {'attr'}
        assert attr_cobj_type.derived_member == 123

    def test_withAttr_onAttrAlreadySet_raiseTypeError(self, cobj_type):
        with pytest.raises(ValueError):
            cobj_type.with_attr('attr').with_attr('attr')

    def test_withAttr_callTwiceWithDifferentAttrs_mergesAttributes(self, cobj_type):
        attr_cobj_type = cobj_type.with_attr('attr1').with_attr('attr2')
        assert attr_cobj_type.c_attributes == {'attr1', 'attr2'}

    def test_hasAttr_onAttrNotSet_returnsFalse(self, cobj_type):
        assert not cobj_type.has_attr('attr')

    def test_hasAttr_onAttrSet_returnsTrue(self, cobj_type):
        attr_test_int32_type = cobj_type.with_attr('attr')
        assert attr_test_int32_type.has_attr('attr')

    def test_call_createsAssignedObj(self, cobj_type):
        cobj_type.COBJ_CLASS = cobj_cls = Mock()
        init_val = Mock()
        depends_on = Mock()
        cobj = cobj_type(init_val, depends_on)
        assert cobj is cobj_cls.return_value
        cobj_cls.assert_called_once_with(cobj_type, init_val, depends_on)

    def test_call_onNoParams_createsAssignedCObjWithNone(self, cobj_type):
        cobj_type.COBJ_CLASS = cobj_cls = Mock()
        cobj = cobj_type()
        cobj_cls.assert_called_once_with(cobj_type, None, None)

    def test_iterSubType_onNoSubTypes_yieldsSelfOnly(self, cobj_type):
        cobj_type.shallow_iter_subtypes = MagicMock()
        assert list(cobj_type.iter_subtypes()) == [cobj_type]
        cobj_type.shallow_iter_subtypes.assert_called_with()

    def test_iterSubType_onFlatObj_forwardsToShallowIterSubType(self, cobj_type):
        cobj_type.shallow_iter_subtypes = MagicMock()
        assert list(cobj_type.iter_subtypes(True)) \
               == [cobj_type]
        cobj_type.shallow_iter_subtypes.assert_called_with()

    def test_iterSubType_onRecusiveSubTypes_yieldsFlattenedSubTypes(self, cobj_type):
        subsubmock = MagicMock()
        submock = Mock()
        submock.iter_subtypes.return_value = iter([submock, subsubmock])
        cobj_type.shallow_iter_subtypes = Mock(return_value=iter([submock]))
        assert list(cobj_type.iter_subtypes()) \
                == [cobj_type, submock, subsubmock]

    def test_iterSubType_onTopLevelFirstIsTrue_reordersElements(self, cobj_type):
        submock1, submock2 = MagicMock(), MagicMock()
        submock1.iter_subtypes = Mock(return_value=iter([submock1]))
        submock2.iter_subtypes = Mock(return_value=iter([submock2]))
        cobj_type.shallow_iter_subtypes = Mock(return_value=iter([submock1,
                                                                  submock2]))
        assert list(cobj_type.iter_subtypes(top_level_last=True)) \
                == [submock1, submock2, cobj_type]
        submock1.iter_subtypes.assert_called_with(True, ANY, ANY, ANY)

    def test_iterSubType_onFilterIsSetAndFilterReturnsFalse_skipsSubType(self, cobj_type):
        filter_func = Mock(return_value=False)
        assert list(cobj_type.iter_subtypes(filter=filter_func)) == []
        filter_func.assert_called_with(cobj_type, None)

    def test_iterSubType_onFilterIsSetAndFilterReturnsFalse_doesNotSkipSubType(self, cobj_type):
        filter_func = Mock(return_value=True)
        assert list(cobj_type.iter_subtypes(filter=filter_func)) == [cobj_type]

    def test_iterSubType_onFilterIsSet_passesParentToFilterAndSubType(self, cobj_type):
        sub_type = MagicMock()
        cobj_type.shallow_iter_subtypes = Mock(return_value=[sub_type])
        filter_func = Mock(return_value=True)
        parent=Mock()
        _ = list(cobj_type.iter_subtypes(filter=filter_func, parent=parent))
        filter_func.assert_any_call(cobj_type, parent)
        sub_type.iter_subtypes.assert_called_with(ANY, filter_func, cobj_type,
                                                  ANY)

    def test_iter_iteratesSubTypes(self, cobj_type):
        assert list(iter(cobj_type)) == []

    def test_eq_onSameAttributes_returnsTrue(self):
        cobj_type1 = cdm.CObjType(ct.c_void_p).with_attr('a').with_attr('b')
        cobj_type2 = cdm.CObjType(ct.c_void_p).with_attr('b').with_attr('a')
        assert cobj_type1 == cobj_type2
        assert not cobj_type1 != cobj_type2

    def test_eq_onDifferentAttributes_returnsFalse(self):
        cobj_type1 = cdm.CObjType(ct.c_void_p).with_attr('a').with_attr('c')
        cobj_type2 = cdm.CObjType(ct.c_void_p).with_attr('a').with_attr('b')
        assert not cobj_type1 == cobj_type2
        assert cobj_type1 != cobj_type2

    def test_eq_onDifferentTypes_returnsFalse(self):
        cobj_type = cdm.CObjType(ct.c_void_p)
        assert cobj_type != "test"

    @patch.object(cdm, 'CArrayType')
    def test_array_onLength_returnsArrayTypeOfGivenSize(self, CArrayType, cobj_type):
        array_type = cobj_type.array(10)
        assert array_type is CArrayType.return_value
        CArrayType.assert_called_once_with(cobj_type, 10)

    @patch.object(CMyType, 'array')
    def test_allocArray_onLength_returnsArrayInstanceOfGivenSize(self, array, cobj_type):
        carray_obj = cobj_type.alloc_array(123)
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
    def test_ptr_returnsCPointerToSelf(self, CPointerType, cobj_type):
        assert cobj_type.ptr is CPointerType.return_value
        CPointerType.assert_called_once_with(cobj_type)

    @patch.object(cdm, 'CPointerType')
    def test_ptr_onCalledMoreThanOnce_returnsCachedPtrType(self, CPointerType, cobj_type):
        retval1 = cobj_type.ptr
        retval2 = cobj_type.ptr
        CPointerType.assert_called_once()
        assert retval1 is retval2

    @patch.object(CMyType, 'alloc_array')
    @patch.object(CMyType, 'ptr')
    def test_allocPtr_onInt_createArrayObjReturnPointerToIt(self, ptr, alloc_array, cobj_type):
        cptr_obj = cobj_type.alloc_ptr(123)
        alloc_array.assert_called_once_with(123)
        ptr.assert_called_once_with(alloc_array.return_value.adr,
                                    _depends_on_=alloc_array.return_value)
        assert cptr_obj == ptr.return_value

    def test_cDecorateCDef_onAttrs_returnsAttrs(self, cobj_type):
        attr_cobj_type = cobj_type.with_attr('volatile').with_attr('other')
        assert attr_cobj_type._decorate_c_definition('*') == 'other volatile *'


class TestCObj:

    def test_init_fromCTypesObj_createsWrapperForTypesObj(self, cobj_type):
        ctypes_obj = ct.c_uint32(999)
        cobj = cdm.CObj(cobj_type, ctypes_obj, None)
        assert cobj.ctypes_obj is ctypes_obj
        assert cobj.cobj_type is cobj_type

    @patch.object(cdm.CObj, 'val')
    def test_init_fromPyObj_returnsCObjInitializedBySetVal(self, val, cobj_type):
        init_val = 'python-object'
        cint = cdm.CObj(cobj_type, init_val, None)
        assert isinstance(cint.ctypes_obj, cobj_type.ctypes_type)
        assert cint.val is init_val

    @patch.object(cdm.CObj, 'val')
    @patch.object(cdm.CObjType, 'null_val')
    def test_init_fromNone_returnsCObjWithNullVal(self, null_val, val, cobj_type):
        cobj = cdm.CObj(cobj_type, None, None)
        assert cobj.val is null_val

    def test_init_fromCObj_returnsCastedObj(self, cobj_type):
        cobj = cdm.CObj(cobj_type, ct.c_uint32(), None)
        class CastedCObj(cdm.CObj):
            _cast_from = Mock()
        _ = CastedCObj(cobj_type, cobj, None)
        CastedCObj._cast_from.assert_called_once_with(cobj)

    @patch.object(cdm.CObj, 'val')
    @patch.object(cdm.CObjType, '__repr__', return_value='name_of_ctype')
    def test_repr_returnsCNameAndValue(self, repr_func, val_prop, cobj_type):
        cobj = cdm.CObj(cobj_type, 123, None)
        assert repr(cobj) == 'name_of_ctype(123)'

    @patch.object(CMyType, 'ptr')
    def test_getAdr_returnsPointerObjToSelfDependingOnSelf(self, ptr, cobj_type):
        cobj_obj = cdm.CObj(cobj_type, ct.c_uint32(), None)
        cptr_obj = cobj_obj.adr
        ptr.ctypes_type.assert_called_once_with(cobj_obj.ctypes_obj)
        ptr.assert_called_once_with(ptr.ctypes_type.return_value,
                                    _depends_on_=cobj_obj)
        assert cptr_obj is ptr.return_value

    @patch.object(cdm.CObjType, 'sizeof')
    def test_sizeof_forwardsToCObjType(self, sizeof, cobj_type):
        cobj_obj = cdm.CObj(cobj_type, ct.c_uint32(), None)
        assert cobj_obj.sizeof is sizeof

    @patch.object(cdm.CObj, 'val', 123)
    def test_repr_returnsCObjTypeReprPlusCallParentheses(self, cobj_type):
        cobj_type = MagicMock()
        cobj_type.__repr__ = Mock(return_value='ts.xyz')
        cobj_obj = cdm.CObj(cobj_type, ct.c_int(999))
        assert repr(cobj_obj) == 'ts.xyz(123)'


