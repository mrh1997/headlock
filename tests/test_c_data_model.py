from unittest.mock import patch, Mock, MagicMock, ANY
import ctypes as ct
import pytest
import headlock.c_data_model as cdm
from contextlib import contextmanager
import re


class TestCMemory:

    def test_init_onAddressOnly_setsAttributes(self):
        cmem_obj = cdm.CMemory(0x1234)
        assert cmem_obj.addr == 0x1234
        assert not cmem_obj.readonly
        assert cmem_obj.max_size is None

    def test_init_onMaxSizeAndReadOnly_setsAttributes(self):
        cmem_obj = cdm.CMemory(0, 1234, readonly=True)
        assert cmem_obj.max_size == 1234
        assert cmem_obj.readonly

    @pytest.fixture
    def testdata(self):
        return b'\x12\x34\x56\x78'

    @pytest.fixture
    def ct_obj(self, testdata):
        return (ct.c_ubyte * len(testdata))(*testdata)

    @pytest.fixture
    def cmem_obj(self, ct_obj, testdata):
        return cdm.CMemory(ct.addressof(ct_obj), len(testdata))

    @pytest.mark.parametrize('test_ndx', [0, 1, 3])
    def test_getItem_onIndex_returnsIntAtIndex(self, cmem_obj, testdata, test_ndx):
        assert cmem_obj[test_ndx] == testdata[test_ndx]

    @pytest.mark.parametrize('test_slice', [slice(2),    slice(1, 3),
                                            slice(2, 4), slice(0, 4, 2)])
    def test_getItem_onSlice_returnsBytes(self, cmem_obj, testdata, test_slice):
        assert cmem_obj[test_slice] == testdata[test_slice]

    @pytest.mark.parametrize('invalid_index', (-1, 4))
    def test_getItem_onInvalidIndex_raisesIndexError(self, cmem_obj, invalid_index):
        with pytest.raises(IndexError):
            _ = cmem_obj[invalid_index]

    @pytest.mark.parametrize('invalid_slice', [
        slice(-1, 4, None),   slice(1, -1, None), slice(1, 4, -1),  # negative
        slice(1, None, None),                                       # None
        slice(1, 5, None)])                                         # too big
    def test_getItem_onInvalidSlice_raisesIndexError(self, cmem_obj, invalid_slice):
        with pytest.raises(IndexError):
            _ = cmem_obj[invalid_slice]

    def test_setItem_onIndex_setsInteger(self, cmem_obj, ct_obj):
        cmem_obj[2] = 0x99
        assert ct_obj[0:4] == [0x12, 0x34, 0x99, 0x78]

    def test_setItem_onSlice_setsByteLike(self, cmem_obj, ct_obj):
        cmem_obj[1:3] = b'\x88\x99'
        assert ct_obj[:4] == [0x12, 0x88, 0x99, 0x78]

    def test_setItem_onReadOnly_raisesWriteProtectError(self, ct_obj):
        ro_raw_access = cdm.CMemory(ct_obj, readonly=True)
        with pytest.raises(cdm.WriteProtectError):
            ro_raw_access[2] = 0x99

    def test_setItem_onInvalidIndex_raisesIndexError(self, cmem_obj):
        with pytest.raises(IndexError):
            cmem_obj[-1] = 1

    def test_repr_ok(self):
        cmem_obj = cdm.CMemory(0x1234, 10, readonly=True)
        assert repr(cmem_obj) == "CMemory(0x1234, 10, readonly=True)"

    def test_iter_ok(self, cmem_obj):
        cmem_obj.max_size = None
        raw_iter = iter(cmem_obj)
        assert [next(raw_iter) for c in range(4)] == [0x12, 0x34, 0x56, 0x78]

    def test_iter_onExceedMaxSize_raisesIndexError(self, cmem_obj):
        raw_iter = iter(cmem_obj)
        for c in range(4): next(raw_iter)
        with pytest.raises(IndexError):
            next(raw_iter)

    def test_eq_onIdenticalStr_returnsTrue(self, cmem_obj):
        assert cmem_obj == b'\x12\x34\x56\x78'

    def test_eq_onShorterStringButIdenticalBytesAtBegin_returnsTrue(self, cmem_obj):
        assert cmem_obj == b'\x12\x34\x56'

    def test_eq_onUnequalString_returnsFalse(self, cmem_obj):
        assert not cmem_obj == b'\x12\x34\x56\x99'

    def test_eq_onWrongType_returnsFalse(self, cmem_obj):
        assert not cmem_obj == 33

    def test_ne_ok(self, cmem_obj):
        assert cmem_obj != b'\x12\x34\x56\x99'
        assert not cmem_obj != b'\x12\x34\x56\x78'

    def test_lt_ok(self, cmem_obj):
        assert cmem_obj < b'\x12\x34\x56\x79'
        assert not cmem_obj < b'\x12\x34\x56\x78'

    def test_gt_ok(self, cmem_obj):
        assert cmem_obj > b'\x12\x34\x56\x77'
        assert not cmem_obj > b'\x12\x34\x56\x78'

    def test_qt_onWrongType_raisesTypeErrpr(self, cmem_obj):
        with pytest.raises(TypeError):
            _ = cmem_obj > 33

    def test_le_ok(self, cmem_obj):
        assert cmem_obj <= b'\x12\x34\x56\x78'
        assert not cmem_obj <= b'\x12\x34\x56\x77'

    def test_ge_ok(self, cmem_obj):
        assert cmem_obj >= b'\x12\x34\x56\x78'
        assert not cmem_obj >= b'\x12\x34\x56\x79'


@pytest.fixture
def cobj_type():
    return cdm.CObjType(ct.c_int)


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

    @patch.object(cdm.CObjType, 'array')
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

    @patch.object(cdm.CObjType, 'alloc_array')
    @patch.object(cdm.CObjType, 'ptr')
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

    @patch.object(cdm.CObjType, 'ptr')
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


@pytest.fixture
def cint_type():
    return cdm.CIntType('typename', 32, True, ct.c_int32)


class TestCIntType:

    def test_cDefinition_returnsCName(self):
        cint_type = cdm.CIntType('typename', 32, True, ct.c_int32)
        assert cint_type.c_definition() == 'typename'

    def test_cDefinition_onRefDefIsSet_returnsWithRefDef(self):
        cint_type = cdm.CIntType('typename', 32, True, ct.c_int32)
        assert cint_type.c_definition('varname') == 'typename varname'

    @pytest.mark.parametrize(('ctypes_type', 'bits', 'signed'), [
        (ct.c_int8, 8, True),
        (ct.c_uint32, 32, False),
        (ct.c_int64, 64, True)])
    def test_sizeof_returnsSizeInBytes(self, ctypes_type, bits, signed):
        cint_type = cdm.CIntType('typename', bits, signed, ctypes_type)
        assert cint_type.sizeof == bits/8

    def test_nullVal_ok(self, cint_type):
        assert cint_type.null_val == 0

    def test_repr_withAttrAndSpaceInName_ok(self):
        cint_type = cdm.CIntType('type name', 32, True, ct.c_int32)
        attr_cint_type = cint_type.with_attr('attrB').with_attr('attrA')
        assert repr(attr_cint_type) == 'ts.attrA_attrB_type_name'

    def test_eq_inSameCIntType_returnsTrue(self):
        assert cdm.CIntType('name', 32, True, ct.c_int) \
               == cdm.CIntType('name', 32, True, ct.c_int)

    @pytest.mark.parametrize('diff_cint_type', [
        "ohertype",
        cdm.CIntType('othername', 32, True, ct.c_int),
        cdm.CIntType('name', 32, True, ct.c_int).with_attr('test'),
        cdm.CIntType('name', 16, True, ct.c_int),
        cdm.CIntType('name', 32, False, ct.c_int)])
    def test_eq_inDifferentCIntType_returnsFalse(self, diff_cint_type):
        assert diff_cint_type != cdm.CIntType('name', 32, True, ct.c_int)


