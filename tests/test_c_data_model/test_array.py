import pytest
import ctypes as ct
from unittest.mock import patch, Mock, MagicMock

import headlock.c_data_model as cdm



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
        carray_obj = self.create_int_carray_obj(8, [0x11] * 32)
        added_cobj = carray_obj + 3
        assert isinstance(added_cobj, cdm.CPointer)
        assert added_cobj.val == self.adr_of(carray_obj[3])

    def test_repr_returnsClassNameAndContent(self, cint_type):
        carray_type = cdm.CArrayType(cint_type, 3)
        carray_obj = carray_type([1, 2, 3])
        assert repr(carray_obj) == 'ts.typename_array3([1, 2, 3])'

    def test_iter_returnsIterOfElements(self):
        data = [0x11, 0x22, 0x33, 0x44]
        carray_obj = self.create_int_carray_obj(8, data)
        assert list(iter(carray_obj)) == data
