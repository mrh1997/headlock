import collections
from typing import Union
from .core import CProxyType, CProxy


class CIntType(CProxyType):

    def __init__(self, c_name, bitsize, signed, endianess, addrspace=None):
        if endianess not in ('big', 'little'):
            raise ValueError('endianess has to be "big" or "little"')
        super().__init__(bitsize // 8, addrspace)
        self.__max_val = 1 << bitsize
        self.signed = signed
        self.endianess = endianess
        self.c_name = c_name

    def shallow_eq(self, other):
        return super().shallow_eq(other) \
               and self.signed == other.signed \
               and self.endianess == other.endianess \
               and self.c_name == other.c_name

    @property
    def null_val(self):
        return 0

    def c_definition(self, refering_def=''):
        result = self._decorate_c_definition(self.c_name)
        if refering_def:
            result += ' ' + refering_def
        return result

    def __repr__(self):
        return ('ts.'
                + ''.join(a+'_' for a in sorted(self.__c_attribs__))
                + self.c_name.replace(' ', '_'))

    def convert_to_c_repr(self, py_val):
        try:
            return super().convert_to_c_repr(py_val)
        except NotImplementedError:
            if isinstance(py_val, (collections.abc.ByteString, str)):
                py_val = ord(py_val)
            cutted_val = py_val & (self.__max_val - 1)
            return cutted_val.to_bytes(self.sizeof, self.endianess)

    def convert_from_c_repr(self, c_repr):
        if len(c_repr) != self.sizeof:
            raise ValueError(f'require C Repr of length {self.sizeof}')
        result = int.from_bytes(c_repr, self.endianess)
        if self.signed and (result & self.__max_val // 2):
            result -= self.__max_val
        return result

    @property
    def alignment(self):
        return self.sizeof


class CInt(CProxy):

    def __int__(self):
        return self.val

    def __index__(self):
        return self.val

    def __repr__(self):
        if self.ctype.sizeof == 1 and self.ctype.signed:
            return f'ts.{self.ctype.c_name}({bytes([self.val])!r})'
        else:
            return super().__repr__()


CIntType.CPROXY_CLASS = CInt