class TestCInt:

    def test_getVal_returnsIntValue(self, cint_type):
        cint_obj = cint_type(999)
        assert isinstance(cint_obj.val, int)
        assert cint_obj.val == 999

    def test_getVal_onChar_returnsIntValue(self):
        cchar_type = cdm.CIntType('char', 8, True, ct.c_char)
        cchar_obj = cchar_type(65)
        assert cchar_obj.val == 65

    def test_setVal_modifiesVal(self, cint_type):
        cint_obj = cint_type(999)
        cint_obj.val = 1111
        assert cint_obj.val == 1111

    def test_setVal_modifiesCObjInplace(self, cint_type):
        cint_obj = cint_type(999)
        orig_adr = ct.addressof(cint_obj.ctypes_obj)
        cint_obj.val = 1111
        assert cint_obj.ctypes_obj.value == 1111
        assert ct.addressof(cint_obj.ctypes_obj) == orig_adr

    def test_setVal_onCObj_writesValOfCObj(self, cint_type):
        cint_obj = cint_type()
        cint_obj.val = cint_type(2)
        assert cint_obj.val == 2

    @pytest.mark.xfail
    def test_setVal_onConstCObj_raisesWriteProtectError(self, cint_type):
        const_cint_obj = cint_type.with_attr('const')(3)
        with pytest.raises(cdm.WriteProtectError):
            const_cint_obj.val = 4

    def test_setVal_onBytesOfSize1_setsAsciiCode(self, cint_type):
        cint_obj = cint_type()
        cint_obj.val = b'\xFF'
        assert cint_obj == 0xFF

    def test_setVal_onStrOfSize1_setsUnicodeCodepoint(self, cint_type):
        cint_type = cint_type()
        cint_type.val = '\U00012345'
        assert cint_type == 0x12345

    def test_eq_onPyObjOfSameValue_returnsTrue(self, cint_type):
        assert cint_type(9) == 9
        assert 9 == cint_type(9)

    def test_eq_onPyObjOfDifferentValue_returnsFalse(self, cint_type):
        assert cint_type(9) != 10
        assert 10 != cint_type(9)

    def test_eq_onCObjOfSameValue_returnsTrue(self, cint_type):
        assert cint_type(999) == cint_type(999)

    def test_eq_onCObjOfDifferentValue_returnsFalse(self, cint_type):
        assert cint_type(1000) != cint_type(999)

    def test_getMem_returnsBufferOfRawData(self, cint_type):
        cint_obj = cint_type(0x120084)
        cmem_obj = cint_obj.mem
        assert isinstance(cmem_obj, cdm.CMemory)
        assert cmem_obj.addr == ct.addressof(cint_obj.ctypes_obj)
        assert cmem_obj.max_size is None
        assert not cmem_obj.readonly

    def test_getMem_onConstObj_returnsReadonlyRawData(self, cint_type):
        cint_obj = cint_type.with_attr('const')(0x120084)
        assert cint_obj.mem.readonly

    def test_setMem_setsRawDataToBuffer(self, cint_type):
        cint_obj = cint_type()
        cint_obj.mem = bytearray.fromhex("34 00 12 00")
        assert cint_obj.val == 0x120034

    def test_setMem_onValueSmallerThanCObj_ok(self, cint_type):
        cint_obj = cint_type()
        cint_obj.mem = b'\x11'
        assert cint_obj.val == 0x00000011

    def test_setMem_onConst_raiseReadOnlyError(self, cint_type):
        int_obj = cint_type.with_attr('const')(2)
        with pytest.raises(cdm.WriteProtectError):
            int_obj.mem = b'1234'

    def test_gtLt_onPyObj_ok(self, cint_type):
        assert cint_type(4) > 3
        assert not cint_type(4) < 3
        assert cint_type(3) < 4
        assert not cint_type(3) > 4

    def test_geLE_onPyObj_ok(self, cint_type):
        assert cint_type(4) >= 3
        assert cint_type(4) >= 4
        assert not cint_type(4) <= 3
        assert cint_type(3) <= 4
        assert cint_type(4) <= 4
        assert not cint_type(3) >= 4

    def test_add_onPyObj_ok(self, cint_type):
        cint_obj = cint_type(4)
        cint_obj2 = cint_obj + 1
        assert cint_obj.val == 4
        assert cint_obj2.val == 5

    def test_add_onCObj_ok(self, cint_type):
        cint_obj = cint_type(4)
        cint_obj2 = cint_obj + cint_type(1)
        assert cint_obj.val == 4
        assert cint_obj2.val == 5

    def test_radd_onPyObj_ok(self, cint_type):
        cint_obj = cint_type(4)
        cint_obj2 = 1 + cint_obj
        assert cint_obj.val == 4
        assert cint_obj2.val == 5

    def test_iadd_operatesInplace(self, cint_type):
        cint_obj = cint_type(3)
        adr = cint_obj.mem.addr
        cint_obj += 4
        assert cint_obj.val == 7
        assert cint_obj.mem.addr == adr

    def test_sub_onPyObj_ok(self, cint_type):
        cint_obj = cint_type(4)
        cint_obj2 = cint_obj - 1
        assert cint_obj.val == 4
        assert cint_obj2.val == 3

    def test_sub_onCObj_ok(self, cint_type):
        cint_obj = cint_type(4)
        cint_obj2 = cint_obj - cint_type(1)
        assert cint_obj.val == 4
        assert cint_obj2.val == 3

    def test_rsub_onPyObj_ok(self, cint_type):
        cint_obj = cint_type(4)
        cint_obj2 = 5 - cint_obj
        assert cint_obj.val == 4
        assert cint_obj2.val == 1

    def test_isub_operatesInplace(self, cint_type):
        cint_obj = cint_type(7)
        adr = cint_obj.mem.addr
        cint_obj -= 3
        assert cint_obj.val == 4
        assert cint_obj.mem.addr == adr

    def test_index_ok(self, cint_type):
        array = [0x11, 0x22, 0x33]
        assert array[cint_type(1)] == 0x22

    def test_int_ok(self, cint_type):
        assert int(cint_type(1)) == 1

    def test_repr_onSignedChar_returnsBytes(self):
        cchar_type = cdm.CIntType('char', 8, True, ct.c_char)
        cchar_obj = cchar_type(b'A')
        assert repr(cchar_obj) == "ts.char(b'A')"

    def test_repr_onNonSignedCharType_returnsInt(self, cint_type):
        cint_obj = cint_type(65)
        assert repr(cint_obj) == "ts.typename(65)"

    def test_copy_returnsSameValueButDifferentAddress(self, cint_type):
        cint_obj = cint_type(999)
        cint_obj_copy = cint_obj.copy()
        assert cint_obj.val == cint_obj_copy.val
        assert cint_obj.mem.addr != cint_obj_copy.mem.addr


@pytest.fixture
def cptr_type(cint_type):
    return cdm.CPointerType(cint_type)


