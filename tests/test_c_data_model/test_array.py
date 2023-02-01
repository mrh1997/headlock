import pytest
from unittest.mock import patch

import headlock.c_data_model as cdm
from headlock.address_space.virtual import VirtualAddressSpace
from time import time


@pytest.fixture
def carray_type(cint_type, addrspace):
    return cdm.CArrayType(cint_type, 10, addrspace)


class TestCArrayType:

    def test_init_returnsArrayCProxy(self, unbound_cint_type):
        carray_type = cdm.CArrayType(unbound_cint_type, 10)
        assert carray_type.__addrspace__ is None
        assert carray_type.base_type is unbound_cint_type
        assert carray_type.element_count == 10

    def test_init_onBaseTypeWithDifferentAddrSpaceSet_raisesInvalidAddressSpace(self, cint_type):
        other_addrspace = VirtualAddressSpace()
        with pytest.raises(cdm.InvalidAddressSpaceError):
            _ = cdm.CArrayType(cint_type, 10, other_addrspace)

    def test_bind_bindsAlsoBaseElement(self, addrspace):
        ctype = cdm.CProxyType(1)
        carray_type = cdm.CArrayType(ctype, 10)
        bound_carray_type = carray_type.bind(addrspace)
        assert bound_carray_type.base_type.__addrspace__ is addrspace

    def test_shallowIterSubTypes_returnsBaseType(self, carray_type):
        assert list(carray_type.shallow_iter_subtypes()) \
               == [carray_type.base_type]

    def test_eq_onSamePointer_returnsTrue(self, cint_type):
        assert cdm.CPointerType(cint_type, 32, 'little') \
               == cdm.CPointerType(cint_type, 32, 'little')

    @pytest.mark.parametrize('diff_carr_type', [
        "othertype",
        cdm.CArrayType(cdm.CIntType('x', 32, True, cdm.ENDIANESS), 10)
                             .with_attr('attr'),
        cdm.CArrayType(cdm.CIntType('x', 32, True, cdm.ENDIANESS), 1000),
        cdm.CArrayType(cdm.CIntType('y', 16, False, cdm.ENDIANESS), 10)])
    def test_eq_onSamePointer_returnsTrue(self, diff_carr_type):
        basetype = cdm.CIntType('x', 32, True, cdm.ENDIANESS)
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
        assert cint_type.array(12).c_definition('x') == 'cint x[12]'

    def test_cDefinition_onNoRefDef_returnsWithoutRefDef(self, cint_type):
        assert cint_type.array(12).c_definition() == 'cint [12]'

    def test_cDefinition_onArrayOfArrays_ok(self, cint_type):
        assert cint_type.array(11).array(22).c_definition() == 'cint [22][11]'

    def test_cDefinition_onArrayOfPtr_ok(self, cint_type):
        assert cint_type.ptr.array(10).c_definition('x') == 'cint *x[10]'

    def test_cDefinition_onPtrToArray_ok(self, cint_type):
        assert cint_type.array(10).ptr.c_definition('x') == 'cint (*x)[10]'

    def test_repr_returnsBaseNamePlusArray(self, unbound_cint_type):
        cptr_type = cdm.CArrayType(unbound_cint_type, 123).with_attr('attr')
        assert repr(cptr_type) == 'ts.cint_attr_array123'

    def test_convertToCRepr_onPyIterable_initializesElementsWithIterablePlusNullVals(self):
        carray_type = cdm.CArrayType(cdm.CIntType('i', 32, False, 'big'), 5)
        c_repr = carray_type.convert_to_c_repr([0x11, 0x22, 0x33445566])
        assert c_repr == b'\x00\x00\x00\x11\x00\x00\x00\x22\x33\x44\x55\x66' \
                         b'\x00\x00\x00\x00\x00\x00\x00\x00'

    def test_convertToCRepr_onUtf8WithBigCodepoint_returnsArrayOfCorrectSize(self):
        carray_type = cdm.CArrayType(cdm.CIntType('i', 32, False, 'big'), 4)
        c_repr = carray_type.convert_to_c_repr('A\u1122')
        assert c_repr == b'\x00\x00\x00\x41\x00\x00\x11\x22' \
                         b'\x00\x00\x00\x00\x00\x00\x00\x00'

    def test_convertFromCRepr_returnsArrayOfCorrectSize(self):
        carray_type = cdm.CArrayType(cdm.CIntType('i', 32, False, 'big'), 5)
        py_repr = carray_type.convert_from_c_repr(
            b'\x00\x00\x00\x11\x00\x00\x00\x22\x33\x44\x55\x66')
        assert py_repr == [0x11, 0x22, 0x33445566, 0, 0]

    def test_init_onConstArray_ok(self, cint_type):
        carray_type = cint_type.with_attr('const').array(1)
        _ = carray_type()

    @pytest.mark.parametrize('size', [1, 4])
    def test_getAlignment_returnsAlignmentOfBase(self, size, unbound_cint_type):
        with patch.object(cdm.CIntType, 'alignment', size):
            carray_type = cdm.CArrayType(unbound_cint_type, 4)
            assert carray_type.alignment == size


