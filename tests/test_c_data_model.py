import ctypes as ct
import collections
import pytest
import headlock.c_data_model


class TestCMemory:

    def test_init_onAddressOnly_setsAttributes(self):
        cmem_obj = headlock.c_data_model.CMemory(0x1234)
        assert cmem_obj.addr == 0x1234
        assert not cmem_obj.readonly
        assert cmem_obj.max_size is None

    def test_init_onMaxSizeAndReadOnly_setsAttributes(self):
        cmem_obj = headlock.c_data_model.CMemory(0, 1234, readonly=True)
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
        return headlock.c_data_model.CMemory(ct.addressof(ct_obj),
                                                len(testdata))

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
        ro_raw_access = headlock.c_data_model.CMemory(ct_obj, readonly=True)
        with pytest.raises(headlock.c_data_model.WriteProtectError):
            ro_raw_access[2] = 0x99

    def test_setItem_onInvalidIndex_raisesIndexError(self, cmem_obj):
        with pytest.raises(IndexError):
            cmem_obj[-1] = 1

    def test_repr_ok(self):
        cmem_obj = headlock.c_data_model.CMemory(0x1234, 10, readonly=True)
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

    def test_ne_ok(self, cmem_obj):
        assert cmem_obj != b'\x12\x34\x56\x99'
        assert not cmem_obj != b'\x12\x34\x56\x78'

    def test_lt_ok(self, cmem_obj):
        assert cmem_obj < b'\x12\x34\x56\x79'
        assert not cmem_obj < b'\x12\x34\x56\x78'

    def test_gt_ok(self, cmem_obj):
        assert cmem_obj > b'\x12\x34\x56\x77'
        assert not cmem_obj > b'\x12\x34\x56\x78'

    def test_le_ok(self, cmem_obj):
        assert cmem_obj <= b'\x12\x34\x56\x78'
        assert not cmem_obj <= b'\x12\x34\x56\x77'

    def test_ge_ok(self, cmem_obj):
        assert cmem_obj >= b'\x12\x34\x56\x78'
        assert not cmem_obj >= b'\x12\x34\x56\x79'


class DummyInt(headlock.c_data_model.CInt):
    bits = 32
    signed = True
    ctypes_type = ct.c_int32


class DummyShortInt(headlock.c_data_model.CInt):
    bits = 16
    signed = False
    ctypes_type = ct.c_uint16


class DummyByte(headlock.c_data_model.CInt):
    bits = 8
    signed = False
    ctypes_type = ct.c_uint8


class TestCInt:

    def test_withAttr_createsDerivedTypeWithAttrSet(self):
        attr_DummyInt = DummyInt.with_attr('attr')
        assert issubclass(attr_DummyInt, DummyInt)
        assert attr_DummyInt is not DummyInt

    def test_withAttr_onAttrAlreadySet_raiseTypeError(self):
        with pytest.raises(TypeError):
            DummyInt.with_attr('attr').with_attr('attr')

    def test_withAttr_callTwiceWithDifferentAttrs_setsParentToBaseType(self):
        attr1_DummyInt = DummyInt.with_attr('attr1')
        attr12_DummyInt = attr1_DummyInt.with_attr('attr2')
        assert not issubclass(attr12_DummyInt, attr1_DummyInt)
        assert issubclass(attr12_DummyInt, DummyInt)

    def test_hasAttr_onAttrNotSet_returnsFalse(self):
        assert not DummyInt.has_attr('attr')

    def test_hasAttr_onAttrSet_returnsTrue(self):
        attr_DummyInt = DummyInt.with_attr('attr')
        assert attr_DummyInt.has_attr('attr')

    def test_isinstance_onAbcCollection_returnsFalse(self):
        assert not isinstance(DummyInt(), collections.abc.Iterable)

    def test_cDefinition_onCNameIsNone_returnsClassName(self):
        assert DummyInt.c_definition() == 'DummyInt'

    def test_cDefinition_onCNameIsNotNone_returnsValue(self):
        class SpecialNameInt(DummyShortInt): c_name = 'test_name'
        assert SpecialNameInt.c_definition() == 'test_name'

    def test_cDefinition_onRefDefIsSet_returnsWithRefDef(self):
        assert DummyInt.c_definition('xy') == 'DummyInt xy'

    def test_cDefinition_onConstAttr_returnsConstCDef(self):
        const_DummyInt = DummyInt.with_attr('const')
        assert const_DummyInt.c_definition('xy') == 'const DummyInt xy'

    def test_cDefinition_onVolatileAttr_returnsVolatileCDef(self):
        volatile_DummyInt = DummyInt.with_attr('volatile')
        assert volatile_DummyInt.c_definition('xy') == 'volatile DummyInt xy'

    def test_cDefinition_onVolatileOnSpecialCName_ok(self):
        class DelimDummyInt(DummyInt): c_name = 'special name'
        volatile_delim_dummy_int = DelimDummyInt.with_attr('volatile')
        assert volatile_delim_dummy_int.c_definition('a') \
               == 'volatile special name a'

    def test_create_fromCTypesObj_returnsCIntThatWrappsCtypesObj(self):
        ctypesObj = ct.c_uint32(999)
        intObj = DummyInt(ctypesObj)
        assert intObj.ctypes_obj is ctypesObj

    def test_create_fromPyInt_returnsCIntWithCTypesObj(self):
        intObj = DummyInt(999)
        assert isinstance(intObj.ctypes_obj, ct.c_int32)
        assert intObj.ctypes_obj.value == 999

    def test_create_withoutArgs_returnsCIntWithValue0(self):
        intObj = DummyInt()
        assert intObj.ctypes_obj.value == 0

    def test_create_fromCInt_returnsCastedObj(self):
        intObj = DummyInt(999)
        shortObj = DummyShortInt(intObj)
        assert isinstance(shortObj.ctypes_obj, ct.c_uint16)
        assert shortObj.ctypes_obj.value == 999

    def test_getVal_returnsIntValue(self):
        intObj = DummyInt(999)
        assert isinstance(intObj.val, int)
        assert intObj.val == 999

    def test_setVal_modifiesVal(self):
        intObj = DummyInt(999)
        intObj.val = 1111
        assert intObj.val == 1111

    def test_setVal_modifiesCObjInplace(self):
        intObj = DummyInt(999)
        orig_adr = ct.addressof(intObj.ctypes_obj)
        intObj.val = 1111
        assert intObj.ctypes_obj.value == 1111
        assert ct.addressof(intObj.ctypes_obj) == orig_adr

    def test_setVal_onCObj_writesValOfCObj(self):
        int_obj = DummyInt()
        int_obj.val = DummyShortInt(2)
        assert int_obj.val == 2

    def test_setVal_onConstCObj_raisesWriteProtectError(self):
        const_int_obj = DummyInt.with_attr('const')(3)
        with pytest.raises(headlock.c_data_model.WriteProtectError):
            const_int_obj.val = 4

    def test_setVal_onBytesOfSize1_setsAsciiCode(self):
        int_obj = DummyInt()
        int_obj.val = b'\xFF'
        assert int_obj == 0xFF

    def test_setVal_onStrOfSize1_setsUnicodeCode(self):
        int_obj = DummyInt()
        int_obj.val = '\U00012345'
        assert int_obj == 0x12345

    def test_repr_returnsClassNameAndValue(self):
        assert repr(DummyInt(1234)) == 'DummyInt(1234)'

    def test_sizeof_onSortInt_returns2(self):
        assert DummyShortInt.sizeof == 2

    def test_nullVal_ok(self):
        assert DummyShortInt.null_val == 0

    def test_typeEq_onNoType_returnsFalse(self):
        assert DummyInt != 3

    def test_typeEq_onNoneCObjType_returnsFalse(self):
        assert DummyInt != int

    def test_typeEq_onDifferentCObjType_returnsFalse(self):
        class DummyCObj(headlock.c_data_model.CObj): pass
        assert DummyInt != DummyCObj

    def test_typeEq_onDifferentIntTypeObjButSameContent_returnsTrue(self):
        class DummyIntSame(DummyInt): pass
        assert DummyInt == DummyIntSame

    def test_typeEq_onDifferentBits_returnsFalse(self):
        class DummyIntNotSame(DummyInt): bits = 11
        assert DummyInt != DummyIntNotSame

    def test_typeEq_onDifferentSign_returnsFalse(self):
        class DummyIntNotSame(DummyInt): signed = False
        assert DummyInt != DummyIntNotSame

    def test_typeEq_onDifferentVolatile_returnsFalse(self):
        assert DummyInt.with_attr('volatile') == DummyInt.with_attr('volatile')
        assert DummyInt.with_attr('volatile') != DummyInt.with_attr('const')
        assert DummyInt.with_attr('volatile') != DummyInt

    def test_eq_onPyObjOfSameValue_returnsTrue(self):
        assert DummyInt(9) == 9
        assert 9 == DummyInt(9)

    def test_eq_onPyObjOfDifferentValue_returnsFalse(self):
        assert DummyInt(9) != 10
        assert 10 != DummyInt(9)

    def test_eq_onCObjOfSameValue_returnsTrue(self):
        assert DummyInt(999) == DummyShortInt(999)

    def test_eq_onCObjOfDifferentValue_returnsFalse(self):
        assert DummyInt(1000) != DummyInt(999)

    def test_gtLt_onPyObj_ok(self):
        assert DummyInt(4) > 3
        assert not DummyInt(4) < 3
        assert DummyInt(3) < 4
        assert not DummyInt(3) > 4

    def test_geLE_onPyObj_ok(self):
        assert DummyInt(4) >= 3
        assert DummyInt(4) >= 4
        assert not DummyInt(4) <= 3
        assert DummyInt(3) <= 4
        assert DummyInt(4) <= 4
        assert not DummyInt(3) >= 4

    def test_add_onPyObj_ok(self):
        intobj = DummyInt(4)
        adr = intobj.adr.val
        intobj2 = intobj + 1
        assert intobj.val == 4
        assert intobj2.val == 5

    def test_add_onCObj_ok(self):
        intobj = DummyInt(4)
        intobj2 = intobj + DummyShortInt(1)
        assert intobj.val == 4
        assert intobj2.val == 5

    def test_radd_onPyObj_ok(self):
        intobj = DummyInt(4)
        adr = intobj.adr.val
        intobj2 = 1 + intobj
        assert intobj.val == 4
        assert intobj2.val == 5

    def test_iadd_operatesInplace(self):
        intobj = DummyInt(3)
        adr = intobj.adr
        intobj += 4
        assert intobj.val == 7
        assert intobj.adr == adr

    def test_sub_onPyObj_ok(self):
        intobj = DummyInt(4)
        adr = intobj.adr.val
        intobj2 = intobj - 1
        assert intobj.val == 4
        assert intobj2.val == 3

    def test_sub_onCObj_ok(self):
        intobj = DummyInt(4)
        intobj2 = intobj - DummyShortInt(1)
        assert intobj.val == 4
        assert intobj2.val == 3

    def test_rsub_onPyObj_ok(self):
        intobj = DummyInt(4)
        adr = intobj.adr.val
        intobj2 = 5 - intobj
        assert intobj.val == 4
        assert intobj2.val == 1

    def test_isub_operatesInplace(self):
        intobj = DummyInt(7)
        adr = intobj.adr
        intobj -= 3
        assert intobj.val == 4
        assert intobj.adr == adr

    def test_index_ok(self):
        array = [0x11, 0x22, 0x33]
        assert array[DummyInt(1)] == 0x22

    def test_int_ok(self):
        assert int(DummyInt(1)) == 1

    def test_copy_returnsSameValueButDifferentAddress(self):
        intobj = DummyInt(999)
        intobj_copy = intobj.copy()
        assert intobj.val == intobj_copy.val
        assert intobj.adr != intobj_copy.adr

    def test_getMem_returnsBufferOfRawData(self):
        int_obj = DummyInt(0x120084)
        cmem_obj = int_obj.mem
        assert isinstance(cmem_obj, headlock.c_data_model.CMemory)
        assert cmem_obj.addr == ct.addressof(int_obj.ctypes_obj)
        assert cmem_obj.max_size is None
        assert not cmem_obj.readonly

    def test_getMem_onConstObj_returnsReadonlyRawData(self):
        int_obj = DummyInt.with_attr('const')(0x120084)
        assert int_obj.mem.readonly

    def test_setMem_setsRawDataToBuffer(self):
        int_obj = DummyInt()
        int_obj.mem = bytearray.fromhex("34 00 12 00")
        assert int_obj.val == 0x120034

    def test_setMem_onValueSmallerThanCObj_ok(self):
        int_obj = DummyInt()
        int_obj.mem = b'\x11'
        assert int_obj.val == 0x00000011

    def test_setMem_onConst_raiseReadOnlyError(self):
        int_obj = DummyInt.with_attr('const')(2)
        with pytest.raises(headlock.c_data_model.WriteProtectError):
            int_obj.mem = b'1234'

    def test_iterReqCustomTypes_returnsEmptyList(self):
        assert list(DummyInt.iter_req_custom_types()) == []