class TestCPointerType:

    def test_init_onPtrType_returnsInitializedPointerObj(self):
        cobj_type = Mock()
        ctypes_type = Mock()
        cptr_type = cdm.CPointerType(cobj_type, ctypes_type)
        assert cptr_type.base_type is cobj_type
        assert cptr_type.ctypes_type is ctypes_type

    def test_init_onDefaultParams_ok(self):
        cobj_type = Mock()
        cobj_type.ctypes_type = ct.c_float
        cobj_type.c_name = 'base_type_name'
        cptr_type = cdm.CPointerType(cobj_type)
        assert cptr_type.ctypes_type is ct.POINTER(ct.c_float)

    def test_shallowIterSubTypes_onNotEmbeddedDefsOnlyIsFalse_returnsReferredTypeElementaryTypes(self, cptr_type):
        assert list(cptr_type.shallow_iter_subtypes()) \
               == [cptr_type.base_type]

    def test_eq_onSamePointer_returnsTrue(self, cint_type):
        assert cdm.CPointerType(cint_type) \
               == cdm.CPointerType(cint_type)

    @pytest.mark.parametrize('diff_cptr_type', [
        "othertype",
        cdm.CPointerType(cdm.CIntType('x', 32,True,ct.c_int)).with_attr('attr'),
        cdm.CPointerType(cdm.CIntType('y', 16,False,ct.c_int))])
    def test_eq_onDifferentPointer_returnsFalse(self, diff_cptr_type):
        basetype = cdm.CIntType('x', 32, True, ct.c_int)
        assert cdm.CPointerType(basetype, ct.c_int) != diff_cptr_type

    def test_sizeof_returnsSameSizeAsInt(self, cptr_type):
        assert cptr_type.sizeof == ct.sizeof(cptr_type.ctypes_type)

    def test_nullValue_ok(self, cptr_type):
        assert cptr_type.null_val == 0

    def test_cDefinition_onNoRefDef_returnsCNameWithoutRefDef(self, cint_type):
        assert cint_type.ptr.c_definition() == 'typename *'

    def test_cDefinition_onPtrToPtr_returnsTwoStars(self, cint_type):
        assert cint_type.ptr.ptr.c_definition() == 'typename **'

    def test_cDefinition_onRefDef_returnsCNameWithRefDef(self, cint_type):
        assert cint_type.ptr.c_definition('ab') == 'typename *ab'

    def test_repr_returnsBaseNamePlusPtr(self):
        cobj_type = MagicMock()
        cobj_type.__repr__ = Mock(return_value='ts.basetype')
        cobj_type.ctypes_type = ct.c_int
        cptr_type = cdm.CPointerType(cobj_type).with_attr('attr')
        assert repr(cptr_type) == 'ts.basetype_attr_ptr'


