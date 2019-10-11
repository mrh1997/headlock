import pytest
from contextlib import contextmanager
from unittest.mock import Mock, patch

import headlock.c_data_model as cdm
from headlock.address_space.virtual import VirtualAddressSpace


@pytest.fixture
def cptr_type(cint_type, addrspace):
    return cdm.CPointerType(cint_type, 32, 'big', addrspace)


class TestCPointerType:

    @pytest.mark.parametrize(('endianess', 'wordsize'), [
        ('little', 32), ('little', 64), ('big', 32)])
    def test_init_onPtrType_returnsInitializedPointerObj(self, unbound_cint_type, addrspace, endianess, wordsize):
        cptr_type = cdm.CPointerType(unbound_cint_type, wordsize, endianess)
        assert cptr_type.base_type is unbound_cint_type
        assert cptr_type.sizeof == wordsize // 8
        assert cptr_type.endianess == endianess

    def test_init_onBaseTypeWithDifferentAddrSpaceSet_raisesInvalidAddressSpaceError(self, cint_type):
        with pytest.raises(cdm.InvalidAddressSpaceError):
            _ = cdm.CPointerType(cint_type, 32, 'little', VirtualAddressSpace())

    def test_bind_bindsAlsoBaseType(self, addrspace, unbound_cint_type):
        cptr_type = cdm.CPointerType(
            unbound_cint_type, 32, 'little')
        bound_cptr_type = cptr_type.bind(addrspace)
        assert bound_cptr_type.base_type.__addrspace__ is not None

    def test_shallowIterSubTypes_onNotEmbeddedDefsOnlyIsFalse_returnsReferredTypeElementaryTypes(self, cptr_type):
        assert list(cptr_type.shallow_iter_subtypes()) \
               == [cptr_type.base_type]

    def test_eq_onSamePointer_returnsTrue(self, unbound_cint_type):
        assert cdm.CPointerType(unbound_cint_type, 32, 'little') \
               == cdm.CPointerType(unbound_cint_type, 32, 'little')

    @pytest.mark.parametrize('diff_cptr_type', [
        cdm.CPointerType(cdm.CIntType('other',16, True, 'little'), 32, 'little'),
        cdm.CPointerType(cdm.CIntType('base', 32, True, 'little'), 64, 'little'),
        cdm.CPointerType(cdm.CIntType('base', 32, True, 'little'), 32, 'big')])
    def test_eq_onDifferentPointer_returnsFalse(self, diff_cptr_type):
        basetype = cdm.CIntType('base', 32, True, 'little')
        assert cdm.CPointerType(basetype, 32, 'little') != diff_cptr_type

    def test_nullValue_ok(self, cptr_type):
        assert cptr_type.null_val == 0

    def test_cDefinition_onNoRefDef_returnsCNameWithoutRefDef(self, unbound_cint_type):
        assert unbound_cint_type.ptr.c_definition() == 'cint *'

    def test_cDefinition_onPtrToPtr_returnsTwoStars(self, unbound_cint_type):
        assert unbound_cint_type.ptr.ptr.c_definition() == 'cint **'

    def test_cDefinition_onPtrToArray_returnsParentethizedStar(self, unbound_cint_type):
        assert unbound_cint_type.array(10).ptr.c_definition() == 'cint (*)[10]'

    def test_cDefinition_onArrayOfPtrs_returnsUnParentethizedStar(self, unbound_cint_type):
        assert unbound_cint_type.ptr.array(10).c_definition() == 'cint *[10]'

    def test_cDefinition_onRefDef_returnsCNameWithRefDef(self, unbound_cint_type):
        assert unbound_cint_type.ptr.c_definition('ab') == 'cint *ab'

    def test_repr_returnsBaseNamePlusPtr(self, unbound_cint_type):
        cptr_type = cdm.CPointerType(unbound_cint_type, 32, 'little').with_attr('attr')
        assert repr(cptr_type) == 'ts.cint_attr_ptr'

    def test_convertFromCRepr_returnsAddressOfReferredObj(self, cptr_type):
        assert cptr_type.convert_from_c_repr(b'\x12\x34\x56\x78') == 0x12345678

    @pytest.mark.parametrize(('bitsize', 'endianess', 'expected_val'), [
        (32, 'little', b'\x21\x43\x65\x87'),
        (16, 'little', b'\x21\x43'),
        (32, 'big',    b'\x87\x65\x43\x21')])
    def test_convertToCRepr_onInt_returnsCRepr(self, bitsize, endianess, expected_val, cint_type, addrspace):
        cptr_type = cdm.CPointerType(cint_type, bitsize, endianess, addrspace)
        assert cptr_type.convert_to_c_repr(0x87654321) == expected_val

    def test_convertToCRepr_onIterable_allocatesPtrAndCastsIt(self, cptr_type, addrspace):
        init_val = Mock(spec=list)
        cptr_type.base_type.alloc_ptr = alloc_ptr = Mock()
        alloc_ptr.return_value.val = 0x123
        assert cptr_type.convert_to_c_repr(init_val) == b'\x00\x00\x01\x23'
        alloc_ptr.assert_called_once_with(init_val)

    def test_convertToCRepr_onCArray_setsAddressOfArray(self, cptr_type, cint_type):
        int_arr = cint_type.alloc_array(3)
        assert cptr_type.convert_to_c_repr(int_arr) \
               == int_arr.__address__.to_bytes(4, 'big')

    @pytest.mark.parametrize(('bitsize', 'endianess', 'c_repr', 'py_val'), [
        (32, 'little', b'\x78\x56\x34\x12', 0x12345678),
        (16, 'little', b'\x34\x12',         0x1234),
        (32, 'big',    b'\x12\x34\x56\x78', 0x12345678)])
    def test_convertFromCRepr_returnsCRepr(self, bitsize, endianess, c_repr, py_val, cint_type, addrspace):
        cptr_type = cdm.CPointerType(cint_type, bitsize, endianess, addrspace)
        assert cptr_type.convert_from_c_repr(c_repr) == py_val

    @pytest.mark.parametrize('size', [4, 8])
    def test_getAlignment_returnsSizeof(self, size, unbound_cint_type):
        cptr_type = cdm.CPointerType(unbound_cint_type, size*8, 'little')
        assert cptr_type.alignment == size