class TestCPointer:

    def test_ptr_onIntType_returnsPointerSubclass(self):
        int_ptr_type = DummyInt.ptr
        assert issubclass(int_ptr_type, headlock.c_data_model.CPointer)
        assert int_ptr_type.base_type == DummyInt

    def test_create_fromCTypes_returnsWrapperAroundCTypesObj(self):
        ctypes_ptr = ct.pointer(ct.c_uint32(999))
        int_ptr = DummyInt.ptr(ctypes_ptr)
        assert int_ptr.ctypes_obj is ctypes_ptr

    def test_create_fromPyInt_returnsPtrObjReferingGivenAddress(self):
        int_ptr = DummyInt.ptr(999)
        assert ct.addressof(int_ptr.ctypes_obj.contents) == 999

    def test_create_withoutArgs_returnsNullrefObj(self):
        int_ptr = DummyInt.ptr()
        assert not int_ptr.ctypes_obj

    def test_create_fromCInt_returnsPtrToSpecifiedAdrVal(self):
        new_int_ctypesobj = ct.c_int32()
        intobj = DummyInt(ct.addressof(new_int_ctypesobj))
        intptr = DummyInt.ptr(intobj)
        assert intptr.val == ct.addressof(new_int_ctypesobj)

    def test_create_fromCPointer_returnsCastedCPointer(self):
        int_ptr = DummyInt.ptr(ct.pointer(ct.c_uint32(0x12345678)))
        short_ptr = DummyShortInt.ptr(int_ptr)
        # on LSB arch only!
        assert short_ptr.ctypes_obj.contents.value == 0x5678

    def test_create_fromCPointer_hasSameDependsOn(self):
        int_obj = DummyInt()
        int_ptr = int_obj.adr
        assert int_ptr._depends_on_ == int_obj
        assert DummyShortInt.ptr(int_ptr)._depends_on_ == int_obj

    def test_create_fromCArray_returnsCastedArray(self):
        array = DummyShortInt.alloc_array([0x1122, 0x3344])
        ptr = DummyInt.ptr(array)
        assert ptr.val == array.adr.val
        assert ptr[0] == 0x33441122

    @pytest.mark.parametrize('initval', [
        b'\x11\x22\x33', '\x11\x22\x33', [0x11, 0x22, 0x33],
        iter([0x11, 0x22, 0x33])])
    def test_create_fromPyIterable_createsReferredArrayFromIterable(self, initval):
        int_ptr = DummyInt.ptr(initval)
        assert int_ptr._depends_on_ is not None
        assert int_ptr[:3] == [0x11, 0x22, 0x33]

    def test_create_fromUnicodeObject_createsArrayWithSizeDependingOnDecodedUnicode(self):
        int_ptr = DummyInt.ptr('\U00012345\u1234')
        assert int_ptr[:3] == [0x12345, 0x1234, 0]

    def test_allocPtr_onInt_returnsPtrToBufOfSpecifiedSize(self):
        ptr = DummyInt.alloc_ptr(100)
        assert isinstance(ptr, headlock.c_data_model.CPointer)
        assert ptr.base_type is DummyInt
        assert ptr[:100] == [0]*100

    def test_allocPtr_returnCObjWithDependsOn(self):
        ptr = DummyInt.alloc_ptr(100)
        assert ptr._depends_on_ is not None

    def test_allocPtr_onList_returnsPtrToBufWithSpecifiedInitVals(self):
        ptr = DummyInt.alloc_ptr([0x11, 0x22, 0x33, 0x44])
        assert ptr[:4] == [0x11, 0x22, 0x33, 0x44]

    def test_getAdr_onInt_returnsPointerObj(self):
        int_obj = DummyInt(999)
        int_ptr = int_obj.adr
        assert isinstance(int_ptr, headlock.c_data_model.CPointer)
        assert ct.addressof(int_ptr.ctypes_obj.contents) == \
               ct.addressof(int_obj.ctypes_obj)

    def test_getVal_returnsAddress(self):
        ctypes_int = ct.c_int32()
        ptr = DummyInt.ptr(ct.addressof(ctypes_int))
        assert ptr.val == ct.addressof(ctypes_int)

    def test_getUnicodeStr_onZeroTerminatedStr_returnsPyString(self):
        ptr = DummyInt.alloc_ptr([0x1234, 0x56, 0])
        assert ptr.unicode_str == '\u1234\x56'

    def test_setUnicodeStr_onPyStr_changesArrayToZeroTerminatedString(self):
        ptr = DummyInt.alloc_ptr([111] * 6)
        ptr.unicode_str = '\u1234\x56\0\x78'
        assert ptr[:6] == [0x1234, 0x56, 0, 0x78, 0, 111]

    def test_getCStr_onZeroTerminatedStr_returnsBytes(self):
        ptr = DummyInt.alloc_ptr([ord('X'), ord('y'), 0])
        assert ptr.c_str == b'Xy'

    def test_setCStr_onPyStr_changesArrayToZeroTerminatedString(self):
        ptr = DummyInt.alloc_ptr([111] * 6)
        ptr.c_str = b'Xy\0z'
        assert ptr[:6] == [ord('X'), ord('y'), 0, ord('z'), 0, 111]

    def test_int_returnsAddress(self):
        ctypes_int = ct.c_int32()
        ptr = DummyInt.ptr(ct.addressof(ctypes_int))
        assert int(ptr) == ct.addressof(ctypes_int)

    def test_getVal_onNullPtr_returns0(self):
        ptr = DummyInt.ptr()
        assert ptr.val == 0

    def test_setVal_setsAddress(self):
        ptr = DummyInt.ptr()
        validMemAddress = ct.addressof(ct.c_int32())
        ptr.val = validMemAddress
        assert ptr.val == validMemAddress

    def test_setVal_onNullPtr_ok(self):
        ptr = DummyInt.ptr()
        ptr.val = 0
        assert ptr.val == 0

    def test_setVal_onCArray_setsAddressOfArray(self):
        int_arr = DummyInt.alloc_array(3)
        int_ptr = DummyInt.ptr()
        int_ptr.val = int_arr
        assert int_ptr.val == int_arr.adr.val

    @pytest.mark.parametrize('setval', [
        [0x11, 0x22, 0x33], iter([0x11, 0x22, 0x33])])
    def test_setVal_onIterable_fillsReferredElemsByIterable(self, setval):
        int_arr = DummyInt.alloc_array([0x99, 0x99, 0x99, 0x99])
        int_ptr = int_arr[0].adr
        int_ptr.val = setval
        assert int_arr.val == [0x11, 0x22, 0x33, 0x99]

    def test_setVal_fromUnicodeObject_fillsReferredElemsWithDecodedUnicodePlus0(self):
        int_arr = DummyInt.alloc_array([0x99, 0x99, 0x99])
        int_ptr = int_arr[0].adr
        int_ptr.val = '\U00012345\u1234'
        assert int_arr == [0x12345, 0x1234, 0]

    def test_setVal_onConstCObj_raisesWriteProtectError(self):
        const_ptr_obj = DummyInt.ptr.with_attr('const')(3)
        with pytest.raises(headlock.c_data_model.WriteProtectError):
            const_ptr_obj.val = 4

    def test_getRef_ok(self):
        cobj = DummyInt(999)
        _ptrobj = cobj.adr
        assert _ptrobj.ref.val == cobj.val

    def test_setRef_ok(self):
        cobj = DummyInt(999)
        ptr = cobj.adr
        ptr.ref.val = 1111
        assert cobj.val == 1111

    def test_getAdr_onPtr_ok(self):
        cobj = DummyInt(999)
        ptr_ptr = cobj.adr.adr
        assert ptr_ptr.ref.ref.val == cobj.val

    def test_repr_returnsClassNameAndHexValue(self):
        ptr = DummyInt(1234).adr
        assert repr(ptr) == f'DummyInt_ptr(0x{ptr.val:08X})'

    def test_sizeof_returnsSameSizeAsInt(self):
        assert DummyShortInt.ptr.sizeof == ct.sizeof(ct.c_int)

    def test_nullValue_ok(self):
        assert DummyShortInt.null_val == 0

    def test_add_returnsNewPointerAtIncrementedAddress(self):
        int_ptr = DummyShortInt(999).adr
        moved_intptr = int_ptr + 100
        assert int_ptr.val + 200 == moved_intptr.val

    def test_add_onCInt_ok(self):
        int_ptr = DummyInt(1).adr
        moved_intptr = int_ptr + DummyInt(1)
        assert moved_intptr.val == int_ptr.val + DummyInt.sizeof

    def test_sub_returnsNewPointerAtDecrementedAddress(self):
        int_ptr = DummyShortInt(999).adr
        moved_intptr = int_ptr - 100
        assert int_ptr.val - 200 == moved_intptr.val

    def test_sub_onCPointer_returnsNumberOfElementsInBetween(self):
        obj_arr = DummyShortInt.alloc_array(3)
        adr0 = obj_arr[0].adr
        adr2 = obj_arr[2].adr
        assert adr2 - adr0 == 2
        assert isinstance(adr2 - adr0, int)

    def test_sub_onCPointerOfDifferrentType_raisesTypeError(self):
        adr1 = DummyInt().adr
        adr2 = DummyShortInt().adr
        with pytest.raises(TypeError):
            adr2 - adr1

    def test_sub_onCArray_returnsNumberOfElementsInBetween(self):
        obj_arr = DummyShortInt.alloc_array(3)
        adr2 = obj_arr[2].adr
        assert adr2 - obj_arr == 2
        assert isinstance(adr2 - obj_arr, int)

    def test_sub_onCPointerOfDifferrentType_raisesTypeError(self):
        short_arr = DummyShortInt.alloc_array(3)
        adr2 = DummyInt().adr
        with pytest.raises(TypeError):
            adr2 - short_arr

    def test_sub_onCInt_ok(self):
        int_ptr = DummyInt(1).adr
        moved_intptr = int_ptr - DummyInt(1)
        assert moved_intptr.val == int_ptr.val - DummyInt.sizeof

    def test_getItem_onNdx_returnsCObjAtNdx(self):
        array = DummyInt.alloc_array([0x11, 0x22, 0x33])
        ptr = DummyInt.ptr(array.adr)
        assert ptr[1] == 0x22  and  ptr[2] == 0x33

    def test_getItem_onSlice_returnsCArrayOfCObjAtSlice(self):
        array = DummyInt.alloc_array([0x11, 0x22, 0x33, 0x44])
        ptr = DummyInt.ptr(array.adr)
        part_array = ptr[1:3]
        assert type(part_array) == DummyInt.array(2)
        assert part_array.val == [0x22, 0x33]

    def test_typeEq_onDifferentTypeObjButSameBases_returnsTrue(self):
        class DummyIntSame(DummyInt): pass
        assert DummyInt.ptr == DummyIntSame.ptr

    def test_typeEq_onNoType_returnsFalse(self):
        assert DummyInt.ptr != 3

    def test_typeEq_onNoneCObjType_returnsFalse(self):
        assert DummyInt.ptr != int

    def test_typeEq_onDifferentCObjType_returnsFalse(self):
        assert DummyInt.ptr != DummyInt

    def test_typeEq_onDifferentBaseTypes_returnsFalse(self):
        assert DummyInt.ptr != DummyShortInt.ptr

    def test_typeEq_onAttrSet(self):
        assert DummyInt.ptr.with_attr('attr') == DummyInt.ptr.with_attr('attr')
        assert DummyInt.ptr.with_attr('attr') != DummyInt.ptr.with_attr('attr2')
        assert DummyInt.ptr.with_attr('attr') != DummyInt.ptr

    def test_cDefinition_onNoRefDef_returnsCNameWithoutRefDef(self):
        assert DummyInt.ptr.c_definition() == 'DummyInt *'

    def test_cDefinition_onPtrToPtr_returnsTwoStars(self):
        assert DummyInt.ptr.ptr.c_definition() == 'DummyInt **'

    def test_cDefinition_onRefDef_returnsCNameWithRefDef(self):
        assert DummyInt.ptr.c_definition('ab') == 'DummyInt *ab'

    def test_cDefinition_onConstRefDef_returnsConstObj(self):
        assert DummyInt.ptr.with_attr('const').c_definition('ab') \
               == 'DummyInt *const ab'

    def test_cDefinition_onVolatileRefDef_returnsVolatileObj(self):
        assert DummyInt.ptr.with_attr('volatile').c_definition('ab') \
               == 'DummyInt *volatile ab'

    def test_iterReqCustomTypes_returnsReferredTypeElementaryTypes(self):
        class X(DummyInt):
            @classmethod
            def iter_req_custom_types(cls, only_full_defs=False,already_processed=None):
                return iter(["test", "test2"])
        assert list(X.ptr.iter_req_custom_types()) == ["test", "test2"]

    def test_iterReqCustomTypes_onOnlyFullDef_doesNotReturnReferredTypeElementaryTypes(self):
        class X(DummyInt):
            @classmethod
            def iter_req_custom_types(cls, only_full_defs=False,already_processed=None):
                raise AssertionError('Must Not be called')
        assert list(X.ptr.iter_req_custom_types(only_full_defs=True)) == []