class TestCPointer:

    def test_init_fromCTypes_returnsWrapperAroundCTypesObj(self, cptr_type):
        ctypes_ptr = ct.pointer(ct.c_uint32(999))
        cptr_obj = cptr_type(ctypes_ptr)
        assert cptr_obj.ctypes_obj is ctypes_ptr

    def test_init_fromPyInt_returnsPtrObjReferingGivenAddress(self, cptr_type):
        cptr_obj = cptr_type(999)
        assert ct.addressof(cptr_obj.ctypes_obj.contents) == 999

    def test_init_fromCInt_returnsPtrToSpecifiedAdrVal(self, cptr_type, cint_type):
        ctypes_int = ct.c_int32()
        cint_obj = cint_type(ct.addressof(ctypes_int))
        cptr_obj = cdm.CPointer(cptr_type, cint_obj)
        assert ct.addressof(cptr_obj.ctypes_obj.contents) \
               == ct.addressof(ctypes_int)

    def test_init_fromCPointer_returnsCastedCPointer(self, cint_type, cptr_type):
        cint_obj = cint_type()
        cptr_obj = cptr_type(cint_obj.adr)
        assert ct.addressof(cptr_obj.ctypes_obj.contents) \
               == ct.addressof(cint_obj.adr.ctypes_obj.contents)
        assert isinstance(cptr_obj.ctypes_obj.contents,
                          cptr_type.base_type.ctypes_type)

    def test_init_fromCPointer_hasSameDependsOn(self, cint_type, cptr_type):
        cintptr_obj = cint_type().adr
        cptr_obj = cptr_type(cintptr_obj)
        assert cptr_obj._depends_on_ is cintptr_obj._depends_on_

    @pytest.mark.parametrize('initval', [
        b'\x11\x22\x33', '\x11\x22\x33', [0x11, 0x22, 0x33],
        iter([0x11, 0x22, 0x33])])
    def test_init_fromPyIterable_createsReferredArrayFromIterable(self, initval, cint_type):
        int_ptr = cint_type.ptr(initval)
        assert int_ptr._depends_on_ is not None
        assert int_ptr[:3] == [0x11, 0x22, 0x33]

    def test_init_fromUnicodeObject_createsArrayWithSizeDependingOnDecodedUnicode(self, cint_type):
        int_ptr = cint_type.ptr('\U00012345\u1234')
        assert int_ptr[:3] == [0x12345, 0x1234, 0]

    @contextmanager
    def cptr_to_list(self, val_list):
        cptr_type = cdm.CPointerType(cdm.CIntType('i32', 32,False, ct.c_uint32))
        ctypes_data = (ct.c_uint32 * len(val_list))(*val_list)
        yield cdm.CPointer(cptr_type, ct.addressof(ctypes_data))
        for ndx, item in enumerate(ctypes_data):
            val_list[ndx] = item

    def test_getVal_returnsAddress(self, cptr_type):
        ctypes_int = ct.c_uint32()
        ptr = cdm.CPointer(cptr_type, ct.addressof(ctypes_int))
        assert ptr.val == ct.addressof(ctypes_int)

    def test_getUnicodeStr_onZeroTerminatedStr_returnsPyString(self):
        with self.cptr_to_list([0x1234, 0x56, 0]) as cptr_obj:
            assert cptr_obj.unicode_str == '\u1234\x56'

    def test_setUnicodeStr_onPyStr_changesArrayToZeroTerminatedString(self):
        ref_data = [111] * 6
        with self.cptr_to_list(ref_data) as cptr_obj:
            cptr_obj.unicode_str = '\u1234\x56\0\x78'
        assert ref_data[:6] == [0x1234, 0x56, 0, 0x78, 0, 111]

    def test_getCStr_onZeroTerminatedStr_returnsBytes(self):
        with self.cptr_to_list([ord('X'), ord('y'), 0]) as cptr_obj:
            assert cptr_obj.c_str == b'Xy'

    def test_setCStr_onPyStr_changesArrayToZeroTerminatedString(self):
        ref_data = [111] * 6
        with self.cptr_to_list(ref_data) as cptr_obj:
            cptr_obj.c_str = b'Xy\0z'
        assert ref_data[:6] == [ord('X'), ord('y'), 0, ord('z'), 0, 111]

    def test_int_returnsAddress(self, cptr_type):
        ctypes_int = ct.c_int32()
        cptr_obj = cdm.CPointer(cptr_type, ct.addressof(ctypes_int))
        assert int(cptr_obj) == ct.addressof(ctypes_int)

    def test_getVal_returnsAddressOfReferredObj(self, cptr_type):
        valid_mem_address = ct.addressof(ct.c_int32())
        cptr_obj = cdm.CPointer(cptr_type, valid_mem_address, None)
        assert cptr_obj.val == valid_mem_address

    def test_setVal_setsAddress(self, cptr_type):
        ptr = cdm.CPointer(cptr_type, 0, None)
        valid_mem_address = ct.addressof(ct.c_int32())
        ptr.val = valid_mem_address
        assert ptr.val == valid_mem_address

    def test_setVal_onNullPtr_setsTo0(self, cptr_type):
        valid_mem_address = ct.addressof(ct.c_int32())
        ptr = cdm.CPointer(cptr_type, valid_mem_address, None)
        ptr.val = 0
        assert ptr.val == 0

    def test_setVal_onCArray_setsAddressOfArray(self, cint_type):
        int_arr = cint_type.alloc_array(3)
        int_ptr = cint_type.ptr()
        int_ptr.val = int_arr
        assert int_ptr.val == int_arr.adr.val

    @pytest.mark.parametrize('setval', [
        [0x11, 0x22, 0x33], iter([0x11, 0x22, 0x33])])
    def test_setVal_onIterable_fillsReferredElemsByIterable(self, setval):
        ref_data = [0x99] * 4
        with self.cptr_to_list(ref_data) as cptr_obj:
            cptr_obj.val = setval
        assert ref_data == [0x11, 0x22, 0x33, 0x99]

    def test_setVal_fromBytesObject_fillsReferredElemsPlus0(self):
        ref_data = [0x99] * 5
        with self.cptr_to_list(ref_data) as cptr_obj:
            cptr_obj.val = b'\x11\x22\x33'
        assert ref_data == [0x11, 0x22, 0x33, 0, 0x99]

    def test_setVal_fromUnicodeObject_fillsReferredElemsWithDecodedUnicodePlus0(self):
        ref_data = [0x99] * 4
        with self.cptr_to_list(ref_data) as cptr_obj:
            cptr_obj.val = '\U00012345\u1234'
        assert ref_data == [0x12345, 0x1234, 0, 0x99]

    def test_setVal_onConstPtr_raisesWriteProtectError(self, cptr_type):
        const_ptr_obj = cptr_type.with_attr('const')(3)
        with pytest.raises(cdm.WriteProtectError):
            const_ptr_obj.val = 4

    def test_getRef_ok(self, cptr_type):
        ctypes_obj = ct.c_uint32()
        ref_adr = ct.addressof(ctypes_obj)
        cptr_obj = cdm.CPointer(cptr_type, ref_adr, None)
        ref_cobj = cptr_obj.ref
        assert ct.addressof(ref_cobj.ctypes_obj) == ref_adr
        assert ref_cobj.cobj_type == cptr_obj.base_type

    def test_add_returnsNewPointerAtIncrementedAddress(self):
        with self.cptr_to_list([0] * 100) as cptr_obj:
            moved_cptr_obj = cptr_obj + 100
            assert moved_cptr_obj.val \
                   == cptr_obj.val + 100 * cptr_obj.sizeof

    def test_add_onCInt_ok(self, cint_type):
        inc_cint_obj = cint_type(100)
        with self.cptr_to_list([0] * 100) as cptr_obj:
            moved_cptr_obj = cptr_obj + inc_cint_obj
            assert moved_cptr_obj.val \
                   == cptr_obj.val + 100 * cptr_obj.sizeof

    def test_sub_returnsNewPointerAtDecrementedAddress(self):
        with self.cptr_to_list([0] * 100) as cptr_obj:
            end_cptr_obj = cptr_obj + 100
            moved_cptr_obj = end_cptr_obj - 70
            assert moved_cptr_obj.val \
                   == end_cptr_obj.val - 70 * cptr_obj.sizeof

    def test_sub_onCPointer_returnsNumberOfElementsInBetween(self):
        with self.cptr_to_list([0] * 100) as cptr_obj:
            end_cptr_obj = cptr_obj + 100
            diff_cobj_obj = end_cptr_obj - cptr_obj
            assert isinstance(diff_cobj_obj, int)
            assert diff_cobj_obj == 100

    def test_sub_onCPointerOfDifferrentType_raisesTypeError(self):
        cptr_type1 = cdm.CPointerType(cdm.CIntType('name1', 32, True, ct.c_int))
        cptr_type2 = cdm.CPointerType(cdm.CIntType('name2', 32, True, ct.c_int))
        cptr_obj1 = cdm.CPointer(cptr_type1, 0)
        cptr_obj2 = cdm.CPointer(cptr_type2, 0)
        with pytest.raises(TypeError):
            _ = cptr_obj2 - cptr_obj1

    def test_sub_onCArray_returnsNumberOfElementsInBetween(self, cint_type):
        obj_arr = cint_type.alloc_array(3)
        adr2 = obj_arr[2].adr
        assert adr2 - obj_arr == 2
        assert isinstance(adr2 - obj_arr, int)

    def test_sub_onCInt_ok(self, cint_type):
        with self.cptr_to_list([0] * 100) as cptr_obj:
            cint_obj = cdm.CInt(cint_type, 100)
            moved_cptr_obj = cptr_obj + 100 - cint_obj
        assert moved_cptr_obj.val == cptr_obj.val

    def test_getItem_onNdx_returnsCObjAtNdx(self):
        with self.cptr_to_list([0x11, 0x22, 0x33]) as cptr_obj:
            assert cptr_obj[1].val == 0x22

    def test_getItem_onSlice_returnsCArrayOfCObjAtSlice(self):
        with self.cptr_to_list([0x11, 0x22, 0x33, 0x44]) as cptr_obj:
            carray_obj = cptr_obj[1:3]
            assert isinstance(carray_obj, cdm.CArray)
            assert carray_obj.val == [0x22, 0x33]

    def test_repr_returnsClassNameAndHexValue(self, cptr_type):
        ptr = cdm.CPointer(cptr_type, 1234, None).adr
        assert repr(ptr) == f'ts.typename_ptr_ptr(0x{ptr.val:08X})'


@pytest.fixture
def carray_type(cint_type):
    return cdm.CArrayType(cint_type, 10)


class TestCArrayType:

    def test_shallowIterSubTypes_returnsBaseType(self, carray_type):
        assert list(carray_type.shallow_iter_subtypes()) \
               == [carray_type.base_type]

    def test_eq_onSamePointer_returnsTrue(self, cint_type):
        assert cdm.CPointerType(cint_type, ct.c_int) \
               == cdm.CPointerType(cint_type, ct.c_int)

    @pytest.mark.parametrize('diff_carr_type', [
        "othertype",
        cdm.CArrayType(cdm.CIntType('x', 32, True, ct.c_int), 10)
                             .with_attr('attr'),
        cdm.CArrayType(cdm.CIntType('x', 32, True, ct.c_int), 1000),
        cdm.CArrayType(cdm.CIntType('y', 16, False, ct.c_int), 10)])
    def test_eq_onSamePointer_returnsTrue(self, diff_carr_type):
        basetype = cdm.CIntType('x', 32, True, ct.c_int)
        assert cdm.CArrayType(basetype, 10) != diff_carr_type

    def test_len_returnsSizeOfObject(self, carray_type):
        assert len(carray_type) == carray_type.element_count

    def test_sizeof_returnsSizeInBytes(self, carray_type):
        assert carray_type.sizeof \
               == carray_type.element_count * carray_type.base_type.sizeof

    @patch.object(cdm.CIntType, 'null_val')
    def test_nullValue_ok(self, null_val, carray_type):
        assert carray_type.null_val == [null_val] * carray_type.element_count

    def test_cDefinition_onRefDef_returnsWithRefDef(self, cint_type):
        assert cint_type.array(12).c_definition('x') == 'typename x[12]'

    def test_cDefinition_onNoRefDef_returnsWithoutRefDef(self, cint_type):
        assert cint_type.array(12).c_definition() == 'typename [12]'

    def test_cDefinition_onArrayOfArrays_ok(self, cint_type):
        assert cint_type.array(11).array(22).c_definition() \
               == 'typename [22][11]'

    def test_cDefinition_onArrayOfPtr_ok(self, cint_type):
        assert cint_type.ptr.array(10).c_definition('x') == 'typename *x[10]'

    def test_cDefinition_onPtrToArray_ok(self, cint_type):
        assert cint_type.array(10).ptr.c_definition('x') == 'typename (*x)[10]'

    def test_repr_returnsBaseNamePlusArray(self):
        cobj_type = MagicMock()
        cobj_type.__repr__ = Mock(return_value='ts.basetype')
        cobj_type.ctypes_type = ct.c_int
        cptr_type = cdm.CArrayType(cobj_type, 123).with_attr('attr')
        assert repr(cptr_type) == 'ts.basetype_attr_array123'


