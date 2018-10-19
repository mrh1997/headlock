import ctypes as ct
import collections, itertools
from .core import CObjType, CObj, isinstance_ctypes, WriteProtectError
from .array import CArray, map_unicode_to_list


class CPointerType(CObjType):

    PRECEDENCE = 10

    def __init__(self, base_type:CObjType, ctypes_type=None):
        super().__init__(ctypes_type or ct.POINTER(base_type.ctypes_type))
        self.base_type = base_type

    @property
    def sizeof(self):
        return ct.sizeof(self.ctypes_type)

    @property
    def null_val(cls):
        return 0

    def c_definition(self, refering_def=''):
        result = '*' + self._decorate_c_definition(refering_def)
        if self.base_type.PRECEDENCE > self.PRECEDENCE:
            result = '(' + result + ')'
        return self.base_type.c_definition(result)

    def shallow_iter_subtypes(self):
        yield self.base_type

    def __repr__(self):
        return '_'.join([repr(self.base_type)]
                        + sorted(self.c_attributes)
                        + ['ptr'])


class CPointer(CObj):

    def __init__(self, cobj_type:CPointerType, init_val=None,
                 _depends_on_=None):
        if isinstance(init_val, collections.Iterable) \
                and not isinstance(init_val, CObj) \
                and not isinstance_ctypes(init_val) \
                and not isinstance(init_val, int):
            assert _depends_on_ is None
            init_val = cobj_type.base_type.alloc_ptr(init_val)
        super().__init__(cobj_type, init_val, _depends_on_)

    @property
    def base_type(self) -> CObjType:
        return self.cobj_type.base_type

    @property
    def ref(self):
        if self.cobj_type.ctypes_type == ct.c_void_p:
            ptr = ct.cast(self.ctypes_obj, ct.POINTER(ct.c_ubyte))
        else:
            ptr = self.ctypes_obj
        return self.base_type.COBJ_CLASS(self.base_type, ptr.contents,
                                         _depends_on_=self._depends_on_)

    @property
    def _as_ctypes_int(self):
        ptr_ptr = ct.pointer(self.ctypes_obj)
        return ct.cast(ptr_ptr, ct.POINTER(ct.c_int)).contents

    @property
    def val(self):
        return self._as_ctypes_int.value

    @val.setter
    def val(self, pyobj):
        if self.cobj_type.has_attr('const') and self._initialized:
            raise WriteProtectError()
        elif isinstance(pyobj, int):
            self._as_ctypes_int.value = pyobj
        elif isinstance(pyobj, CArray) and self.base_type == pyobj.base_type:
            self.val = pyobj.adr.val
        elif isinstance(pyobj, collections.Iterable) \
                and not isinstance(pyobj, CObj):
            if isinstance(pyobj, str):
                pyobj = map_unicode_to_list(pyobj, self.base_type)
            elif isinstance(pyobj, (bytes, bytearray)):
                pyobj += b'\0'
            for ndx, item in enumerate(pyobj):
                self[ndx].val = item
        else:
            CObj.val.fset(self, pyobj)

    @property
    def c_str(self):
        for terminator_pos in itertools.count():
            if not self[terminator_pos]:
                return bytes(self[:terminator_pos])

    @c_str.setter
    def c_str(self, new_val):
        self.val = new_val

    @property
    def unicode_str(self):
        for terminator_pos in itertools.count():
            if self[terminator_pos] == 0:
                return ''.join(map(chr, self[0:terminator_pos]))

    @unicode_str.setter
    def unicode_str(self, new_val):
        self.val = new_val

    def _cast_from(self, cobj):
        if isinstance(cobj, CArray):
            self.val = cobj.adr.val
            self._depends_on_ = cobj
        else:
            super(CPointer, self)._cast_from(cobj)
            if isinstance(cobj, CPointer):
                self._depends_on_ = cobj._depends_on_

    def __repr__(self):
        digits = ct.sizeof(ct.c_int) * 2
        fmt_str = '{!r}(0x{:0' + str(digits) + 'X})'
        return fmt_str.format(self.cobj_type, self.val)

    def __add__(self, offs):
        newobj = self.copy()
        newobj += offs
        return newobj

    def __iadd__(self, offs):
        self.val += int(offs) * self.base_type.sizeof
        return self

    def __sub__(self, other):
        if isinstance(other, CPointer):
            if self.cobj_type != other.cobj_type:
                raise TypeError(
                    f'Cannot subtract pointers of different types '
                    f'({self.cobj_type.c_definition()} '
                    f'and {other.cobj_type.c_definition()})')
            return (self.val - other.val) // self.base_type.sizeof
        if isinstance(other, CArray):
            if self.cobj_type.base_type != other.cobj_type.base_type:
                raise TypeError(
                    f'Cannot subtract array from pointer of different types '
                    f'({self.cobj_type.c_definition()} '
                    f'and {other.cobj_type.c_definition()})')
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
            arr_ptr_type = self.base_type.array(ndx.stop - start).ptr
            arr_ptr = arr_ptr_type((self + start).val)
            arr = arr_ptr.ref
            arr._depends_on_ = self
            return arr
        else:
            return (self + ndx).ref

    def __int__(self):
        return self.val

CPointerType.COBJ_CLASS = CPointer
