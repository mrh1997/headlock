import ctypes as ct
from .core import CProxyType, CProxy
from .integer import CIntType


class CVoidType(CProxyType):

    def __init__(self):
        super().__init__(None)

    @property
    def sizeof(self):
        raise NotImplementedError('.sizeof does not work on void')

    def c_definition(self, refering_def=''):
        result = self._decorate_c_definition('void')
        if refering_def:
            result += ' ' + refering_def
        return result


class CVoid(CProxy):
    pass


CVoidType.CPROXY_CLASS = CVoid