import collections

from .core import CObjType, CObj


class CIntType(CObjType):

    def __init__(self, c_name, bits, signed, ctypes_type):
        super().__init__(ctypes_type)
        self.bits = bits
        self.signed = signed
        self.c_name = c_name

    def shallow_eq(self, other):
        return super().shallow_eq(other) \
               and self.bits == other.bits \
               and self.signed == other.signed \
               and self.c_name == other.c_name

    @property
    def sizeof(self):
        return self.bits // 8

    @property
    def null_val(self):
        return 0

    def c_definition(self, refering_def=''):
        result = self._decorate_c_definition(self.c_name)
        if refering_def:
            result += ' ' + refering_def
        return result

    def __repr__(self):
        return ('ts.' \
                + ''.join(a+'_' for a in sorted(self.c_attributes)) \
                + self.c_name.replace(' ', '_'))

class CInt(CObj):

    @property
    def val(self):
        result = self.ctypes_obj.value
        if isinstance(result, bytes):
            return result[0]
        else:
            return result

    @val.setter
    def val(self, pyobj):
        if pyobj is None:
            pyobj = 0
        elif isinstance(pyobj, (collections.abc.ByteString, str)):
            if len(pyobj) != 1:
                raise ValueError(f'{pyobj!r} must contain exactly 1 character')
            pyobj = ord(pyobj)

        if isinstance(pyobj, int):
            self.ctypes_obj.value = pyobj
        else:
            CObj.val.fset(self, pyobj)

    def __int__(self):
        return self.val

    def __index__(self):
        return self.val

    def __repr__(self):
        if self.cobj_type.bits == 8 and self.cobj_type.signed:
            return f'ts.{self.cobj_type.c_name}({bytes([self.val])!r})'
        else:
            return super().__repr__()


CIntType.COBJ_CLASS = CInt