class TestCArray:

    def test_array_onLength_returnsArraySubClassOfGivenSize(self):
        array_type = DummyInt.array(10)
        assert issubclass(array_type, headlock.c_data_model.CArray)
        assert array_type.base_type == DummyInt
        assert array_type.element_count == 10

    def test_allocArray_onLength_returnsArrayInstanceOfGivenSize(self):
        array = DummyInt.alloc_array(3)
        assert isinstance(array, headlock.c_data_model.CArray)
        assert array == [0, 0, 0]

    @pytest.mark.parametrize('initval', [[1, 2, 3, 4], b'\x01\x02\x03\x04',
                                         iter([1, 2, 3, 4])])
    def test_allocArray_onPyCollection_returnsArrayInstanceInitializedWithPyColl(self, initval):
        array = DummyInt.alloc_array(initval)
        assert array == [1, 2, 3, 4]

    def test_allocArray_onPyStr_returnsArrayInstanceInitializedWithZeroTerminatedByStr(self):
        array = DummyByte.alloc_array('Ab')
        assert array.element_count > 2

    def test_create_fromCTypesObj_returnsWrapperAroundParam(self):
        ctype_array = (ct.c_int32 * 100)()
        array = DummyInt.array(100)(ctype_array)
        assert array.ctypes_obj == ctype_array

    def test_create_fromNoParam_returnsDefaultEntries(self):
        array = DummyInt.alloc_array(100)
        assert all(array.ctypes_obj[ndx] == 0 for ndx in range(100))

    def test_create_fromPyIterable_ok(self):
        array = DummyInt.array(4)(iter([11, 22, 33, 44]))
        assert array.ctypes_obj[0] == 11
        assert array.ctypes_obj[1] == 22
        assert array.ctypes_obj[2] == 33
        assert array.ctypes_obj[3] == 44

    def test_create_fromUtf8WithBigCodepoint_returnsArrayOfCorrectSize(self):
        array = DummyInt.array(2)('\u1122')
        assert array.ctypes_obj[0] == 0x1122
        assert array.ctypes_obj[1] == 0

    def test_len_returnsSizeOfObject(self):
        array_type = DummyInt.array(44)
        assert len(array_type) == 44
        assert len(array_type()) == 44

    def test_getVal_returnsListOfBaseTypeObjs(self):
        array_obj = DummyInt.array(4)([0x11, 0x22, 0x33, 0x44])
        assert array_obj.val == [0x11, 0x22, 0x33, 0x44]

    @pytest.mark.parametrize('init_iter',
        [b'\x11\x22\x33', [0x11, 0x22, 0x33], iter([0x11, 0x22, 0x33])])
    def test_setVal_onIterable_setsArrayElemFromIterableEnries(self, init_iter):
        array = DummyShortInt.array(3)()
        array.val = init_iter
        assert array.val == [0x11, 0x22, 0x33]

    def test_setVal_onIterable_convertsToCTypesObj(self):
        array = DummyInt.array(2)()
        array.val = [0x11, 0x22]
        assert array.ctypes_obj[0] == 0x11
        assert array.ctypes_obj[1] == 0x22

    def test_setVal_withOnShorterIterable_setsRemainingEntriesToNull(self):
        array = DummyInt.array(3)([0x99, 0x99, 0x99])
        array.val = [0x11]
        assert array.val == [0x11, 0x00, 0x00]

    def test_setVal_onStringTo8BitArray_storesArrayElemUtf8Encoded(self):
        array = DummyByte.array(9)()
        array.val = '\x11\u2233\U00014455'
        assert array.val == [0x11, 0xe2, 0x88, 0xb3, 0xf0, 0x94, 0x91, 0x95, 0]

    def test_setVal_onStringTo16BitArray_storesArrayElemUtf16Encoded(self):
        array = DummyShortInt.array(5)()
        array.val = '\x11\u2233\U00014455'
        assert array.val == [0x0011, 0x2233, 0xD811, 0xDC55, 0]

    def test_setVal_onStringTo32BitArray_storesArrayElemUtf32Encoded(self):
        array = DummyInt.array(4)()
        array.val = '\x11\u2233\U00014455'
        assert array.val == [0x00000011, 0x00002233, 0x00014455, 0]

    def test_str_returnsStringWithZeros(self):
        array = DummyShortInt.array(3)([ord('x'), ord('Y'), 0])
        assert str(array) == 'xY\0'

    def test_getCStr_onZeroTerminatedStr_returnsBytes(self):
        array = DummyInt.array(3)([ord('X'), ord('y'), 0])
        assert array.c_str == b'Xy'

    def test_setCStr_onPyStr_changesArrayToZeroTerminatedString(self):
        array = DummyInt.alloc_array([111] * 6)
        array.c_str = 'Xy\0z'
        assert array.val == [ord('X'), ord('y'), 0, ord('z'), 0, 0]

    def test_getUnicodeStr_onZeroTerminatedStr_returnsPyString(self):
        array = DummyInt.alloc_array([0x1234, 0x56, 0])
        assert array.unicode_str == '\u1234\x56'

    def test_setUnicodeStr_onPyStr_changesArrayToZeroTerminatedString(self):
        array = DummyInt.alloc_array([111] * 6)
        array.unicode_str = '\u1234\x56\0\x78'
        assert array.val == [0x1234, 0x56, 0, 0x78, 0, 0]

    def test_setCStr_onPyStr_changesArrayToZeroTerminatedString(self):
        array = DummyInt.alloc_array([111] * 5)
        array.c_str = 'X\0y'
        assert array.val == [ord('X'), 0, ord('y'), 0, 0]

    def test_setCStr_onTooLongPyStr_raisesValueError(self):
        array = DummyInt.array(3)()
        with pytest.raises(ValueError):
            array.c_str = 'Xyz'

    def test_getItem_returnsObjectAtNdx(self):
        array_obj = DummyShortInt.array(4)([1, 2, 3, 4])
        assert array_obj[2].adr.val == array_obj.adr.val+2*DummyShortInt.sizeof

    def test_getItem_onNegativeIndex_returnsElementFromEnd(self):
        array_obj = DummyInt.array(4)([1, 2, 3, 4])
        assert array_obj[-1].adr == array_obj[3].adr

    def test_getItem_onSlice_returnsSubArray(self):
        array_obj = DummyInt.array(4)([1, 2, 3, 4])
        sliced_array = array_obj[1:3]
        assert type(sliced_array), DummyInt.array(2)
        assert sliced_array.val == [2, 3]
        assert [obj.adr for obj in sliced_array] == \
               [array_obj[1].adr, array_obj[2].adr]

    def test_getItem_onSliceWithSteps_raiseValueError(self):
        array_obj = DummyInt.array(4)([1, 2, 3, 4])
        with pytest.raises(ValueError):
            array_obj[0:4:2]

    def test_getItem_onSliceWithNegativeBoundaries_returnsPartOfArrayFromEnd(self):
        array_obj = DummyInt.array(5)([1, 2, 3, 4, 5])
        sliced_array = array_obj[-3:-1]
        assert [obj.adr for obj in sliced_array] == \
               [array_obj[2].adr, array_obj[3].adr]

    def test_getItem_onSliceWithOpenEnd_returnsPartOfArrayUntilEnd(self):
        array_obj = DummyInt.array(4)([1, 2, 3, 4])
        sliced_array = array_obj[1:]
        assert [obj.adr for obj in sliced_array] == \
               [array_obj[1].adr, array_obj[2].adr, array_obj[3].adr]

    def test_getItem_onSliceWithOpenStart_returnsPartOfArrayFromStart(self):
        array_obj = DummyInt.array(4)([1, 2, 3, 4])
        sliced_array = array_obj[:3]
        assert [obj.adr for obj in sliced_array] == \
               [array_obj[0].adr, array_obj[1].adr, array_obj[2].adr]

    def test_add_returnsPointer(self):
        array = DummyInt.array(4)()
        assert array + 3 == array[3].adr

    def test_repr_returnsClassNameAndContent(self):
        assert repr(DummyInt.array(3)()) == 'DummyInt_3([0, 0, 0])'

    def test_sizeof_returnsSizeInBytes(self):
        assert DummyShortInt.array(9).sizeof == 9*2

    def test_nullValue_ok(self):
        assert DummyShortInt.array(3).null_val == [0, 0, 0]

    def test_iter_returnsIterOfElements(self):
        data = [0x11, 0x22, 0x33, 0x44]
        array_obj = DummyInt.array(4)(data)
        assert list(array_obj) == list(map(DummyInt, data))

    def test_typeEq_onNoType_returnsFalse(self):
        assert DummyInt.array(4) != 3

    def test_typeEq_onNoneCObjType_returnsFalse(self):
        assert DummyInt.array(4) != int

    def test_typeEq_onDifferentCObjType_returnsFalse(self):
        assert DummyInt.array(4) != DummyInt

    def test_typeEq_onDifferentTypeButSameSizeAndBaseType_returnsTrue(self):
        type1 = DummyInt.array(4)
        type2 = DummyInt.array(4)
        assert type1 is not type2
        assert type1 == type2

    def test_typeEq_onDifferentBaseType_returnsFalse(self):
        type1 = DummyInt.array(4)
        type2 = DummyInt.array(4)
        assert type1 is not type2
        assert type1 == type2

    def test_cDefinition_onRefDef_returnsWithRefDef(self):
        assert DummyInt.array(12).c_definition('x') == 'DummyInt x[12]'

    def test_cDefinition_onNoRefDef_returnsWithoutRefDef(self):
        assert DummyInt.array(12).c_definition() == 'DummyInt [12]'

    def test_cDefinition_onArrayOfArrays_ok(self):
        assert DummyInt.array(11).array(22).c_definition() \
               == 'DummyInt [22][11]'

    def test_cDefinition_onArrayOfPtr_ok(self):
        assert DummyInt.ptr.array(10).c_definition('x') == 'DummyInt *x[10]'

    def test_cDefinition_onPtrToArray_ok(self):
        assert DummyInt.array(10).ptr.c_definition('x') == 'DummyInt (*x)[10]'

    @pytest.mark.parametrize('only_full_defs', [True, False])
    def test_iterReqCustomTypes_returnsReferredTypeElementaryTypes(self, only_full_defs):
        class X(DummyInt):
            @classmethod
            def iter_req_custom_types(cls, only_full_defs=False,already_processed=None):
                return iter(["test", "test2"])
        assert list(X.array(3).iter_req_custom_types(only_full_defs)) \
               == ["test", "test2"]


