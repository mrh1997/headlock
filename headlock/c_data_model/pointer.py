import collections, itertools
from .core import CProxyType, CProxy, InvalidAddressSpaceError
from .array import CArray, map_unicode_to_list
from ..address_space import AddressSpace


class CPointerType(CProxyType):

    PRECEDENCE = 10

    def __init__(self, base_type:CProxyType, bitsize:int, endianess:str,
                 addrspace:AddressSpace=None):
        if base_type.__addrspace__ is not addrspace:
            raise InvalidAddressSpaceError('Addressspace of self and base_type '
                                           'of pointer has to be identical')
        super().__init__(bitsize // 8, addrspace)
        self.endianess = endianess
        self.base_type = base_type

    def bind(self, addrspace):
        bound = super().bind(addrspace)
        bound.base_type = bound.base_type.bind(addrspace)
        return bound

    @property
    def null_val(cls):
        return 0

    def c_definition(self, refering_def=''):
        result = '*' + self._decorate_c_definition(refering_def)
        if self.base_type.PRECEDENCE > self.PRECEDENCE:
            result = '(' + result + ')'
        return self.base_type.c_definition(result)

    def shallow_eq(self, other):
        return super().shallow_eq(other) \
               and self.endianess == other.endianess

    def shallow_iter_subtypes(self):
        yield self.base_type

    def __repr__(self):
        return '_'.join([repr(self.base_type)]
                        + sorted(self.__c_attribs__)
                        + ['ptr'])

    def convert_to_c_repr(self, py_val):
        if isinstance(py_val, CArray):
            return self.convert_to_c_repr(py_val.__address__)
        else:
            try:
                return super().convert_to_c_repr(py_val)
            except NotImplementedError:
                if isinstance(py_val, collections.abc.Iterable):
                    cptr_obj = self.base_type.alloc_ptr(py_val)
                    return self.convert_to_c_repr(cptr_obj.val)
                elif isinstance(py_val, int):
                    cutted_val = py_val & ((1 << (self.sizeof*8)) - 1)
                    return cutted_val.to_bytes(self.sizeof, self.endianess)
                else:
                    raise

    def convert_from_c_repr(self, c_repr):
        if len(c_repr) != self.sizeof:
            raise ValueError(f'require C Repr of length {self.sizeof}')
        return int.from_bytes(c_repr, self.endianess)

    @property
    def alignment(self):
        return self.sizeof


class CPointer(CProxy):

    @property
    def base_type(self) -> CProxyType:
        return self.ctype.base_type

    @property
    def ref(self):
        return self.base_type.create_cproxy_for(self.val)

    @property
    def c_str(self):
        string = []
        for terminator_pos in itertools.count():
            if self[terminator_pos] == 0:
                break
            else:
                string.append(self[terminator_pos])
        return bytes(string)

    @c_str.setter
    def c_str(self, new_val):
        for ndx, b in enumerate(itertools.chain(new_val, [0])):
            self[ndx].val = b

    @property
    def unicode_str(self):
        string = []
        for terminator_pos in itertools.count():
            if self[terminator_pos] == 0:
                break
            else:
                string.append(self[terminator_pos])
        return ''.join(map(chr, string))

    @unicode_str.setter
    def unicode_str(self, new_val):
        if not isinstance(new_val, str):
            raise TypeError(f'Except Type str, got {type(new_val)}')
        for ndx, ch in enumerate(map_unicode_to_list(new_val, self.base_type)):
            self[ndx].val = ch

    def __repr__(self):
        digits = self.ctype.sizeof * 2
        fmt_str = '{!r}(0x{:0' + str(digits) + 'X})'
        return fmt_str.format(self.ctype, self.val)

    def __add__(self, offs):
        newobj = self.copy()
        newobj += offs
        return newobj

    def __iadd__(self, offs):
        self.val += int(offs) * self.base_type.sizeof
        return self

    def __sub__(self, other):
        if isinstance(other, CPointer):
            if self.ctype != other.ctype:
                raise TypeError(
                    f'Cannot subtract pointers of different types '
                    f'({self.ctype.c_definition()} '
                    f'and {other.ctype.c_definition()})')
            return (self.val - other.val) // self.base_type.sizeof
        if isinstance(other, CArray):
            if self.ctype.base_type != other.ctype.base_type:
                raise TypeError(
                    f'Cannot subtract array from pointer of different types '
                    f'({self.ctype.c_definition()} '
                    f'and {other.ctype.c_definition()})')
            return (self.val - other[0].adr.val) // self.base_type.sizeof
        else:
            newobj = self.copy()
            newobj -= int(other)
            return newobj

    def __isub__(self, offs):
        self.val -= int(offs) * self.base_type.sizeof
        return self

    def __getitem__(self, ndx):
        if isinstance(ndx, slice):
            if ndx.step is not None:
                raise ValueError('Steps are not supported '
                                 'in slices of CPointers')
            start = ndx.start or 0
            carray_type = self.base_type.array(ndx.stop - start)
            return CArray(carray_type, (self + start).val)
        else:
            return (self + ndx).ref

    def __int__(self):
        return self.val

CPointerType.CPROXY_CLASS = CPointer