class TestCArray:

    def create_int_carray_obj(self, bits, init_val):
        cint_type = cdm.CIntType('i'+str(bits), bits, False, cdm.ENDIANESS)
        if isinstance(init_val, int):
            content = b'\00' * (bits//8 * init_val)
            size = init_val
        else:
            content = b''.join(map(cint_type.convert_to_c_repr, init_val))
            size = len(init_val)
        addrspace = VirtualAddressSpace(content)
        carray_type = cdm.CArrayType(cint_type.bind(addrspace), size, addrspace)
        return cdm.CArray(carray_type, 0)

    def test_str_returnsStringWithZeros(self):
        test_vector = [ord('x'), ord('Y'), 0]
        carray_obj = self.create_int_carray_obj(16, test_vector)
        assert str(carray_obj) == 'xY\0'

    def test_getCStr_onZeroTerminatedStr_returnsBytes(self):
        test_vector = [ord('X'), ord('y'), 0]
        carray_obj = self.create_int_carray_obj(16, test_vector)
        assert carray_obj.c_str == b'Xy'

    def test_setCStr_onPyStr_changesArrayToZeroTerminatedString(self):
        carray_obj = self.create_int_carray_obj(16, [111]*6)
        carray_obj.c_str = 'Xy\0z'
        assert carray_obj.val == [ord('X'), ord('y'), 0, ord('z'), 0, 0]

    def test_setCStr_onTooLongPyStr_raisesValueError(self):
        array = self.create_int_carray_obj(16, [111] * 3)
        with pytest.raises(ValueError):
            array.c_str = 'Xyz'

    def test_getUnicodeStr_onZeroTerminatedStr_returnsPyString(self):
        test_vector = [0x1234, 0x56, 0]
        carray_obj = self.create_int_carray_obj(16, test_vector)
        assert carray_obj.unicode_str == '\u1234\x56'

    def test_setUnicodeStr_onPyStr_changesArrayToZeroTerminatedString(self):
        carray_obj = self.create_int_carray_obj(16, [111] * 6)
        carray_obj.unicode_str = '\u1234\x56\0\x78'
        assert carray_obj.val == [0x1234, 0x56, 0, 0x78, 0, 0]

    def test_init_onVeryBigBytesObject_providesOptimizedImplementation(self):
        big_array_size = 1000000
        array = self.create_int_carray_obj(8, big_array_size+1)
        start_timestamp = time()
        array.ctype(b'\x00' * big_array_size)
        assert time() - start_timestamp < 0.050

    def test_setVal_onComplexStructure_convertsBaseType(self):
        array = self.create_int_carray_obj(32, 2)
        array.val = [0x01234567, 0x89ABCDEF]
        assert array.val == [0x01234567, 0x89ABCDEF]

    def test_setVal_onVeryBigBytesObject_providesOptimizedImplementation(self):
        big_array_size = 1000000
        array = self.create_int_carray_obj(8, big_array_size+1)
        start_timestamp = time()
        array.val = b'\x00' * big_array_size
        assert time() - start_timestamp < 0.050

    def test_getVal_onComplexStructure_convertsBaseType(self):
        array = self.create_int_carray_obj(32, [0x01234567, 0x89ABCDEF])
        assert array.val == [0x01234567, 0x89ABCDEF]

    def test_getItem_returnsObjectAtNdx(self):
        carray_obj = self.create_int_carray_obj(16, [1, 2, 3, 4])
        assert carray_obj[2].__address__ \
               == carray_obj.__address__ + 2*carray_obj.base_type.sizeof

    def test_getItem_onNegativeIndex_returnsElementFromEnd(self):
        carray_obj = self.create_int_carray_obj(16, [0]*5)
        assert carray_obj[-2].__address__ == carray_obj[3].__address__

    def test_getItem_onSlice_returnsSubArray(self):
        carray_obj = self.create_int_carray_obj(16, [1, 2, 3, 4])
        sliced_carray_obj = carray_obj[1:3]
        assert isinstance(sliced_carray_obj, cdm.CArray)
        assert sliced_carray_obj.base_type == carray_obj.base_type
        assert sliced_carray_obj.__address__ == carray_obj[1].__address__
        assert sliced_carray_obj.element_count == 2

    def test_getItem_onSliceWithSteps_raiseValueError(self):
        carray_obj = self.create_int_carray_obj(16, [1, 2, 3, 4])
        with pytest.raises(ValueError):
            _ = carray_obj[0:4:2]

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
        carray_obj = self.create_int_carray_obj(8, [0x11] * 32)
        added_cproxy = carray_obj + 3
        assert isinstance(added_cproxy, cdm.CPointer)
        assert added_cproxy.val == carray_obj[3].__address__

    def test_repr_returnsClassNameAndContent(self, cint_type, addrspace):
        carray_type = cdm.CArrayType(cint_type, 3, addrspace)
        carray_obj = carray_type([1, 2, 3])
        assert repr(carray_obj) == 'ts.cint_array3([1, 2, 3])'

    def test_iter_returnsIterOfElements(self):
        data = [0x11, 0x22, 0x33, 0x44]
        carray_obj = self.create_int_carray_obj(8, data)
        assert list(iter(carray_obj)) == data