class TestCStruct:

    @pytest.fixture
    def DummyStruct(self): 
        return headlock.c_data_model.CStruct.typedef(
            'DummyStruct',
            ('member_int', DummyInt),
            ('member_short', DummyShortInt),
            ('member_int2', DummyInt))

    def test_typedef_returnsStructSubClass(self, DummyStruct):
        assert issubclass(DummyStruct, headlock.c_data_model.CStruct)
        assert issubclass(DummyStruct.ctypes_type, ct.Structure)
        assert DummyStruct._members_ == {'member_int': DummyInt,
                                         'member_short': DummyShortInt,
                                         'member_int2': DummyInt}
        assert DummyStruct._members_order_ == \
               ['member_int', 'member_short', 'member_int2']
        assert issubclass(DummyStruct.member_short, DummyShortInt)
        assert issubclass(DummyStruct.member_int, DummyInt)

    def test_typedef_onNameIsNone_returnsAnonymousStructPlusUniqueId(self):
        astrct1 = headlock.c_data_model.CStruct.typedef(None, ('m', DummyInt))
        astrct2 = headlock.c_data_model.CStruct.typedef(None, ('m', DummyInt))
        assert astrct1.__name__.startswith('__anonymous_')
        assert astrct2.__name__.startswith('__anonymous_')
        assert astrct1.__name__ != astrct2.__name__

    def test_create_fromCTypes_returnsWrappedCTypesObj(self, DummyStruct):
        ctypes_struct = DummyStruct.ctypes_type(
            member_int=11, member_short=22)
        struct = DummyStruct(ctypes_struct)
        assert isinstance(struct.ctypes_obj, DummyStruct.ctypes_type)
        assert struct.ctypes_obj is ctypes_struct

    def test_create_fromNoParam_intializesMembersWithDefaults(self, DummyStruct):
        struct = DummyStruct(DummyStruct.ctypes_type())
        assert struct.ctypes_obj.member_int == 0

    def test_create_fromPositionalParams_initializesMembers(self, DummyStruct):
        struct = DummyStruct(111111, 222)
        assert struct.ctypes_obj.member_int == 111111
        assert struct.ctypes_obj.member_short == 222

    def test_create_fromKeywordArgs_initializesMembers(self, DummyStruct):
        struct = DummyStruct(member_short=222, member_int=111111)
        assert struct.ctypes_obj.member_int == 111111
        assert struct.ctypes_obj.member_short == 222

    def test_create_fromPositionalAndKeywordArgs_initializesMembers(self, DummyStruct):
        struct = DummyStruct(111111, member_short=222)
        assert struct.ctypes_obj.member_int == 111111
        assert struct.ctypes_obj.member_short == 222

    def test_getItem_onStrings_returnsPyObjOfMember(self, DummyStruct):
        struct = DummyStruct(111111, 222, 3)
        member_int = struct['member_int']
        assert isinstance(member_int, DummyInt)
        assert member_int.adr.val == struct.adr.val
        assert member_int.val == 111111
        member_short = struct['member_short']
        assert isinstance(member_short, DummyShortInt)
        assert member_short.adr.val > struct.adr.val
        assert member_short.val == 222
        member_int2 = struct['member_int2']
        assert isinstance(member_int2, DummyInt)
        assert member_int2.adr.val > struct.adr.val
        assert member_int2.val == 3

    def test_getItem_onIndex_returnsPyObjOfMembers(self, DummyStruct):
        struct = DummyStruct()
        assert struct[0].adr == struct['member_int'].adr
        assert struct[1].adr == struct['member_short'].adr

    def test_len_returnsNumberOfMembers(self, DummyStruct):
        assert len(DummyStruct) == 3
        assert len(DummyStruct()) == 3

    def test_iter_returnsMembersInOrder(self, DummyStruct):
        struct = DummyStruct()
        assert list(iter(struct)) == \
               [struct.member_int, struct.member_short, struct.member_int2]

    def test_CMemberGet_onInstance_createsPyObjOfMember(self, DummyStruct):
        struct = DummyStruct()
        assert struct.member_int.adr == struct['member_int'].adr
        assert struct.member_short.adr == struct['member_short'].adr

    @pytest.mark.parametrize('name', [
        'val', 'adr', 'typedef', 'c_definition', 'sizeof'])
    def test_CMemberGet_onReservedName_isNotEnabled(self, name):
        struct = headlock.c_data_model.CStruct.typedef(
            'StructWithReservedMemberNames',
            (name, DummyInt))
        struct_inst = struct([0])
        assert getattr(struct_inst, name) != 0

    def test_getVal_returnsDictOfVals(self, DummyStruct):
        struct = DummyStruct(1, 2)
        assert struct.val == {'member_int':1, 'member_short':2, 'member_int2':0}

    def test_getVal_onNestedStruct_ok(self, DummyStruct):
        NestedStruct = headlock.c_data_model.CStruct.typedef(
            'NestedStruct',
            ('struct', DummyStruct),
            ('int', DummyInt))
        nested_struct = NestedStruct(struct={'member_int':2, 'member_short':99},
                                     int=888)
        assert nested_struct.val == \
               {'struct':{'member_int':2,
                          'member_short':99,
                          'member_int2':0},
                'int':888}

    def test_setVal_onDict_changesMembers(self, DummyStruct):
        struct = DummyStruct(member_int2=99)
        struct.val = {'member_int':1, 'member_short':2}
        assert struct.val == {'member_int':1, 'member_short':2, 'member_int2':0}

    def test_setVal_onSequence_changesMembers(self, DummyStruct):
        struct = DummyStruct(member_int2=99)
        struct.tuple = (1, 2)
        assert struct.val == {'member_int':1, 'member_short':2, 'member_int2':0}

    def test_setVal_onBuf_setsRawData(self, DummyStruct):
        array = DummyStruct()
        array.val = bytearray(range(array.sizeof))
        assert array.member_int.val > 0

    def test_getTuple_returnsTupleOfVals(self, DummyStruct):
        struct = DummyStruct(1, 2, 3)
        assert struct.tuple == (1, 2, 3)

    def test_setTuple_onIterable_changesMembers(self, DummyStruct):
        struct = DummyStruct(member_int2=99)
        struct.tuple = (1, 2)
        assert struct.val == {'member_int':1, 'member_short':2, 'member_int2':0}

    def test_setTuple_onTooLong_raisesValueError(self, DummyStruct):
        struct = DummyStruct()
        with pytest.raises(ValueError):
            struct.tuple = range(4)

    def test_sizeof_returnsSizeOfStruct(self, DummyStruct):
        assert DummyStruct.sizeof == \
               ct.sizeof(DummyStruct.ctypes_type)

    @pytest.mark.parametrize(('packing', 'exp_size'), [(1, 6), (4, 8)])
    def test_sizeof_onDifferentPacking_returnsPackedSize(self, packing, exp_size):
        packed_struct = headlock.c_data_model.CStruct.typedef(
            'packed_struct',
            ('m1', DummyShortInt),
            ('m2', DummyInt),
            packing=packing)
        assert packed_struct.sizeof == exp_size

    def test_nullValue_returnsDictionaryOfNullValues(self, DummyStruct):
        assert DummyStruct.null_val == \
               {'member_int':0, 'member_short':0, 'member_int2':0}

    def test_repr_ok(self, DummyStruct):
        struct = DummyStruct(1, 2)
        assert repr(struct) == \
               'DummyStruct(member_int=1, member_short=2, member_int2=0)'

    def test_delayedDef_setsMembers(self):
        TestStruct = headlock.c_data_model.CStruct.typedef('TestStruct')
        TestStruct.delayed_def(('member1', DummyInt), ('member2', DummyInt))
        assert issubclass(TestStruct.member1, DummyInt)
        assert issubclass(TestStruct.member2, DummyInt)
        assert TestStruct.sizeof == 8

    def test_delayedDef_onRecursiveStruct_ok(self):
        TestStruct = headlock.c_data_model.CStruct.typedef('TestStruct')
        TestStruct.delayed_def(('nested', TestStruct.ptr))
        test_struct = TestStruct(TestStruct().adr)
        assert isinstance(test_struct.nested.ref, TestStruct)

    def test_typeEq_onNoType_returnsFalse(self, DummyStruct):
        assert DummyStruct != 3

    def test_typeEq_onNoneCObjType_returnsFalse(self, DummyStruct):
        assert DummyStruct != int

    def test_typeEq_onDifferentCObjType_returnsFalse(self, DummyStruct):
        assert DummyStruct != DummyInt

    def test_typeEq_onDifferentTypeButSameMembersAndPacking_returnsTrue(self, DummyStruct):
        StructSame = headlock.c_data_model.CStruct.typedef(
            'DummyStruct',
            ('member_int', DummyInt),
            ('member_short', DummyShortInt),
            ('member_int2', DummyInt))
        assert DummyStruct == StructSame

    def test_typeEq_onDifferentMemberOrder_returnsFalse(self, DummyStruct):
        StructDifferent = headlock.c_data_model.CStruct.typedef(
            'DummyStruct',
            ('member_short', DummyShortInt),
            ('member_int', DummyInt),
            ('member_int2', DummyInt))
        assert DummyStruct != StructDifferent

    def test_typeEq_onDifferentPacking_returnsFalse(self, DummyStruct):
        StructDifferent = headlock.c_data_model.CStruct.typedef(
            'DummyStruct',
            ('member_int', DummyInt),
            ('member_short', DummyShortInt),
            ('member_int2', DummyInt),
            packing=1)
        assert DummyStruct != StructDifferent

    def test_typeEq_onDifferentMembers_returnsFalse(self, DummyStruct):
        StructDifferent = headlock.c_data_model.CStruct.typedef(
            'DummyStruct',
            ('member_int', DummyInt),
            ('member_short', DummyInt),
            ('member_int2', DummyInt))
        assert DummyStruct != StructDifferent

    def test_typeEq_onRecursiveStructs_avoidEndlessRecusion(self, DummyStruct):
        RecStruct1 = headlock.c_data_model.CStruct.typedef('RecStruct1')
        RecStruct1.delayed_def(('nested', RecStruct1.ptr))
        RecStruct2 = headlock.c_data_model.CStruct.typedef('RecStruct2')
        RecStruct2.delayed_def(('nested', RecStruct2.ptr))
        assert RecStruct1 == RecStruct2

    def test_cDefinition_onNoRefDef_returnsDefOnly(self, DummyStruct):
        assert DummyStruct.c_definition() == 'struct DummyStruct'

    def test_cDefinition_onRefDef_returnsDefWithName(self, DummyStruct):
        assert DummyStruct.c_definition('x') == 'struct DummyStruct x'

    def test_cDefinition_onDerivedClassName_usesOriginalNameForOutput(self, DummyStruct):
        class DerivedStruct(DummyStruct): pass
        assert DerivedStruct.c_definition() == 'struct DummyStruct'

    def test_cDefinitionFull_onEmptyStruct_ok(self):
        empty_struct = headlock.c_data_model.CStruct.typedef('strctname')
        assert empty_struct.c_definition_full() == 'struct strctname {\n}'

    def test_cDefinitionFull_onRefDef_DefWithName(self):
        empty_struct = headlock.c_data_model.CStruct.typedef('strctname')
        assert empty_struct.c_definition_full('varname') \
               == 'struct strctname {\n} varname'

    def test_cDefinitionFull_onMembers_addsOneMemberPerLine(self, DummyStruct):
        assert DummyStruct.c_definition_full() \
               == ('struct DummyStruct {\n'
                   '\tDummyInt member_int;\n'
                   '\tDummyShortInt member_short;\n'
                   '\tDummyInt member_int2;\n'
                   '}')

    def test_cDefinitionFull_onNestedStructs_notRecursive(self, DummyStruct):
        NestedStruct = headlock.c_data_model.CStruct.typedef(
            'NestedStruct',
            ('inner_strct', DummyStruct))
        assert NestedStruct.c_definition_full() \
               == ('struct NestedStruct {\n'
                   '\tstruct DummyStruct inner_strct;\n'
                   '}')

    @pytest.mark.parametrize('only_full_defs', [True, False])
    def test_iterReqCustomTypes_returnsNameOfStructBeforeNamesOfSubTypes(self, DummyStruct, only_full_defs):
        TestStruct = headlock.c_data_model.CStruct.typedef(
            'TestStruct',
            ('m1', DummyStruct), ('m2', DummyStruct))
        assert list(TestStruct.iter_req_custom_types(only_full_defs)) \
               == ['DummyStruct', 'TestStruct']

    def test_iterReqCustomTypes_onSelfReferringStruct_returnsTypeOnlyOnce(self, DummyStruct):
        TestStruct = headlock.c_data_model.CStruct.typedef('TestStruct')
        TestStruct.delayed_def(('member', TestStruct.ptr))
        assert list(TestStruct.iter_req_custom_types()) == ['TestStruct']

    def test_iterReqCustomTypes_onConstStruct_doesNotModifyReturnValue(self, DummyStruct):
        TestStruct = headlock.c_data_model.CStruct.typedef('TestStruct')
        ConstTestStruct = TestStruct.with_attr('const')
        assert list(ConstTestStruct.iter_req_custom_types()) == ['TestStruct']


