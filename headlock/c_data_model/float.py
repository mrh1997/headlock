from .core import CObjType, CObj

class CFloatType(CObjType):
    """This is a dummy yet"""

    def __init__(self, c_name, bits, ctypes_type):
        super().__init__(ctypes_type)
        self.bits = bits
        self.c_name = c_name


class CFloat(CObj):
    """This is a dummy yet"""
    pass

CFloatType.COBJ_CLASS = CFloat
