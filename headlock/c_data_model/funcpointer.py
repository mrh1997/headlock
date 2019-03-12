from .pointer import CPointerType, CPointer
from .function import CFuncType
from ..address_space import AddressSpace


class CFuncPointerType(CPointerType):

    def __init__(self, base_type:CFuncType, bitsize:int, endianess:str,
                 addrspace:AddressSpace=None):
        # if not isinstance(base_type, CFuncType):
        #     raise TypeError('Expect CFuncPointerType refer to CFuncType')
        super().__init__(base_type, bitsize, endianess, addrspace)

    def convert_to_c_repr(self, py_val):
        try:
            return super().convert_to_c_repr(py_val)
        except NotImplementedError:
            if callable(py_val):
                cfunc_type = self.base_type(py_val)
                return super().convert_to_c_repr(cfunc_type.val)
            else:
                raise



class CFuncPointer(CPointer):

    def __call__(self, *args):
        return self.ref(*args)

CFuncPointerType.CPROXY_CLASS = CFuncPointer
