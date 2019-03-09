import pytest
import ctypes as ct
from unittest.mock import Mock

from headlock.address_space.virtual import VirtualAddressSpace
from headlock.c_data_model.memory_access import CMemory, WriteProtectError
import headlock.c_data_model as cdm


class TestCMemory:

    @pytest.fixture
    def testdata(self):
        return b'\x12\x34\x56\x78'

    @pytest.fixture()
    def addrspace(self, testdata):
        return VirtualAddressSpace(b'\xFF' + testdata + b'\xEE\xFF')

    def test_init_onAddressOnly_setsAttributes(self, addrspace):
        cmem_obj = CMemory(addrspace, 0x1234)
        assert cmem_obj.addrspace == addrspace
        assert cmem_obj.address == 0x1234
        assert cmem_obj.max_address is None
        assert not cmem_obj.readonly

    def test_init_onMaxAddrAndReadOnly_setsAttributes(self, addrspace):
        cmem_obj = CMemory(addrspace, 0, 1234, readonly=True)
        assert cmem_obj.max_address == 1234
        assert cmem_obj.readonly

    @pytest.fixture
    def cmem_obj(self, testdata, addrspace):
        return CMemory(addrspace, 1, 5)

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

    def test_setItem_onIndex_setsInteger(self, cmem_obj, addrspace, testdata):
        cmem_obj[2] = 0xaa
        assert addrspace.content[1:5] == b'\x12\x34\xaa\x78'

    def test_setItem_onSlice_setsByteLike(self, cmem_obj, addrspace):
        cmem_obj[1:3] = b'\xaa\xbb'
        assert addrspace.content[1:5] == b'\x12\xaa\xbb\x78'

    def test_setItem_onSliceWithSteps_setsByteLike(self, cmem_obj, addrspace):
        cmem_obj[1:4:2] = b'\xaa\xbb'
        assert addrspace.content[1:5] == b'\x12\xaa\x56\xbb'

    def test_setItem_onReadOnly_raisesWriteProtectError(self, addrspace):
        ro_raw_access = CMemory(addrspace, 1, readonly=True)
        with pytest.raises(WriteProtectError):
            ro_raw_access[2] = 0x99

    def test_setItem_onInvalidIndex_raisesIndexError(self, cmem_obj):
        with pytest.raises(IndexError):
            cmem_obj[-1] = 1

    def test_iter_ok(self, cmem_obj):
        cmem_obj.max_size = None
        raw_iter = iter(cmem_obj)
        assert [next(raw_iter) for c in range(4)] == [0x12, 0x34, 0x56, 0x78]

    def test_iter_onExceedMaxSize_raisesIndexError(self, cmem_obj):
        raw_iter = iter(cmem_obj)
        for c in range(4): next(raw_iter)
        with pytest.raises(IndexError):
            next(raw_iter)

    def test_eq_onIdenticalStr_returnsTrue(self, cmem_obj, testdata):
        assert cmem_obj == testdata

    def test_eq_onShorterStringButIdenticalBytesAtBegin_returnsTrue(self, cmem_obj, testdata):
        assert cmem_obj == testdata[:-1]

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
