import pytest
import ctypes as ct
from contextlib import contextmanager
from unittest.mock import Mock, MagicMock

import headlock.c_data_model as cdm



@pytest.fixture
def cptr_type(cint_type):
    return cdm.CPointerType(cint_type)


class TestCPointerType:

    def test_init_onPtrType_returnsInitializedPointerObj(self):
        ctype = Mock()
        ctypes_type = Mock()
        cptr_type = cdm.CPointerType(ctype, ctypes_type)
        assert cptr_type.base_type is ctype
        assert cptr_type.ctypes_type is ctypes_type

    def test_init_onDefaultParams_ok(self):
        ctype = Mock()
        ctype.ctypes_type = ct.c_float
        ctype.c_name = 'base_type_name'
        cptr_type = cdm.CPointerType(ctype)
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
        ctype = MagicMock()
        ctype.__repr__ = Mock(return_value='ts.basetype')
        ctype.ctypes_type = ct.c_int
        cptr_type = cdm.CPointerType(ctype).with_attr('attr')
        assert repr(cptr_type) == 'ts.basetype_attr_ptr'


class TestCPointer:

    def test_init_fromCTypes_returnsWrapperAroundCTypesObj(self, cptr_type):
        ctypes_ptr = ct.pointer(ct.c_uint32(999))
        cptr_obj = cptr_type(ctypes_ptr)
        assert cptr_obj.ctypes_obj is ctypes_ptr

    def test_init_fromPyInt_returnsPtrObjReferingGivenAddress(self, cptr_type):
        cptr_obj = cptr_type(999)
        assert ct.addressof(cptr_obj.ctypes_obj.contents) == 999

    def test_init_fromCInt_returnsPtrToSpecifiedAdrVal(self, cptr_type, cuint64_type):
        ctypes_int = ct.c_int8()
        cint_obj = cuint64_type(ct.addressof(ctypes_int))
        cptr_obj = cdm.CPointer(cptr_type, cint_obj)
        assert ct.addressof(cptr_obj.ctypes_obj.contents) == cint_obj.val

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
        ref_cproxy = cptr_obj.ref
        assert ct.addressof(ref_cproxy.ctypes_obj) == ref_adr
        assert ref_cproxy.ctype == cptr_obj.base_type

    def test_add_returnsNewPointerAtIncrementedAddress(self):
        with self.cptr_to_list([0] * 100) as cptr_obj:
            moved_cptr_obj = cptr_obj + 100
            assert moved_cptr_obj.val \
                   == cptr_obj.val + 100 * cptr_obj.ref.sizeof

    def test_add_onCInt_ok(self, cint_type):
        inc_cint_obj = cint_type(100)
        with self.cptr_to_list([0] * 100) as cptr_obj:
            moved_cptr_obj = cptr_obj + inc_cint_obj
            assert moved_cptr_obj.val \
                   == cptr_obj.val + 100 * cptr_obj.ref.sizeof

    def test_sub_returnsNewPointerAtDecrementedAddress(self):
        with self.cptr_to_list([0] * 100) as cptr_obj:
            end_cptr_obj = cptr_obj + 100
            moved_cptr_obj = end_cptr_obj - 70
            assert moved_cptr_obj.val \
                   == end_cptr_obj.val - 70 * cptr_obj.ref.sizeof

    def test_sub_onCPointer_returnsNumberOfElementsInBetween(self):
        with self.cptr_to_list([0] * 100) as cptr_obj:
            end_cptr_obj = cptr_obj + 100
            diff_cproxy_obj = end_cptr_obj - cptr_obj
            assert isinstance(diff_cproxy_obj, int)
            assert diff_cproxy_obj == 100

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

    def test_getItem_onNdx_returnsCProxyAtNdx(self):
        with self.cptr_to_list([0x11, 0x22, 0x33]) as cptr_obj:
            assert cptr_obj[1].val == 0x22

    def test_getItem_onSlice_returnsCArrayOfCProxyAtSlice(self):
        with self.cptr_to_list([0x11, 0x22, 0x33, 0x44]) as cptr_obj:
            carray_obj = cptr_obj[1:3]
            assert isinstance(carray_obj, cdm.CArray)
            assert carray_obj.val == [0x22, 0x33]

    def test_repr_returnsClassNameAndHexValue(self, cptr_type):
        ptr = cdm.CPointer(cptr_type, 1234, None).adr
        assert repr(ptr) == f'ts.typename_ptr_ptr(0x{ptr.val:08X})'


