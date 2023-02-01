from .core import CProxyType, CProxy, InvalidAddressSpaceError
from .integer import CIntType
from ..address_space import AddressSpace
from collections.abc import Iterable


def map_unicode_to_list(val, base_type):
    if not isinstance(base_type, CIntType):
        raise TypeError('Python Strings can only be assigned to '
                        'arrays/pointers of scalars')
    else:
        elem_bits = min(base_type.sizeof*8, 32)
        enc_val = val.encode(f'utf{elem_bits}')
        if elem_bits == 8:
            result = list(enc_val)
        else:
            elem_len = elem_bits // 8
            conv_val = [int.from_bytes(enc_val[pos:pos+elem_len], 'little')
                        for pos in range(0, len(enc_val), elem_len)]
            result = conv_val[1:]
        return result + [0]


class CArrayType(CProxyType):

    PRECEDENCE = 20

    def __init__(self, base_type:CProxyType, element_count:int,
                 addrspace:AddressSpace=None):
        if base_type.__addrspace__ is not addrspace:
            raise InvalidAddressSpaceError('Addressspace of self and base_type '
                                           'of pointer has to be identical')
        super().__init__(base_type.sizeof * element_count, addrspace)
        self.base_type = base_type
        self.element_count = element_count

    def bind(self, addrspace:AddressSpace):
        bound_ctype = super().bind(addrspace)
        bound_ctype.base_type = self.base_type.bind(addrspace)
        return bound_ctype

    def shallow_eq(self, other):
        return super().shallow_eq(other) \
               and self.element_count == other.element_count

    def __repr__(self):
        return '_'.join([repr(self.base_type)]
                        + sorted(self.__c_attribs__)
                        + [f'array{self.element_count}'])

    @property
    def null_val(cls):
        return [cls.base_type.null_val] * cls.element_count

    def __len__(self):
        return self.element_count

    def c_definition(self, refering_def=''):
        result = f'{refering_def}[{self.element_count}]'
        result = self._decorate_c_definition(result)
        if self.base_type.PRECEDENCE > self.PRECEDENCE:
            result = '(' + result + ')'
        return self.base_type.c_definition(result)

    def shallow_iter_subtypes(self):
        yield self.base_type
        
    def convert_to_c_repr(self, py_val):
        try:
            return super().convert_to_c_repr(py_val)
        except NotImplementedError:
            if isinstance(py_val, (bytes, bytearray)) and \
                    self.base_type.sizeof == 1:
                return py_val + (b'\x00' * (self.sizeof - len(py_val)))
            if isinstance(py_val, Iterable):
                payload = b''.join(map(self.base_type.convert_to_c_repr,py_val))
                return payload + (b'\x00' * (self.sizeof - len(payload)))
            else:
                raise

    def convert_from_c_repr(self, c_repr):
        if not len(c_repr) <= self.sizeof:
            raise ValueError('c_repr is too long')
        if len(c_repr) % self.base_type.sizeof != 0:
            raise ValueError('c_repr is not multiple of size of basetype')
        element_size = self.base_type.sizeof
        py_repr = [
            self.base_type.convert_from_c_repr(c_repr[pos:pos + element_size])
            for pos in range(0, len(c_repr), element_size)]
        return py_repr + ([0] * (self.element_count - len(py_repr)))

    @property
    def alignment(self):
        return self.base_type.alignment


class CArray(CProxy):

    @property
    def base_type(self):
        return self.ctype.base_type

    @property
    def element_count(self):
        return self.ctype.element_count

    def __len__(self):
        return len(self.ctype)

    def __getitem__(self, ndx):
        def abs_ndx(rel_ndx, ext=0):
            if -(self.element_count+ext) <= rel_ndx < 0:
                return self.element_count + rel_ndx
            elif 0 <= rel_ndx < (self.element_count+ext):
                return rel_ndx
            else:
                raise ValueError(f'ndx has to be between 0 and '
                                 f'{self.element_count} (but is {rel_ndx})')

        if isinstance(ndx, slice):
            if ndx.step is not None:
                raise ValueError('Steps are not supported in slices of CArrays')
            start = abs_ndx(ndx.start or 0)
            stop = abs_ndx(ndx.stop if ndx.stop is not None
                           else self.element_count,
                           ext=1)
            part_array_type = self.base_type.array(stop - start)
            return CArray(part_array_type,
                          self.__address__ + start*self.base_type.sizeof)
        else:
            adr = self.__address__ + abs_ndx(ndx) * self.base_type.sizeof
            return self.base_type.create_cproxy_for(adr)

    @classmethod
    def _get_len(cls):
        return cls.element_count

    def __iter__(self):
        return (self[ndx] for ndx in range(self.element_count))

    @property
    def c_str(self):
        val = self.val
        terminator_pos = val.index(0)
        return bytes(val[0:terminator_pos])

    @c_str.setter
    def c_str(self, new_val):
        if len(new_val) >= len(self):
            raise ValueError('string is too long')
        self.val = new_val

    @property
    def unicode_str(self):
        val = self.val
        terminator_pos = val.index(0)
        return ''.join(map(chr, self[0:terminator_pos]))

    @unicode_str.setter
    def unicode_str(self, new_val):
        self.val = new_val

    def __add__(self, other):
        return self[0].adr + other

    def __str__(self):
        return ''.join(chr(el.val) for el in self[0:self.element_count])

CArrayType.CPROXY_CLASS = CArray