class TestCPointer:

    def test_getRef_returnsCorrectTypeWithCorrectAddress(self, cptr_type, addrspace):
        adr = addrspace.alloc_memory(1)
        cptr_obj = cptr_type(adr)
        ref_cobj = cptr_obj.ref
        assert ref_cobj.__address__ == adr
        assert ref_cobj.ctype == cptr_obj.base_type

    @contextmanager
    def cptr_to_array_of(self, val_list):
        addrspace = VirtualAddressSpace(b'some-data')
        cptr_type = cdm.CPointerType(
            cdm.CIntType('i32', 32, False, 'little', addrspace),
            32, 'little', addrspace)
        adr = addrspace.alloc_memory(len(val_list) * 4)
        addrspace.write_memory(
            adr,
            b''.join(v.to_bytes(4, 'little') for v in val_list))
        yield cptr_type(adr)
        content = addrspace.read_memory(adr, len(val_list) * 4)
        for ndx in range(len(val_list)):
            val_list[ndx] = int.from_bytes(content[ndx*4:ndx*4+4], 'little')

    def test_getItem_onInt_returnsCProxyOfReferredAddress(self):
        with self.cptr_to_array_of([0, 11, 22]) as cptr_obj:
            assert cptr_obj[2].ctype == cptr_obj.ref.ctype
            assert cptr_obj[2].val == 22

    def test_getItem_onSlice_returnsPyArrayOfCProxies(self):
        with self.cptr_to_array_of([0, 11, 22, 33]) as cptr_obj:
            array = cptr_obj[1:3]
            assert array.base_type == cptr_obj.base_type
            assert array.element_count == 2
            assert array.__address__ == cptr_obj[1].__address__

    def test_getItem_onSliceWithStep_raisesValueError(self):
        with self.cptr_to_array_of([0, 11, 22]) as cptr_obj:
            with pytest.raises(ValueError):
                _ = cptr_obj[0:3:2]

    def test_int_returnsAddress(self, cptr_type):
        cptr_obj = cptr_type(0x12345678)
        assert int(cptr_obj) == 0x12345678

    def test_getUnicodeStr_onZeroTerminatedStr_returnsPyString(self):
        with self.cptr_to_array_of([0x1234, 0x56, 0]) as cptr_obj:
            assert cptr_obj.unicode_str == '\u1234\x56'

    def test_setUnicodeStr_onPyStr_changesArrayToZeroTerminatedString(self):
        ref_data = [111] * 6
        with self.cptr_to_array_of(ref_data) as cptr_obj:
            cptr_obj.unicode_str = '\u1234\x56\0\x78'
        assert ref_data[:6] == [0x1234, 0x56, 0, 0x78, 0, 111]

    def test_getCStr_onZeroTerminatedStr_returnsBytes(self):
        with self.cptr_to_array_of([ord('X'), ord('y'), 0]) as cptr_obj:
            assert cptr_obj.c_str == b'Xy'

    def test_setCStr_onPyStr_changesArrayToZeroTerminatedString(self):
        ref_data = [111] * 6
        with self.cptr_to_array_of(ref_data) as cptr_obj:
            cptr_obj.c_str = b'Xy\0z'
        assert ref_data[:6] == [ord('X'), ord('y'), 0, ord('z'), 0, 111]

    def test_add_returnsNewPointerAtIncrementedAddress(self):
        with self.cptr_to_array_of([0] * 100) as cptr_obj:
            moved_cptr_obj = cptr_obj + 100
            assert moved_cptr_obj.val \
                   == cptr_obj.val + 100 * cptr_obj.ref.sizeof

    def test_add_onCInt_ok(self, cint_type):
        inc_cint_obj = cint_type(100)
        with self.cptr_to_array_of([0] * 100) as cptr_obj:
            moved_cptr_obj = cptr_obj + inc_cint_obj
            assert moved_cptr_obj.val \
                   == cptr_obj.val + 100 * cptr_obj.ref.sizeof

    def test_sub_returnsNewPointerAtDecrementedAddress(self):
        with self.cptr_to_array_of([0] * 100) as cptr_obj:
            end_cptr_obj = cptr_obj + 100
            moved_cptr_obj = end_cptr_obj - 70
            assert moved_cptr_obj.val \
                   == end_cptr_obj.val - 70 * cptr_obj.ref.sizeof

    def test_sub_onCPointer_returnsNumberOfElementsInBetween(self):
        with self.cptr_to_array_of([0] * 100) as cptr_obj:
            end_cptr_obj = cptr_obj + 100
            diff_cproxy_obj = end_cptr_obj - cptr_obj
            assert isinstance(diff_cproxy_obj, int)
            assert diff_cproxy_obj == 100

    def test_sub_onCPointerOfDifferrentType_raisesTypeError(self):
        cptr_type1 = cdm.CPointerType(cdm.CIntType('name1', 32, True, 'little'),
                                      32, 'little')
        cptr_type2 = cdm.CPointerType(cdm.CIntType('name2', 32, True, 'little'),
                                      32, 'little')
        cptr_obj1 = cdm.CPointer(cptr_type1, 0)
        cptr_obj2 = cdm.CPointer(cptr_type2, 0)
        with pytest.raises(TypeError):
            _ = cptr_obj2 - cptr_obj1

    def test_sub_onCArray_returnsNumberOfElementsInBetween(self, cptr_type, cint_type, addrspace):
        mem_block = addrspace.alloc_memory(cint_type.sizeof * 3)
        cobj0 = cdm.CPointer(cptr_type, mem_block)
        cobj2 = cdm.CPointer(cptr_type, mem_block + cint_type.sizeof * 2)
        assert cobj2.adr - cobj0.adr == 2
        assert isinstance(cobj2.adr - cobj0.adr, int)

    def test_sub_onCInt_ok(self, cint_type):
        with self.cptr_to_array_of([0] * 100) as cptr_obj:
            cint_obj = cint_type(100)
            moved_cptr_obj = cptr_obj + 100 - cint_obj
        assert moved_cptr_obj.val == cptr_obj.val

    def test_getItem_onNdx_returnsCProxyAtNdx(self):
        with self.cptr_to_array_of([0x11, 0x22, 0x33]) as cptr_obj:
            assert cptr_obj[2].__address__ \
                   == cptr_obj.val + cptr_obj.base_type.sizeof*2

    def test_getItem_onSlice_returnsCArrayOfCProxyAtSlice(self):
        with self.cptr_to_array_of([0x11, 0x22, 0x33, 0x44]) as cptr_obj:
            carray_obj = cptr_obj[1:3]
            assert isinstance(carray_obj, cdm.CArray)
            assert carray_obj.base_type is cptr_obj.base_type
            assert carray_obj.__address__ == cptr_obj[1].__address__

    def test_repr_returnsClassNameAndHexValue(self, cptr_type):
        ptr = cptr_type(1234).adr
        ptr_digits = cdm.MACHINE_WORDSIZE // 4
        assert repr(ptr) == f'ts.cint_ptr_ptr(0x{ptr.val:0{ptr_digits}X})'
