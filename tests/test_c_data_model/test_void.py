import pytest

import headlock.c_data_model as cdm


class TestCVoidType:

    def test_cDefintion_onConstAttr_returnsConstAttr(self):
        const_void = cdm.CVoidType().with_attr('const')
        assert const_void.c_definition('x') == 'const void x'

    def test_getMem_returnsCRawAccessWithMaxSizeNone(self, addrspace):
        cvoid_type = cdm.CVoidType(addrspace)
        cvoid_obj = cdm.void.CVoid(cvoid_type, 123)
        assert cvoid_obj.mem.max_address is None
        assert cvoid_obj.mem.address == 123

    def test_eq_onVoid_returnsTrue(self):
        assert cdm.CVoidType() == cdm.CVoidType()
