import pytest
from unittest.mock import Mock

import headlock.c_data_model as cdm



class TestCIntType:

    def test_init_setsAttrs(self):
        addrspace = Mock()
        cint_type = cdm.CIntType('typename', 32, True, 'little', addrspace)
        assert cint_type.c_name == 'typename'
        assert cint_type.sizeof == 4
        assert cint_type.signed == True
        assert cint_type.endianess == 'little'
        assert cint_type.__addrspace__ is addrspace

    def test_cDefinition_returnsCName(self):
        cint_type = cdm.CIntType('typename', 32, True, 'little')
        assert cint_type.c_definition() == 'typename'

    def test_cDefinition_onRefDefIsSet_returnsWithRefDef(self):
        cint_type = cdm.CIntType('typename', 32, True, 'little')
        assert cint_type.c_definition('varname') == 'typename varname'

    @pytest.mark.parametrize('bits', [8, 32])
    def test_sizeof_returnsSizeInBytes(self, bits):
        cint_type = cdm.CIntType('typename', bits, True, 'little')
        assert cint_type.sizeof == bits // 8

    def test_nullVal_ok(self, cint_type):
        assert cint_type.null_val == 0

    def test_repr_withAttrAndSpaceInName_ok(self):
        cint_type = cdm.CIntType('type name', 32, True, 'little')
        attr_cint_type = cint_type.with_attr('attrB').with_attr('attrA')
        assert repr(attr_cint_type) == 'ts.attrA_attrB_type_name'

    def test_eq_inSameCIntType_returnsTrue(self):
        assert cdm.CIntType('name', 32, True, 'little') \
               == cdm.CIntType('name', 32, True, 'little')

    @pytest.mark.parametrize('diff_cint_type', [
        "othertype",
        cdm.CIntType('othername', 32, True, 'little'),
        cdm.CIntType('name', 32, True, 'little').with_attr('test'),
        cdm.CIntType('name', 16, True, 'little'),
        cdm.CIntType('name', 32, False, 'little'),
        cdm.CIntType('name', 32, True, 'big'),])
    def test_eq_inDifferentCIntType_returnsFalse(self, diff_cint_type):
        assert diff_cint_type != cdm.CIntType('name', 32, True, 'little')

    @pytest.mark.parametrize(('cint_type', 'expected_val'), [
        (cdm.CIntType('name', 32, False, 'little'), b'\x21\x43\x65\x87'),
        (cdm.CIntType('name', 16, False, 'little'), b'\x21\x43'),
        (cdm.CIntType('name', 32, False, 'big'),    b'\x87\x65\x43\x21')])
    def test_convertToCRepr_returnsCRepr(self, cint_type, expected_val):
        assert cint_type.convert_to_c_repr(0x87654321) == expected_val

    def test_convertToCRepr_onSignBitSetAndSigned_returnsNegativePyVal(self):
        signed_cint_type = cdm.CIntType('name', 32, True, 'little')
        assert signed_cint_type.convert_to_c_repr(-1) == b'\xFF\xFF\xFF\xFF'

    def test_convertToCRepr_onBytesOfSize1_setsAsciiCode(self, cint16_type):
        assert cint16_type.convert_to_c_repr(b'\x12') == b'\x12\x00'

    def test_convertToCRepr_onStrOfSize1_setsUnicodeCodepoint(self, cint_type):
        assert cint_type.convert_to_c_repr('\U00012345') == b'\x45\x23\x01\x00'

    def test_convertToCRepr_onOtherType_forwardsToBaseClass(self, cint_type):
        assert cint_type.convert_to_c_repr(None) == b'\x00\x00\x00\x00'

    @pytest.mark.parametrize(('cint_type', 'c_repr', 'py_val'), [
        (cdm.CIntType('name', 32, False, 'little'), b'\x78\x56\x34\x12', 0x12345678),
        (cdm.CIntType('name', 16, False, 'little'), b'\x34\x12',         0x1234),
        (cdm.CIntType('name', 32, False, 'big'),    b'\x12\x34\x56\x78', 0x12345678),
        (cdm.CIntType('name', 32, True,  'little'), b'\xFF\xFF\xFF\xFF', -1),
        (cdm.CIntType('name', 8,  True,  'little'), b'\x80',             -128)])
    def test_convertFromCRepr_returnsCRepr(self, cint_type, c_repr, py_val):
        assert cint_type.convert_from_c_repr(c_repr) == py_val

    @pytest.mark.parametrize('size', [1, 2, 4, 8])
    def test_getAlignment_returnsSizeof(self, size):
        cint_type = cdm.CIntType('name', size*8, False, 'little')
        assert cint_type.alignment == size


class TestCInt:

    def test_index_ok(self, cint_type):
        array = [0x11, 0x22, 0x33]
        assert array[cint_type(1)] == 0x22

    def test_int_ok(self, cint_type):
        assert int(cint_type(1)) == 1

    def test_repr_returnsCTypeAndInt(self, cint_type):
        cint_obj = cint_type(65)
        assert repr(cint_obj) == "ts.cint(65)"

    def test_repr_onSigned8Bit_returnsBytes(self, addrspace):
        cchar_type = cdm.CIntType('char', 8, True, cdm.ENDIANESS, addrspace)
        cchar_obj = cchar_type(b'A')
        assert repr(cchar_obj) == "ts.char(b'A')"
