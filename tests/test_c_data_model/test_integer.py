import pytest
import ctypes as ct

import headlock.c_data_model as cdm



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


