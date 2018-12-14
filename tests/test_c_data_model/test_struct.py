import pytest
import re
import ctypes as ct
from unittest.mock import patch

import headlock.c_data_model as cdm



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

    @patch.object(cdm.CStructType, 'CPROXY_CLASS')
    def test_call_onPositionAndKeywordArgs_mergesParameters(self, CPROXY_CLASS, cstruct_type):
        cproxy = cstruct_type(1, 2, _depends_on_=3, member_int2=4)
        assert cproxy is CPROXY_CLASS.return_value
        CPROXY_CLASS.assert_called_once_with(
            cstruct_type, dict(member_int=1, member_short=2, member_int2=4), 3)

    @patch.object(cdm.CStructType, 'CPROXY_CLASS')
    def test_call_onNoParams_ok(self, CPROXY_CLASS, cstruct_type):
        cstruct_type()
        CPROXY_CLASS.assert_called_once_with(cstruct_type, {}, None)

    def test_sizeof_onNoExplicitPacking_returnsSizeOfUnpackedStruct(self, cuint64_type, cint16_type):
        unpacked_cstruct_type = cdm.CStructType(
            'unpacked_struct',
            [('m1', cint16_type),
             ('m2', cuint64_type)])
        assert unpacked_cstruct_type.sizeof == 2*cuint64_type.sizeof

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
        assert member_cint_obj.ctype == cint_type
        assert member_cint_obj.adr.val == cstruct_obj.adr.val
        assert member_cint_obj.val == 111111
        member_cshort_obj = cstruct_obj['member_short']
        assert member_cshort_obj.ctype == cint16_type
        assert member_cshort_obj.adr.val > cstruct_obj.adr.val
        assert member_cshort_obj.val == 222
        member_cint2_obj = cstruct_obj['member_int2']
        assert member_cint2_obj.ctype == cint_type
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
                                      'ctype'])
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
