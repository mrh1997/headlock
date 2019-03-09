import collections.abc
from .core import CProxyType, CProxy
from .pointer import CPointerType
from ..address_space import AddressSpace



class CVoidType(CProxyType):

    def __init__(self, addrspace:AddressSpace=None):
        super().__init__(None, addrspace)

    def c_definition(self, refering_def=''):
        result = self._decorate_c_definition('void')
        if refering_def:
            result += ' ' + refering_def
        return result


class CVoid(CProxy):
    pass


CVoidType.CPROXY_CLASS = CVoid