class TestCArray:

    def test_init_fromCTypesObj_returnsWrapperAroundParam(self, carray_type):
        ctypes_array = (ct.c_uint32 * carray_type.element_count)()
        carray_obj = cdm.CArray(carray_type, ctypes_array)
        assert carray_obj.ctypes_obj is ctypes_array

    @patch.object(cdm.CIntType, 'null_val', 123)
    def test_init_fromNoParam_returnsArrayOfNullVals(self, carray_type):
        carray_obj = cdm.CArray(carray_type)
        assert all(carray_obj.ctypes_obj[ndx] == 123
                   for ndx in range(carray_type.element_count))

    @patch.object(cdm.CIntType, 'null_val', 0x99)
    def test_init_fromPyIterable_initializesElementsWithIterablePlusNullVals(self, carray_type):
        carray_obj = cdm.CArray(carray_type, [0x11, 0x22])
        assert carray_obj.ctypes_obj[0] == 0x11
        assert carray_obj.ctypes_obj[1] == 0x22
        assert carray_obj.ctypes_obj[2] == 0x99
        assert carray_obj.ctypes_obj[carray_type.element_count-1] == 0x99

    def test_init_fromUtf8WithBigCodepoint_returnsArrayOfCorrectSize(self, carray_type):
        array = cdm.CArray(carray_type, '\u1122')
        assert array.ctypes_obj[0] == 0x1122
        assert array.ctypes_obj[1] == 0

    def test_init_onConstArray_ok(self, cint_type):
        carray_obj = cint_type.with_attr('const').array(1)
        _ = carray_obj()

    def test_getVal_returnsListOfPyObjs(self, carray_type):
        carray_obj = cdm.CArray(carray_type, [0x11, 0x22, 0x33, 0x44])
        assert isinstance(carray_obj.val, list)
        assert isinstance(carray_obj.val[0], int)
        assert carray_obj.val[:4] == [0x11, 0x22, 0x33, 0x44]
        assert len(carray_obj.val) == carray_type.element_count

    @pytest.mark.parametrize('init_iter',
        [b'\x11\x22\x33', [0x11, 0x22, 0x33], iter([0x11, 0x22, 0x33])])
    @patch.object(cdm.CIntType, 'null_val', 0x99)
    def test_setVal_onIterable_setsArrayElemFromIterableEnriesPlusNullVals(self, init_iter, carray_type):
        carray_obj = cdm.CArray(carray_type, [0xAA] * carray_type.element_count)
        carray_obj.val = init_iter
        assert carray_obj.val[:3] == [0x11, 0x22, 0x33]
        assert all(elem == 0x99 for elem in carray_obj.val[3:])

    def create_int_carray_obj(self, bits, init_val):
        ctypes_MAP = {8: ct.c_uint8, 16:ct.c_uint16, 32:ct.c_uint32}
        cint_type = cdm.CIntType('i'+str(bits), bits, False, ctypes_MAP[bits])
        carray_type = cdm.CArrayType(cint_type, len(init_val))
        return carray_type(init_val)

    def test_setVal_onStringTo8BitArray_storesArrayElemUtf8Encoded(self):
        carray_obj = self.create_int_carray_obj(8, [0]*9)
        carray_obj.val = '\x11\u2233\U00014455'
        assert carray_obj.val \
               == [0x11, 0xe2, 0x88, 0xb3, 0xf0, 0x94, 0x91, 0x95, 0]

    def test_setVal_onStringTo16BitArray_storesArrayElemUtf16Encoded(self):
        carray_obj = self.create_int_carray_obj(16, [0]*5)
        carray_obj.val = '\x11\u2233\U00014455'
        assert carray_obj.val == [0x0011, 0x2233, 0xD811, 0xDC55, 0]

    def test_setVal_onStringTo32BitArray_storesArrayElemUtf32Encoded(self):
        carray_obj = self.create_int_carray_obj(32, [0]*4)
        carray_obj.val = '\x11\u2233\U00014455'
        assert carray_obj.val == [0x00000011, 0x00002233, 0x00014455, 0]

    def test_str_returnsStringWithZeros(self):
        carray_obj = self.create_int_carray_obj(16, [ord('x'), ord('Y'), 0])
        assert str(carray_obj) == 'xY\0'

    def test_getCStr_onZeroTerminatedStr_returnsBytes(self):
        carray_obj = self.create_int_carray_obj(16, [ord('X'), ord('y'), 0])
        assert carray_obj.c_str == b'Xy'

    def test_setCStr_onPyStr_changesArrayToZeroTerminatedString(self):
        carray_obj = self.create_int_carray_obj(16, [111]*6)
        carray_obj.c_str = 'Xy\0z'
        assert carray_obj.val == [ord('X'), ord('y'), 0, ord('z'), 0, 0]

    def test_setCStr_onPyStr_changesArrayToZeroTerminatedString(self):
        array = self.create_int_carray_obj(16, [111] * 5)
        array.c_str = 'X\0y'
        assert array.val == [ord('X'), 0, ord('y'), 0, 0]

    def test_setCStr_onTooLongPyStr_raisesValueError(self):
        array = self.create_int_carray_obj(16, [111] * 3)
        with pytest.raises(ValueError):
            array.c_str = 'Xyz'

    def test_getUnicodeStr_onZeroTerminatedStr_returnsPyString(self):
        carray_obj = self.create_int_carray_obj(16, [0x1234, 0x56, 0])
        assert carray_obj.unicode_str == '\u1234\x56'

    def test_setUnicodeStr_onPyStr_changesArrayToZeroTerminatedString(self):
        carray_obj = self.create_int_carray_obj(16, [111] * 6)
        carray_obj.unicode_str = '\u1234\x56\0\x78'
        assert carray_obj.val == [0x1234, 0x56, 0, 0x78, 0, 0]

    def adr_of(self, cobj_obj):
        return ct.addressof(cobj_obj.ctypes_obj)

    def test_getItem_returnsObjectAtNdx(self):
        carray_obj = self.create_int_carray_obj(16, [1, 2, 3, 4])
        assert self.adr_of(carray_obj[2]) \
               == self.adr_of(carray_obj) + 2*carray_obj[0].sizeof

    def test_getItem_onNegativeIndex_returnsElementFromEnd(self):
        carray_obj = self.create_int_carray_obj(16, [0]*5)
        assert self.adr_of(carray_obj[-2]) == self.adr_of(carray_obj[3])

    def test_getItem_onSlice_returnsSubArray(self):
        carray_obj = self.create_int_carray_obj(16, [1, 2, 3, 4])
        sliced_carray_obj = carray_obj[1:3]
        assert sliced_carray_obj.base_type == carray_obj.base_type
        assert [self.adr_of(obj) for obj in sliced_carray_obj] == \
               [self.adr_of(carray_obj[1]), self.adr_of(carray_obj[2])]

    def test_getItem_onSliceWithSteps_raiseValueError(self):
        carray_obj = self.create_int_carray_obj(16, [1, 2, 3, 4])
        with pytest.raises(ValueError):
            carray_obj[0:4:2]

    def test_getItem_onSliceWithNegativeBoundaries_returnsPartOfArrayFromEnd(self):
        carray_obj = self.create_int_carray_obj(16, [0x11, 0x22, 0x33, 0x44])
        assert carray_obj[-3:-1] == [0x22, 0x33]

    def test_getItem_onSliceWithOpenEnd_returnsPartOfArrayUntilEnd(self):
        carray_obj = self.create_int_carray_obj(16, [0x11, 0x22, 0x33, 0x44])
        assert carray_obj[1:] == [0x22, 0x33, 0x44]

    def test_getItem_onSliceWithOpenStart_returnsPartOfArrayFromStart(self):
        carray_obj = self.create_int_carray_obj(16, [0x11, 0x22, 0x33, 0x44])
        assert carray_obj[:3] == [0x11, 0x22, 0x33]

    def test_add_returnsPointer(self):
        carray_obj = self.create_int_carray_obj(32, [0x11, 0x22, 0x33, 0x44])
        added_obj = carray_obj + 3
        assert isinstance(added_obj, cdm.CPointer)
        assert added_obj.val == self.adr_of(carray_obj[3])

    def test_repr_returnsClassNameAndContent(self, cint_type):
        carray_type = cdm.CArrayType(cint_type, 3)
        carray_obj = carray_type([1, 2, 3])
        assert repr(carray_obj) == 'ts.typename_array3([1, 2, 3])'

    def test_iter_returnsIterOfElements(self):
        data = [0x11, 0x22, 0x33, 0x44]
        carray_obj = self.create_int_carray_obj(8, data)
        assert list(iter(carray_obj)) == data


