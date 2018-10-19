import pytest
import ctypes as ct

import headlock.c_data_model as cdm


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
