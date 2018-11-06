import ctypes as ct
from .core import CProxyType, CProxy
from .integer import CIntType


def map_unicode_to_list(val, base_type):
    if not isinstance(base_type, CIntType):
        raise TypeError('Python Strings can only be assigned to '
                        'arrays/pointers of scalars')
    else:
        elem_bits = min(base_type.bits, 32)
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

    def __init__(self, base_type:CProxyType, element_count:int, ctypes_type=None):
        super().__init__(ctypes_type or base_type.ctypes_type * element_count)
        self.base_type = base_type
        self.element_count = element_count

    def shallow_eq(self, other):
        return super().shallow_eq(other) \
               and self.element_count == other.element_count

    def __repr__(self):
        return '_'.join([repr(self.base_type)]
                        + sorted(self.c_attributes)
                        + [f'array{self.element_count}'])

    @property
    def sizeof(cls):
        return cls.base_type.sizeof * cls.element_count

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

        def adr(abs_ndx):
            return ct.addressof(self.ctypes_obj) + \
                   abs_ndx * self.sizeof // self.element_count

        if isinstance(ndx, slice):
            if ndx.step is not None:
                raise ValueError('Steps are not supported in slices of CArrays')
            start = abs_ndx(ndx.start or 0)
            stop = abs_ndx(ndx.stop if ndx.stop is not None
                           else self.element_count,
                           ext=1)
            part_array_type = self.base_type.array(stop - start)
            return part_array_type(
                self.ctype.ctypes_type.from_address(adr(start)),
                _depends_on_=self)
        else:
            return self.base_type(
                self.base_type.ctypes_type.from_address(adr(abs_ndx(ndx))),
                _depends_on_=self)

    @classmethod
    def _get_len(cls):
        return cls.element_count

    def __iter__(self):
        return (self[ndx] for ndx in range(self.element_count))

    @property
    def val(self):
        return [self[ndx].val for ndx in range(self.element_count)]

    @val.setter
    def val(self, new_val):
        if isinstance(new_val, str):
            new_val = map_unicode_to_list(new_val, self.base_type)
        ndx = 0
        for ndx, val in enumerate(new_val):
            self[ndx].val = val
        for ndx2 in range(ndx+1, self.element_count):
            self[ndx2].val = self.base_type.null_val

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
        return ''.join(chr(c) for c in self.val[0:self.element_count])

CArrayType.CPROXY_CLASS = CArray