@pytest.fixture
def cint16_type():
    return cdm.CIntType('i16', 16, True, ct.c_int16)


@pytest.fixture
def cstruct_type(cint_type, cint16_type):
    return cdm.CStructType(
        'strct_name',
        [('member_int', cint_type),
         ('member_short', cint16_type),
         ('member_int2', cint_type)])


class TestCStructType:

    def test_init_returnsCStructType(self, cstruct_type, cint_type, cint16_type):
        assert isinstance(cstruct_type, cdm.CStructType)
        assert issubclass(cstruct_type.ctypes_type, ct.Structure)
        assert cstruct_type._members_ == {'member_int': cint_type,
                                          'member_short': cint16_type,
                                          'member_int2': cint_type}
        assert cstruct_type._members_order_ == \
               ['member_int', 'member_short', 'member_int2']

    def test_init_onNameIsNone_returnsAnonymousStructPlusUniqueId(self, cint_type):
        anon1_cstrct_type = cdm.CStructType(None, [('m', cint_type)])
        anon2_cstrct_type = cdm.CStructType(None, [('m', cint_type)])
        assert re.match(r'__anonymous_\d*__', anon1_cstrct_type.struct_name)
        assert re.match(r'__anonymous_\d*__', anon2_cstrct_type.struct_name)
        assert anon1_cstrct_type.struct_name != anon2_cstrct_type.struct_name

    def test_init_onPackingIsSet_setsPacking(self, cint_type):
        cstruct_type = cdm.CStructType('name', [], 1)
        assert cstruct_type._packing_ == 1
        assert cstruct_type.ctypes_type._pack_ == 1

    @patch.object(cdm.CStructType, 'COBJ_CLASS')
    def test_call_onPositionAndKeywordArgs_mergesParameters(self, COBJ_CLASS, cstruct_type):
        cobj = cstruct_type(1, 2, _depends_on_=3, member_int2=4)
        assert cobj is COBJ_CLASS.return_value
        COBJ_CLASS.assert_called_once_with(
            cstruct_type, dict(member_int=1, member_short=2, member_int2=4), 3)

    @patch.object(cdm.CStructType, 'COBJ_CLASS')
    def test_call_onNoParams_ok(self, COBJ_CLASS, cstruct_type):
        cstruct_type()
        COBJ_CLASS.assert_called_once_with(cstruct_type, {}, None)

    def test_sizeof_onNoExplicitPacking_returnsSizeOfUnpackedStruct(self, cstruct_type, cint_type, cint16_type):
        unpacked_cstruct_type = cdm.CStructType(
            'unpacked_struct',
            [('m1', cint16_type),
             ('m2', cint_type)])
        assert unpacked_cstruct_type.sizeof == 2*cint_type.sizeof

    def test_sizeof_onPacking1_returnsSizeOfPackedStruct(self, cint_type, cint16_type):
        packed_struct = cdm.CStructType(
            'packed_struct',
            [('m1', cint16_type), ('m2', cint_type)],
            1)
        assert packed_struct.sizeof == cint16_type.sizeof + cint_type.sizeof

    def test_nullValue_returnsDictionaryOfNullValues(self, cstruct_type):
        assert cstruct_type.null_val == \
               {'member_int':0, 'member_short':0, 'member_int2':0}

    def test_delayedDef_setsMembers(self, cint_type):
        cstruct_type = cdm.CStructType('strct')
        cstruct_type.delayed_def([('member1',cint_type), ('member2',cint_type)])
        assert cstruct_type.member1 is cint_type
        assert cstruct_type.member2 is cint_type
        assert cstruct_type.ctypes_type._fields_[0][0] == 'member1'

    def test_delayedDef_onRecursiveStruct_ok(self):
        recur_cstruct_type = cdm.CStructType('strct')
        recur_cstruct_type.delayed_def([('nested', recur_cstruct_type.ptr)])
        cstruct_obj = recur_cstruct_type(recur_cstruct_type().adr)
        assert cstruct_obj.nested.ref.nested.val is 0

    def test_len_returnsNumberOfMembers(self, cstruct_type):
        assert len(cstruct_type) == 3

    @pytest.mark.parametrize('name', ['delayed_def', 'c_definition', 'ptr',
                                      'array'])
    def test_GetAttr_OnStructMemberWithReservedName_returnsReservedObj(self, name, cint_type):
        cstruct_type = cdm.CStructType(
            'StructWithReservedMemberNames',
            [(name, cint_type)])
        assert getattr(cstruct_type, name) != 123

    def test_cDefinition_onNoRefDef_returnsDefOnly(self, cint_type):
        cstruct_type = cdm.CStructType('strct_name', [('i', cint_type)])
        assert cstruct_type.c_definition() == 'struct strct_name'

    def test_cDefinition_onRefDef_returnsDefWithName(self, cint_type):
        cstruct_type = cdm.CStructType('strct_name', [('i', cint_type)])
        assert cstruct_type.c_definition('x') == 'struct strct_name x'

    def test_cDefinition_onAnonymousStruct_returnsFullDefinitionWithoutName(self):
        anonym_cstruct_type = cdm.CStructType(None, [])
        assert anonym_cstruct_type.c_definition('x') \
               == 'struct {\n} x'

    def test_cDefinitionFull_onEmptyStruct_ok(self):
        empty_struct = cdm.CStructType('strct_name', [])
        assert empty_struct.c_definition_full() == 'struct strct_name {\n}'

    def test_cDefinitionFull_onRefDef_DefWithName(self):
        empty_struct = cdm.CStructType('strctname', [])
        assert empty_struct.c_definition_full('varname') \
               == 'struct strctname {\n} varname'

    def test_cDefinitionFull_onMembers_addsOneMemberPerLine(self, cint_type, cint16_type):
        cstruct_type = cdm.CStructType('strct_name', [('i', cint_type),
                                                      ('i16', cint16_type)])
        assert cstruct_type.c_definition_full() \
               == ('struct strct_name {\n'
                   '\ttypename i;\n'
                   '\ti16 i16;\n'
                   '}')

    def test_cDefinitionFull_onNestedStructs_notRecursive(self, cstruct_type):
        nested_cstruct_type = cdm.CStructType(
            'nested_cstruct_type',
            [('inner_strct', cstruct_type)])
        assert nested_cstruct_type.c_definition_full() \
               == ('struct nested_cstruct_type {\n'
                   '\tstruct strct_name inner_strct;\n'
                   '}')

    def test_cDefinitionFull_onNestedAnonymousStructs_indentCorrectly(self, cint_type):
        nested_anonym_cstruct_type = cdm.CStructType(
            'nested_anonym_strct',
            [('inner_strct', cdm.CStructType(
                None,
                [('member', cint_type)]))])
        assert nested_anonym_cstruct_type.c_definition_full() \
               == ('struct nested_anonym_strct {\n'
                   '\tstruct {\n'
                   '\t\ttypename member;\n'
                   '\t} inner_strct;\n'
                   '}')

    def test_shallowIterSubTypes_returnsStructAfterNamesOfSubTypes(self, cstruct_type):
        assert list(cstruct_type.shallow_iter_subtypes()) \
               == [cstruct_type._members_[nm]
                   for nm in cstruct_type._members_order_]

    def test_shallowIterSubTypes_onSelfReferringStruct_returnsTypeOnlyOnce(self):
        recur_cstruct_type = cdm.CStructType('recur_cstruct_type')
        recur_cstruct_type.delayed_def([('member', recur_cstruct_type.ptr)])
        assert list(recur_cstruct_type.iter_subtypes()) \
               == [recur_cstruct_type, recur_cstruct_type.ptr]

    def test_shallowIterSubTypes_onAttr_doesNotModifyReturnValue(self, cstruct_type):
        const_cstruct_type = cstruct_type.with_attr('const')
        assert list(const_cstruct_type.shallow_iter_subtypes()) == \
               list(cstruct_type.shallow_iter_subtypes())

    def test_shallowIterSubTypes_onNotYetDefinedMembers_returnsNothing(self):
        cstruct_type = cdm.CStructType('cstruct_type')
        assert list(cstruct_type) == []

    def test_eq_onSameType_returnsTrue(self, cint_type):
        return cdm.CStructType('sname', [('mname', cint_type)]) \
               == cdm.CStructType('sname', [('mname', cint_type)])

    def test_eq_onDifferentType_returnsFalse(self, cstruct_type):
        assert not cstruct_type == "test"

    def test_eq_onDifferentPacking_returnsFalse(self, cint_type):
        return cdm.CStructType('sname', [('mname', cint_type)], packing=1) \
               == cdm.CStructType('sname', [('mname', cint_type)], packing=2)

    def test_eq_onDifferentMemberNames_returnsFalse(self, cint_type):
        return cdm.CStructType('sname', [('mname', cint_type)]) \
               == cdm.CStructType('sname', [('other_mname', cint_type)])
    def test_eq_onDifferentMemberTypes_returnsFalse(self, cint_type, cint16_type):
        return cdm.CStructType('sname', [('mname', cint_type)]) \
               == cdm.CStructType('sname', [('mname', cint16_type)])

    def test_eq_onDifferentMemberCount_returnsFalse(self, cint_type):
        return cdm.CStructType('sname', [('m1', cint_type), ('m2', cint_type)])\
               != cdm.CStructType('sname', [('m1', cint_type)])

    def test_eq_onDifferentMemberOrder_returnsFalse(self, cint_type, cint16_type):
        return cdm.CStructType('sname', [('m1', cint16_type),
                                         ('m2', cint_type)])\
               != cdm.CStructType('sname', [('m1', cint_type),
                                            ('m2', cint16_type)])\


    def test_eq_onNestedStructsWithDifferentInnerStruct_returnsFalse(self, cint_type, cint16_type):
        inner1_cstruct_type = cdm.CStructType('inner1', [('m', cint_type)])
        outer1_cstruct_type = cdm.CStructType('outer',
                                              [('m', inner1_cstruct_type)])
        inner2_cstruct_type = cdm.CStructType('inner2', [('m', cint16_type)])
        outer2_cstruct_type = cdm.CStructType('outer',
                                              [('m', inner2_cstruct_type)])
        assert outer1_cstruct_type != outer2_cstruct_type

    def test_eq_onRecursiveStructs_avoidEndlessRecursion(self):
        recur_cstruct1_type = cdm.CStructType('recur_cstruct_type')
        recur_cstruct1_type.delayed_def([('nested', recur_cstruct1_type.ptr)])
        recur_cstruct2_type = cdm.CStructType('recur_cstruct_type')
        recur_cstruct2_type.delayed_def([('nested', recur_cstruct2_type.ptr)])
        assert recur_cstruct1_type == recur_cstruct2_type

    def test_repr_ok(self):
        cstruct_type = cdm.CStructType('strct_type').with_attr('attr')
        assert repr(cstruct_type) == 'ts.struct.attr_strct_type'