@pytest.fixture
def DummyCFunc():
    return headlock.c_data_model.CFunc.typedef(
        DummyInt, DummyShortInt, DummyInt,
        returns=DummyInt)

@pytest.fixture
def dummy_callback(DummyCFunc):
    @DummyCFunc
    def dummy_callback(*args):
        return 1
    return dummy_callback

@pytest.fixture
def abs_func():
    AbsFuncType = headlock.c_data_model.CFunc.typedef(DummyInt,
                                                      returns=DummyInt)
    return AbsFuncType(ct.cdll.msvcrt.abs)


class TestCFunc:

    def test_typedef_checkAttributes(self, DummyCFunc):
        assert DummyCFunc.returns == DummyInt
        assert DummyCFunc.args == (DummyInt, DummyShortInt, DummyInt)
        assert DummyCFunc.ctypes_type._restype_ == ct.c_int
        assert DummyCFunc.ctypes_type._argtypes_ == \
               (ct.c_int, ct.c_uint16, ct.c_int)

    def test_create_fromCallable_returnPyCallbackFuncPtr(self, DummyCFunc):
        def py_dummy_callback(*args):
            assert args == (DummyInt(1), DummyShortInt(2), DummyInt(3))
            return 4
        dummy_callback = DummyCFunc(py_dummy_callback)
        assert dummy_callback.pyfunc == py_dummy_callback
        assert dummy_callback.ctypes_obj(1, 2, 3) == 4

    def test_create_fromCtypesObj_setsPyFuncToNone(self, abs_func):
        assert abs_func.pyfunc is None
        assert abs_func.ctypes_obj is ct.cdll.msvcrt.abs

    def test_create_fromCallableThatReturnsPtr_ok(self):
        var = DummyInt(0)
        func_type = headlock.c_data_model.CFunc.typedef(returns=DummyInt.ptr)
        func = func_type(lambda: var.adr)
        assert func() == var.adr

    def test_create_fromNoParam_raisesValueError(self, DummyCFunc):
        with pytest.raises(ValueError):
            _ = DummyCFunc()

    def test_getLanguage_onPyCallback_returnsPYTHON(self, dummy_callback):
        assert dummy_callback.language == 'PYTHON'

    def test_getLanguage_onCFunc_returnsC(self, abs_func):
        assert abs_func.language == 'C'

    def test_getVal_raisesValueError(self, abs_func):
        with pytest.raises(TypeError):
            _ = abs_func.val

    def test_setVal_raisesAttributeError(self, abs_func):
        with pytest.raises(TypeError):
            abs_func.val = 0

    def test_getName_onPyCallback_returnsNameOfPyFuncObj(self, dummy_callback):
        assert dummy_callback.name == 'dummy_callback'

    def test_getName_onCFunc_returnsNameOfCFunc(self, abs_func):
        assert abs_func.name == 'abs'

    def test_call_onCObjArgs_ok(self, DummyCFunc):
        @DummyCFunc
        def dummy_callback(*args):
            assert args == (DummyInt(1), DummyShortInt(2), DummyInt(3))
            return 0
        dummy_callback(DummyInt(1), DummyShortInt(2), DummyShortInt(3))

    def test_call_onPyObjArgs_ok(self, DummyCFunc):
        @DummyCFunc
        def dummy_callback(*args):
            return 4
        assert dummy_callback(DummyInt(1), DummyShortInt(2), DummyShortInt(3)) \
               == DummyInt(4)

    def test_call_onCFunc_returnsOk(self, abs_func):
        assert abs_func(-9).val == 9

    def test_call_onPyCallbackThatReturnsCObj_ok(self, DummyCFunc):
        def py_dummy_callback(*args):
            return DummyInt(4)
        dummy_callback = DummyCFunc(py_dummy_callback)
        assert dummy_callback.pyfunc == py_dummy_callback
        assert dummy_callback.ctypes_obj(1, 2, 3) == 4

    def test_call_onPyCallbackWithInvalidReturnValue_raisesValueError(self, DummyCFunc):
        @DummyCFunc
        def dummy_callback(*args):
            return "test"
        with pytest.raises(ValueError):
            dummy_callback(0, 0, 0)

    def test_call_onPyCallbackWithReturnTypeVoid_returnsNone(self):
        @headlock.c_data_model.CFunc.typedef()
        def void_func(*args):
            pass
        assert void_func() is None

    def test_call_onPyCallbackThatRaisesException_forwardsException(self):
        @headlock.c_data_model.CFunc.typedef()
        def raise_exc_func():
            raise ValueError()
        with pytest.raises(ValueError):
            raise_exc_func()

    def test_call_onWrongParamCount_raisesTypeError(self, dummy_callback):
        with pytest.raises(TypeError):
            dummy_callback(1, 2)
        with pytest.raises(TypeError):
            dummy_callback(1, 2, 3, 4)

    def test_typeEq_onNoType_returnsFalse(self, DummyCFunc):
        assert DummyCFunc != 3

    def test_typeEq_onNoneCObjType_returnsFalse(self, DummyCFunc):
        assert DummyCFunc != int

    def test_typeEq_onDifferentCObjType_returnsFalse(self, DummyCFunc):
        assert DummyCFunc != DummyInt

    def test_typeEq_onDifferentCObjButSameContent_returnsTrue(self, DummyCFunc):
        DummyCallback2 = headlock.c_data_model.CFunc.typedef(
            DummyInt, DummyShortInt, DummyInt,
            returns=DummyInt)
        assert DummyCFunc == DummyCallback2

    def test_typeEq_onDifferentReturns_returnsFalse(self, DummyCFunc):
        DummyCallback2 = headlock.c_data_model.CFunc.typedef(
            DummyInt, DummyShortInt, DummyInt,
            returns=DummyShortInt)
        assert DummyCFunc != DummyCallback2

    def test_typeEq_onDifferentArgTypes_returnsFalse(self, DummyCFunc):
        DummyCallback2 = headlock.c_data_model.CFunc.typedef(
            DummyInt, DummyShortInt, DummyInt,
            returns=DummyShortInt)
        assert DummyCFunc != DummyCallback2

    def test_typeEq_onDifferentCDecl_returnsFalse(self, DummyCFunc):
        assert DummyCFunc != DummyCFunc.with_attr('cdecl')

    def test_repr_onCallback_ok(self, dummy_callback):
        assert repr(dummy_callback).startswith(
            'CFunc(<function dummy_callback')
        assert repr(dummy_callback).endswith('>)')

    def test_repr_onCFunc_ok(self, abs_func):
        assert repr(abs_func) == "CFunc(<dll function 'abs')"

    def test_sizeof_raisesTypeError(self, DummyCFunc):
        with pytest.raises(TypeError):
            DummyCFunc.sizeof()

    def test_getPtr_onPyCallback_returnsCFuncPointer(self, dummy_callback):
        func_ptr = dummy_callback.adr
        assert isinstance(func_ptr, headlock.c_data_model.CFuncPointer)
        assert func_ptr(0, 0, 0).val == 1

    def test_getPtr_onPyCallback_setsDependsOn(self, dummy_callback):
        func_ptr = dummy_callback.adr
        assert func_ptr._depends_on_ is dummy_callback

    def test_getPtr_onCFunc_returnsCFuncPointer(self, abs_func):
        func_ptr = abs_func.adr
        assert isinstance(func_ptr, headlock.c_data_model.CFuncPointer)
        assert func_ptr(-2).val == 2

    def test_nullValue_raisesTypeError(self, DummyCFunc):
        with pytest.raises(TypeError):
            DummyCFunc.null_val

    def test_cDefinition_onVoidFunc(self):
        void_func_def = headlock.c_data_model.CFunc.typedef()
        assert void_func_def.c_definition('f') == 'void f(void)'

    def test_cDefinition_onFuncWithParamsAndReturnVal_ok(self, DummyCFunc):
        assert DummyCFunc.c_definition('f') \
               == 'DummyInt f(DummyInt p0, DummyShortInt p1, DummyInt p2)'

    def test_cDefintition_onCdeclFunc(self):
        cdecl_func_def = \
            headlock.c_data_model.CFunc.typedef().with_attr('cdecl')
        assert cdecl_func_def.c_definition('f') == 'void __cdecl f(void)'

    def test_iterReqCustomTypes_returnsMemberTypesElementaryTypes(self):
        def define_type(elem_type_name):
            class ElemType(DummyInt):
                @classmethod
                def iter_req_custom_types(cls, only_full_defs=False,already_processed=None):
                    yield elem_type_name
            return ElemType
        test_func = headlock.c_data_model.CFunc.typedef(
            define_type('test'),
            define_type('test2'),
            returns=define_type('test3'))
        assert set(test_func.iter_req_custom_types()) \
               == {'test', 'test2', 'test3'}


