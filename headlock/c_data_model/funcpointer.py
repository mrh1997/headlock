from .core import CObjType, CObj, isinstance_ctypes
from .pointer import CPointerType, CPointer
from .function import CFuncType


class CFuncPointerType(CPointerType):

    def __init__(self, base_type:CObjType, ctypes_type=None):
        if not isinstance(base_type, CFuncType):
            raise TypeError('Expect CFuncPointerType refer to CFuncType')
        super().__init__(base_type, ctypes_type or base_type.ctypes_type)

class CFuncPointer(CPointer):

    def __init__(self, cobj_type:CFuncPointerType, init_obj, _depends_on_=None):
        if callable(init_obj) and not isinstance_ctypes(init_obj) and \
                not isinstance(init_obj, CObj):
            cfunc_obj = cobj_type.base_type(init_obj)
            if _depends_on_ is None:
                _depends_on_ = cfunc_obj
            init_obj = cfunc_obj.ctypes_obj
        super().__init__(cobj_type, init_obj, _depends_on_=_depends_on_)

    def __call__(self, *args):
        return self.ref(*args)

    @property
    def ref(self):
        return self.base_type(self.ctypes_obj)

CFuncPointerType.COBJ_CLASS = CFuncPointer