class TestCStruct:

    def test_init_fromCTypes_returnsWrappedCTypesObj(self, cstruct_type):
        ctypes_struct = cstruct_type.ctypes_type()
        cstruct_obj = cdm.CStruct(cstruct_type, ctypes_struct)
        assert cstruct_obj.ctypes_obj is ctypes_struct

    def test_init_fromNoParam_intializesMembersWithDefaults(self, cstruct_type):
        cstruct_obj = cdm.CStruct(cstruct_type)
        assert cstruct_obj.ctypes_obj.member_int == 0

    def test_init_fromPositionalParams_initializesMembers(self, cstruct_type):
        cstruct_obj = cstruct_type(111111, 222)
        assert cstruct_obj.ctypes_obj.member_int == 111111
        assert cstruct_obj.ctypes_obj.member_short == 222

    def test_init_fromKeywordArgs_initializesMembers(self, cstruct_type):
        cstruct_obj = cstruct_type(member_short=222, member_int=111111)
        assert cstruct_obj.ctypes_obj.member_int == 111111
        assert cstruct_obj.ctypes_obj.member_short == 222

    def test_init_fromPositionalAndKeywordArgs_initializesMembers(self, cstruct_type):
        cstruct_obj = cstruct_type(111111, member_short=222)
        assert cstruct_obj.ctypes_obj.member_int == 111111
        assert cstruct_obj.ctypes_obj.member_short == 222

    def test_getVal_returnsDictOfVals(self, cstruct_type):
        cstruct_obj = cstruct_type(1, 2)
        assert cstruct_obj.val\
               == {'member_int':1, 'member_short':2, 'member_int2':0}

    def test_getVal_onNestedStruct_ok(self, cstruct_type, cint_type):
        nested_cstruct_obj = cdm.CStructType(
            'nested_cstruct_obj',
            members=[('struct', cstruct_type),
                     ('int', cint_type)])
        nested_struct = nested_cstruct_obj(
            struct={'member_int':2, 'member_short':99},
            int=888)
        assert nested_struct.val == \
               {'struct':{'member_int':2,
                          'member_short':99,
                          'member_int2':0},
                'int':888}

    def test_setVal_onDict_changesMembers(self, cstruct_type):
        cstruct_obj = cstruct_type(member_int2=99)
        cstruct_obj.val = {'member_int':1, 'member_short':2}
        assert cstruct_obj.val \
               == {'member_int':1, 'member_short':2, 'member_int2':0}

    @pytest.mark.parametrize('seq', [b'\x11\x22', (0x11, 0x22),
                                     iter([0x11, 0x22])])
    def test_setVal_onSequence_changesMembers(self, seq, cstruct_type):
        cstruct_obj = cstruct_type(member_int2=99)
        cstruct_obj.val = seq
        assert cstruct_obj.val \
               == {'member_int':0x11, 'member_short':0x22, 'member_int2':0}

    def test_getTuple_returnsTupleOfVals(self, cstruct_type):
        cstruct_obj = cstruct_type(1, 2, 3)
        assert cstruct_obj.tuple == (1, 2, 3)

    def test_setTuple_onIterable_changesMembers(self, cstruct_type):
        struct = cstruct_type(member_int2=99)
        struct.tuple = (1, 2)
        assert struct.val == {'member_int':1, 'member_short':2, 'member_int2':0}

    def test_setTuple_onTooLong_raisesValueError(self, cstruct_type):
        cstruct_obj = cstruct_type()
        with pytest.raises(ValueError):
            cstruct_obj.tuple = range(4)

    def test_getItem_onStrings_returnsPyObjOfMember(self, cstruct_type, cint_type, cint16_type):
        cstruct_obj = cstruct_type(111111, 222, 3)
        member_cint_obj = cstruct_obj['member_int']
        assert member_cint_obj.cobj_type == cint_type
        assert member_cint_obj.adr.val == cstruct_obj.adr.val
        assert member_cint_obj.val == 111111
        member_cshort_obj = cstruct_obj['member_short']
        assert member_cshort_obj.cobj_type == cint16_type
        assert member_cshort_obj.adr.val > cstruct_obj.adr.val
        assert member_cshort_obj.val == 222
        member_cint2_obj = cstruct_obj['member_int2']
        assert member_cint2_obj.cobj_type == cint_type
        assert member_cint2_obj.adr.val > cstruct_obj.adr.val
        assert member_cint2_obj.val == 3

    def test_getItem_onIndex_returnsPyObjOfMembers(self, cstruct_type):
        cstruct_obj = cstruct_type()
        assert cstruct_obj[0].adr == cstruct_obj['member_int'].adr
        assert cstruct_obj[1].adr == cstruct_obj['member_short'].adr

    def test_len_returnsNumberOfMembers(self, cstruct_type):
        cstruct_obj = cstruct_type()
        assert len(cstruct_obj) == 3

    def test_iter_returnsMembersInOrder(self, cstruct_type):
        cstruct_obj = cstruct_type()
        assert list(iter(cstruct_obj)) \
               == [cstruct_obj.member_int, cstruct_obj.member_short,
                   cstruct_obj.member_int2]

    def test_GetAttr_onStructMemberName_createsPyObjOfMember(self, cstruct_type):
        cstruct_obj = cstruct_type()
        assert cstruct_obj.member_int.adr == cstruct_obj['member_int'].adr
        assert cstruct_obj.member_short.adr == cstruct_obj['member_short'].adr

    @pytest.mark.parametrize('name', ['mem', 'val', 'adr', 'tuple', 'sizeof',
                                      'cobj_type'])
    def test_GetAttr_OnStructMemberWithReservedName_returnsReservedObj(self, name, cint_type):
        cstruct_type = cdm.CStructType(
            'StructWithReservedMemberNames',
            members=[(name, cint_type)])
        cstruct_obj = cstruct_type(123)
        assert getattr(cstruct_obj, name) != 123

    def test_GetAttr_onNotExistingName_raisesAttributeError(self, cstruct_type):
        struct = cstruct_type()
        with pytest.raises(AttributeError):
            _ = struct.invalid_name

    def test_repr_returnsMembersAsKeywords(self, cstruct_type):
        struct = cstruct_type(member_int=1, member_short=2, member_int2=3)
        assert repr(struct) == \
               'ts.struct.strct_name(member_int=1, member_short=2, ' \
               'member_int2=3)'


