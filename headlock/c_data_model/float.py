from .core import CProxyType, CProxy

class CFloatType(CProxyType):
    """This is a dummy yet"""

    def __init__(self, c_name, bits, ctypes_type):
        super().__init__(ctypes_type)
        self.bits = bits
        self.c_name = c_name


class CFloat(CProxy):
    """This is a dummy yet"""
    pass

CFloatType.CPROXY_CLASS = CFloat