class TestCFuncPointer:

    def test_typedef_setsCTypesTypeToCFuncPointer(self, DummyCFunc):
        func_ptr = headlock.c_data_model.CFuncPointer.typedef(DummyCFunc)
        assert func_ptr.base_type == DummyCFunc
        assert func_ptr.ctypes_type == DummyCFunc.ctypes_type
        assert func_ptr.__name__ == DummyCFunc.__name__ + '_ptr'

    def test_create_fromPyCallable_returnPyCallbackFuncPtr(self, DummyCFunc):
        def py_dummy_callback(*args):
            assert args == (DummyInt(1), DummyShortInt(2), DummyInt(3))
            return 4
        dummy_callback = DummyCFunc.ptr(py_dummy_callback)
        del py_dummy_callback   # ensure that there is another ref to the func
        assert dummy_callback.ref.ctypes_obj(1, 2, 3) == 4

    def test_create_fromPyCallable_setsDependsOn(self):
        def py_func(): pass
        func_ptr_type = headlock.c_data_model.CFunc.typedef().ptr
        func_ptr = func_ptr_type(py_func)
        assert func_ptr._depends_on_.language == 'PYTHON'

    def test_ref_returnsObjOfTypeCFunc(self, dummy_callback):
        func_ptr = dummy_callback.adr
        assert isinstance(func_ptr.ref, headlock.c_data_model.CFunc)

    def test_sizeof_onFuncPtr_returnsMachineWordSize(self, DummyCFunc):
        dummy_cfunc_ptr = DummyCFunc.ptr(0)
        assert dummy_cfunc_ptr.sizeof == ct.sizeof(ct.c_int)

    def test_getPtr_returnsCPointer(self, DummyCFunc):
        func_ptr = DummyCFunc.ptr(0)
        func_ptr_ptr = func_ptr.adr
        assert isinstance(func_ptr_ptr, headlock.c_data_model.CPointer)
        assert func_ptr_ptr.ref == func_ptr

    def test_call_onCFunc_runsCCode(self, abs_func):
        func_ptr = abs_func.adr
        assert abs_func(-3) == 3

    def test_call_onPyCallback_runsPythonCode(self, dummy_callback):
        func_ptr = dummy_callback.adr
        assert func_ptr(11, 22, 33) == 1

    @pytest.mark.parametrize('repeat', range(100))
    def test_call_repeatedlyOnPyCallback_preservesReference(self, repeat):
        def py_func(): pass
        func_ptr_type = headlock.c_data_model.CFunc.typedef().ptr
        func_ptr = func_ptr_type(py_func)
        for c in range(100):
            func_ptr()

    def test_cDefinition_withFuncName_returnsFuncNameWithStarInBrackets(self):
        func_ptr = headlock.c_data_model.CFunc.typedef().ptr
        assert func_ptr.c_definition('f') == 'void (*f)(void)'

    def test_cDefinition_withoutFuncName_returnsOnlyStar(self):
        func_ptr = headlock.c_data_model.CFunc.typedef().ptr
        assert func_ptr.c_definition() == 'void (*)(void)'


class TestCVoid:

    def test_cDefintion_onConstAttr_returnsConstAttr(self):
        const_void = headlock.c_data_model.CVoid.with_attr('const')
        assert const_void.c_definition() == 'const void'

    def test_getMem_returnsCRawAccessWithMaxSizeNone(self):
        int = DummyInt()
        void_ptr = headlock.c_data_model.CVoid.ptr(int.adr.val)
        assert void_ptr.ref.mem.max_size is None

    def test_allocPtr_allocatesBytewise(self):
        void_ptr = headlock.c_data_model.CVoid.alloc_ptr([1, 2, 3])
        assert void_ptr.ref.mem == [1, 2, 3]

    def test_ptr_onIterable_allocatesBlockBytewise(self):
        void_ptr = headlock.c_data_model.CVoid.ptr([1, 2, 3])
        assert void_ptr.ref.mem == [1, 2, 3]