@pytest.fixture
def cfunc_type():
    return cdm.CFuncType()


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

    @patch.object(cdm.CFuncType, 'COBJ_CLASS')
    def test_call_withLoggerKeyword_passesLoggerToCFunc(self, COBJ_CLASS):
        cfunc_type = cdm.CFuncType()
        logger = Mock()
        func = Mock()
        cfunc_obj = cfunc_type(func, logger=logger)
        assert cfunc_obj is COBJ_CLASS.return_value
        COBJ_CLASS.assert_called_with(cfunc_type, func, None, logger=logger)


@pytest.fixture
def cfunc_obj(cfunc_type):
    return cfunc_type(lambda:None)

@pytest.fixture
def abs_cfunc_obj(cint_type):
    abs_cfunc_type = cdm.CFuncType(cint_type, [cint_type])
    return abs_cfunc_type(ct.cdll.msvcrt.abs)

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

    def test_init_fromCtypesObj_ok(self, abs_cfunc_obj):
        assert abs_cfunc_obj.pyfunc is None
        assert abs_cfunc_obj.ctypes_obj is ct.cdll.msvcrt.abs
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

    def test_call_onCObjs_ok(self, cint_type, cint16_type):
        @cdm.CFuncType(None, [cint_type, cint16_type])
        def cfunc_obj(*args):
            assert args == (12, 34)
        cfunc_obj(cint_type(12), cint16_type(34))

    def test_call_onPyObjs_convertsArgsToCObj(self, cint_type, cint16_type):
        @cdm.CFuncType(None, [cint_type, cint16_type])
        def cfunc_obj(p1, p2):
            assert p1.cobj_type.bits == 32 and p2.cobj_type.bits == 16
            assert p1.val == 12 and  p2.val == 34
        cfunc_obj(12, 34)

    def test_call_onResult_returnsCObj(self, cint_type):
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
        ctypes_ptr = ct.cast(ct.pointer(cfunc_obj.ctypes_obj),
                             ct.POINTER(ct.c_int))
        cfuncptr_type.assert_called_with(ctypes_ptr.contents.value,
                                         _depends_on_=cfunc_obj)

    @patch.object(cdm, 'CFuncPointerType')
    def test_getAdr_onCFunc_returnsCFuncPointer(self, CFuncPointerType, abs_cfunc_obj):
        cfuncptr_type = CFuncPointerType.return_value
        cfuncptr_obj = abs_cfunc_obj.adr
        assert cfuncptr_obj == cfuncptr_type.return_value
        ctypes_ptr = ct.cast(ct.pointer(abs_cfunc_obj.ctypes_obj),
                             ct.POINTER(ct.c_int))
        cfuncptr_type.assert_called_with(ctypes_ptr.contents.value,
                                         _depends_on_=abs_cfunc_obj)


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


class TestCVoidType:

    def test_cDefintion_onConstAttr_returnsConstAttr(self):
        const_void = cdm.CVoidType().with_attr('const')
        assert const_void.c_definition('x') == 'const void x'

    def test_getMem_returnsCRawAccessWithMaxSizeNone(self):
        buf = ct.create_string_buffer(10)
        cvoidptr_obj = cdm.CVoidType().ptr(ct.addressof(buf))
        assert cvoidptr_obj.ref.mem.max_size is None
        assert cvoidptr_obj.ref.mem.addr == ct.addressof(buf)

    def test_allocPtr_allocatesBytewise(self):
        cvoidptr_obj = cdm.CVoidType().alloc_ptr([1, 2, 3])
        assert cvoidptr_obj.ref.mem == [1, 2, 3]

    def test_ptr_onIterable_allocatesBlockBytewise(self):
        void_ptr = cdm.CVoidType().ptr([1, 2, 3])
        assert void_ptr.ref.mem == [1, 2, 3]

    def test_eq_onVoid_returnsTrue(self):
        assert cdm.CVoidType() == cdm.CVoidType()