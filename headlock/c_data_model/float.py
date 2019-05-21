from .core import CProxyType, CProxy

class CFloatType(CProxyType):
    """This is a dummy yet"""

    def __init__(self, c_name, bits):
        super().__init__(bits//8)
        self.bits = bits
        self.c_name = c_name


class CFloat(CProxy):
    """This is a dummy yet"""
    pass

CFloatType.CPROXY_CLASS = CFloat
