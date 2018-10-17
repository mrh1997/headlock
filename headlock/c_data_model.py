import ctypes as ct
import itertools
import sys
import collections, collections.abc
import functools
import copy


class WriteProtectError(Exception):
    """
    This exception is raised, if a const memory object shall be modified
    """


CTypePointer = type(ct.POINTER(ct.c_int))
CTypePyFuncPointer = type(ct.CFUNCTYPE(None))


def issubclass_ctypes_ptr(cls):
    return cls == ct.c_char_p or cls == ct.c_wchar_p or \
           isinstance(cls, CTypePointer) or isinstance(cls, CTypePyFuncPointer)


def issubclass_ctypes(cls):
    # this is a dirty hack, as there is no access to the public visible
    # common base class of ctypes objects
    return cls.__mro__[-2].__name__ == '_CData' or \
           issubclass(cls, (ct.Structure, ct.Union))


def isinstance_ctypes(obj):
    return issubclass_ctypes(type(obj))


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


@functools.total_ordering
class CMemory:

    def __init__(self, addr, max_size=None, readonly=False):
        super().__init__()
        self.addr = addr
        self.max_size = max_size
        self.readonly = readonly

    @property
    def _ctypes_obj(self):
        ptr = ct.POINTER(ct.c_ubyte)()
        ptr_ptr = ct.cast(ct.pointer(ptr), ct.POINTER(ct.c_uint))
        ptr_ptr.contents.value = self.addr
        return ptr

    def __check_ndx(self, ndx):
        if isinstance(ndx, slice):
            if ndx.stop is None:
                raise IndexError(f'End of slice has to be defined ({ndx})')
            if (ndx.start or 0) < 0 or ndx.stop < 0 or (ndx.step or 1) < 0:
                raise IndexError(f'Negative values are not supported in '
                                 f'slices ({ndx})')
            if self.max_size is not None and ndx.stop > self.max_size:
                raise IndexError(f'End of slice ({ndx.stop}) '
                                 f'exceeds max_size ({self.max_size})')
        else:
            if ndx < 0:
                raise IndexError(f'Negative Indices are not supported ({ndx})')
            if self.max_size is not None and ndx >= self.max_size:
                raise IndexError(f'Index ({ndx}) '
                                 f'exceeds max_size ({self.max_size})')

    def __getitem__(self, ndx):
        self.__check_ndx(ndx)
        result = self._ctypes_obj[ndx]
        if isinstance(ndx, slice):
            return bytes(result)
        else:
            return result

    def __setitem__(self, ndx, value):
        if self.readonly:
            raise WriteProtectError()
        self.__check_ndx(ndx)
        if isinstance(ndx, slice):
            ctypes_obj = self._ctypes_obj
            indeces = range(ndx.start or 0, ndx.stop, ndx.step or 1)
            for n, v in zip(indeces, value):
                ctypes_obj[n] = v
        else:
            self._ctypes_obj[ndx] = value

    def __iter__(self):
        return map(self.__getitem__, itertools.count(0))

    def __repr__(self):
        result = f"{type(self).__name__}({hex(self.addr)}"
        if self.max_size is not None:
            result += f', {self.max_size}'
        if self.readonly:
            result += f', readonly=True'
        return result + ')'

    def __eq__(self, other):
        try:
            other_as_bytes = bytes(other)
            other_len = len(other)
        except TypeError:
            return False
        else:
            return self[:other_len] == other_as_bytes

    def __gt__(self, other):
        return self[:len(other)] > bytes(other)


class CObjType:

    COBJ_CLASS:type = None

    PRECEDENCE = 0

    def __init__(self, ctypes_type):
        self.c_attributes = frozenset()
        self.ctypes_type = ctypes_type
        self._ptr = None

    def __call__(self, init_obj=None, _depends_on_=None):
        return self.COBJ_CLASS(self, init_obj, _depends_on_)

    def __bool__(self):
        return True

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return NotImplemented
        else:
            remaining = [(self, other)]
            processed = set()
            while remaining:
                (self_cobj_type, other_cobj_type) = remaining.pop()
                if (id(self_cobj_type), id(other_cobj_type)) not in processed:
                    if not self_cobj_type.shallow_eq(other_cobj_type):
                        return False
                    remaining += zip(self_cobj_type.shallow_iter_subtypes(),
                                     other_cobj_type.shallow_iter_subtypes())
                    processed.add( (id(self_cobj_type), id(other_cobj_type)) )
            return True

    def shallow_eq(self, other):
        return type(self) == type(other) \
               and self.c_attributes == other.c_attributes

    def __hash__(self):
        return hash(self.c_definition())

    def __iter__(self):
        return self.shallow_iter_subtypes()

    @property
    def ptr(self):
        # this is an optimization to avoid creating a new Pointer type
        # everytime a pointer to this type is required
        if self._ptr is None:
            self._ptr = CPointerType(self)
        return self._ptr

    def array(self, element_count):
        return CArrayType(self, element_count)

    def alloc_array(self, initval):
        if isinstance(initval, collections.abc.Iterable):
            if not isinstance(initval, collections.abc.Collection):
                initval = list(initval)
            elif isinstance(initval, str):
                initval = map_unicode_to_list(initval, self)
            elif isinstance(initval, collections.abc.ByteString):
                initval = initval + b'\0'
            return self.array(len(initval))(initval)
        else:
            return self.array(initval)()

    def alloc_ptr(self, initval):
        array = self.alloc_array(initval)
        return self.ptr(array.adr, _depends_on_=array)

    @property
    def sizeof(self):
        raise NotImplementedError('this is an abstract base class')

    @property
    def null_val(self):
        raise NotImplementedError('this is an abstract base class')

    def c_definition(self, refering_def=''):
        raise NotImplementedError('this is an abstract base class')

    def _decorate_c_definition(self, c_def):
        return ''.join(attr + ' ' for attr in sorted(self.c_attributes)) + c_def

    def with_attr(self, attr_name):
        if attr_name in self.c_attributes:
            raise ValueError(f'attribute {attr_name} is already set')
        derived = copy.copy(self)
        derived.c_attributes = self.c_attributes | {attr_name}
        return derived

    def iter_subtypes(self, top_level_last=False, filter=None,
                      parent=None, processed=None):
        if processed is None:
            processed = set()
        ident = self.ident()
        if ident not in processed:
            if filter is None or filter(self, parent):
                processed.add(ident)
                if not top_level_last:
                    yield self
                for sub_type in self.shallow_iter_subtypes():
                    yield from sub_type.iter_subtypes(top_level_last, filter,
                                                      self, processed)
                if top_level_last:
                    yield self

    def ident(self):
        return id(self)

    def shallow_iter_subtypes(self):
        return iter([])

    def has_attr(self, attr_name):
        return attr_name in self.c_attributes


class CObj:

    def __init__(self, cobj_type:CObjType, init_obj=None, _depends_on_=None):
        super(CObj, self).__init__()
        self.cobj_type =  cobj_type
        self._initialized = False
        self._depends_on_ = _depends_on_
        if isinstance_ctypes(init_obj):
            self.ctypes_obj = init_obj
        else:
            self.ctypes_obj = self.cobj_type.ctypes_type()
            if init_obj is None:
                self.val = self.cobj_type.null_val
            elif isinstance(init_obj, CObj):
                self._cast_from(init_obj)
            else:
                self.val = init_obj
        self._initialized = True

    def __repr__(self):
        return f'{self.cobj_type!r}({self.val!r})'

    def __bool__(self):
        return self.val != self.cobj_type.null_val

    @property
    def adr(self):
        # type: () -> CPointer
        ptr = self.cobj_type.ptr
        return ptr(ptr.ctypes_type(self.ctypes_obj), _depends_on_=self)

    @property
    def sizeof(self):
        return self.cobj_type.sizeof

    def _cast_from(self, cobj):
        self.val = cobj.val

    @property
    def val(self):
        raise NotImplementedError('this is an abstract base class')

    @val.setter
    def val(self, pyobj):
        if isinstance(pyobj, CObj):
            self.val = pyobj.val
        else:
            try:
                self.mem = pyobj
            except TypeError:
                raise ValueError(f'{pyobj!r} cannot be converted to {self!r}')

    def __eq__(self, other):
        if isinstance(other, CObj):
            return self.val == other.val
        else:
            return self.val == other

    def __ne__(self, other):
        return not self == other

    def __gt__(self, other):
        if isinstance(other, CObj):
            return self.cobj_type == self.cobj_type and self.val > other.val
        else:
            return self.val > other

    def __lt__(self, other):
        if isinstance(other, CObj):
            return self.cobj_type == self.cobj_type and self.val < other.val
        else:
            return self.val < other

    def __ge__(self, other):
        if isinstance(other, CObj):
            return self.cobj_type == self.cobj_type and self.val >= other.val
        else:
            return self.val >= other

    def __le__(self, other):
        if isinstance(other, CObj):
            return self.cobj_type == self.cobj_type and self.val <= other.val
        else:
            return self.val <= other

    def __add__(self, other):
        return self.cobj_type(self.val + int(other))

    def __sub__(self, other):
        return self.cobj_type(self.val - int(other))

    def __radd__(self, other):
        return self.cobj_type(int(other) + self.val)

    def __rsub__(self, other):
        return self.cobj_type(int(other) - self.val)

    def __iadd__(self, other):
        self.val += int(other)
        return self

    def __isub__(self, other):
        self.val -= int(other)
        return self

    def copy(self):
        return self.cobj_type(self.val)

    @property
    def mem(self):
        readonly = self.cobj_type.has_attr('const')
        return CMemory(ct.addressof(self.ctypes_obj), None, readonly)

    @mem.setter
    def mem(self, new_val):
        if self.cobj_type.has_attr('const'):
            raise WriteProtectError()
        ptr = ct.cast(ct.pointer(self.ctypes_obj), ct.POINTER(ct.c_ubyte))
        for ndx in range(len(new_val)):
            ptr[ndx] = new_val[ndx]


class CVoidType(CObjType):

    def __init__(self):
        super().__init__(None)

    @property
    def sizeof(self):
        raise NotImplementedError('.sizeof does not work on void')

    def alloc_ptr(self, initval):
        array = BuildInDefs.unsigned_char.alloc_array(initval)
        return self.ptr(array.adr, _depends_on_=array)

    def c_definition(self, refering_def=''):
        result = self._decorate_c_definition('void')
        if refering_def:
            result += ' ' + refering_def
        return result


class CVoidObj(CObj):
    pass


CVoidType.COBJ_CLASS = CVoidObj


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


class CFloatType(CObjType):
    """This is a dummy yet"""

    def __init__(self, c_name, bits, ctypes_type):
        super().__init__(ctypes_type)
        self.bits = bits
        self.c_name = c_name


class CFloat(CObj):
    """This is a dummy yet"""
    pass

CFloatType.COBJ_CLASS = CFloat


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


class CArrayType(CObjType):

    PRECEDENCE = 20

    def __init__(self, base_type:CObjType, element_count:int, ctypes_type=None):
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


class CArray(CObj):

    @property
    def base_type(self):
        return self.cobj_type.base_type

    @property
    def element_count(self):
        return self.cobj_type.element_count

    def __len__(self):
        return len(self.cobj_type)

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
                self.cobj_type.ctypes_type.from_address(adr(start)),
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

CArrayType.COBJ_CLASS = CArray


class CStructType(CObjType):

    __NEXT_ANONYMOUS_ID__ = 1

    def __init__(self, struct_name, members=None, packing=None):
        if not struct_name:
            struct_name = f'__anonymous_{CStructType.__NEXT_ANONYMOUS_ID__}__'
            CStructType.__NEXT_ANONYMOUS_ID__ += 1
        self._packing_ = packing or 4
        self._members_ = None
        self._members_order_ = None
        ctypes_type = type('ctypes_' + struct_name,
                           (ct.Structure,),
                           {'_pack_': self._packing_})
        super().__init__(ctypes_type)
        self.struct_name = struct_name
        if members is not None:
            self.delayed_def(members)

    def delayed_def(self, member_types):
        self._members_ = dict(member_types)
        self._members_order_ = [nm for nm, tp in member_types]
        if member_types:
            self.ctypes_type._fields_ = [(nm, cobj_type.ctypes_type)
                                         for nm, cobj_type in member_types]
        for nm, cobj_type in member_types:
            if nm and not hasattr(self, nm):
                setattr(self, nm, cobj_type)

    def __call__(self, *args, _depends_on_=None, **argv):
        argv.update(zip(self._members_order_, args))
        return super().__call__(argv, _depends_on_)

    def __len__(self):
        return len(self._members_)

    @property
    def sizeof(self):
        return ct.sizeof(self.ctypes_type)

    @property
    def null_val(cls):
        return {name: cobj_type.null_val
                for name, cobj_type in cls._members_.items()}

    def shallow_eq(self, other):
        return super().shallow_eq(other) \
               and self._packing_ == other._packing_ \
               and self._members_order_ == other._members_order_

    def __hash__(self):
        return super().__hash__()

    def is_anonymous_struct(self):
        return self.struct_name.startswith('__anonymous_')

    def c_definition(self, refering_def=''):
        if self.is_anonymous_struct():
            return self.c_definition_full(refering_def)
        else:
            return self.c_definition_base(refering_def)

    def c_definition_base(self, refering_def=''):
        result = self._decorate_c_definition(
            'struct' if self.is_anonymous_struct() else
            f'struct {self.struct_name}')
        if refering_def:
            result += ' ' + refering_def
        return result

    def c_definition_full(self, refering_def=''):
        space = ' ' if refering_def else ''
        body = '{\n' \
               + ''.join(f'\t{line}\n'
                         for mname in self._members_order_
                         for line in (
                                 self._members_[mname].c_definition(mname) + ';')
                                                                .splitlines()) \
               + '}'
        return self.c_definition_base(refering_def=body + space + refering_def)

    def shallow_iter_subtypes(self):
        if self._members_ is not None:
            yield from self._members_.values()

    def ident(self):
        return id(self) if self.is_anonymous_struct() else \
               'struct '+self.struct_name

    def __repr__(self):
        return ('ts.struct.'
                + ''.join(a+'_' for a in sorted(self.c_attributes))
                + self.struct_name.replace(' ', '_'))



class CStruct(CObj):

    def __repr__(self):
        params = (name + '=' + repr(cobj.val)
                  for name, cobj in zip(self.cobj_type._members_order_, self))
        return repr(self.cobj_type) + '(' + ', '.join(params) + ')'

    def __getitem__(self, member_id):
        if isinstance(member_id, str):
            member_name = member_id
        else:
            member_name = self.cobj_type._members_order_[member_id]
        member_type = self.cobj_type._members_[member_name]
        struct_adr = ct.addressof(self.ctypes_obj)
        offset = getattr(self.cobj_type.ctypes_type, member_name).offset
        ctypes_obj = member_type.ctypes_type.from_address(struct_adr + offset)
        return member_type.COBJ_CLASS(member_type, ctypes_obj,_depends_on_=self)

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    @property
    def tuple(self):
        return tuple(cobj.val for cobj in self)

    @tuple.setter
    def tuple(self, new_tuple):
        if len(new_tuple) > len(self.cobj_type._members_):
            raise ValueError('too much entries in tuple')
        else:
            self.val = dict(zip(self.cobj_type._members_order_, new_tuple))

    @property
    def val(self):
        return {name: cobj.val
                for name, cobj in zip(self.cobj_type._members_order_, self)}

    @val.setter
    def val(self, new_val):
        if isinstance(new_val, collections.Iterator):
            new_val = list(new_val)
        if isinstance(new_val, collections.Sequence):
            new_val = dict(zip(self.cobj_type._members_order_, new_val))
        for name in self.cobj_type._members_order_:
            member = self[name]
            try:
                val = new_val[name]
            except KeyError:
                member.val = member.cobj_type.null_val
            else:
                member.val = val

    def __len__(self):
        return len(self.cobj_type._members_)


CStructType.COBJ_CLASS = CStruct


class CUnionType(CStructType):
    """This is a dummy yet"""

CUnion = CStruct


class CVectorType(CIntType):
    """This is a dummy yet"""

    name = 'vector'

    def __init__(self, name=None):
        super().__init__(name or '', 32, False, ct.c_int)

CVector = CInt


class CEnumType(CIntType):

    def __init__(self, name=None):
        super().__init__(name or '', 32, False, ct.c_int)

    def c_definition(self, refering_def=''):
        return 'enum ' + self.c_name \
               + (' '+refering_def if refering_def else '')

CEnum = CInt


last_tunnelled_exception = None

class CFuncType(CObjType):

    PRECEDENCE = 20

    def __init__(self, returns:CObjType=None, args:list=None):
        self.returns = returns
        self.args = args or []
        self.language = "C"
        if returns is None:
            self.ctypes_returns = None
        elif issubclass_ctypes_ptr(returns.ctypes_type):
            self.ctypes_returns = ct.c_void_p
        else:
            self.ctypes_returns = returns.ctypes_type
        self.ctypes_args = tuple(cobj_type.ctypes_type
                                 for cobj_type in self.args)
        super().__init__(
            ct.CFUNCTYPE(self.ctypes_returns, *self.ctypes_args))

    def shallow_eq(self, other):
        return super().shallow_eq(other) \
               and ((self.returns is None and other.returns is None)
                    or (self.returns is not None and other.returns is not None)) \
               and len(self.args) == len(other.args)

    def shallow_iter_subtypes(self):
        if self.returns:
            yield self.returns
        yield from self.args

    @property
    def sizeof(self):
        raise TypeError('cannot retrieve size of c/python function')

    @property
    def ptr(self):
        return CFuncPointerType(self)

    @property
    def null_val(cls):
        raise TypeError('Function objects do not support null vals')

    def _decorate_c_definition(self, c_def):
        if self.has_attr('cdecl'):
            return '__cdecl ' + super()._decorate_c_definition(c_def)
        else:
            return super()._decorate_c_definition(c_def)

    def c_definition(self, refering_def=''):
        if not refering_def:
            raise TypeError('.c_definition() for CFuncType objects always '
                            'require a referring_def')
        if len(self.args) == 0:
            partype_strs = ('void',)
        else:
            partype_strs = (arg.c_definition(f'p{ndx}')
                            for ndx, arg in enumerate(self.args))
        rettype = self.returns or CVoidType()
        deco = (refering_def) + '('+', '.join(partype_strs)+')'
        return rettype.c_definition(self._decorate_c_definition(deco))

    def __repr__(self):
        arg_repr_str = ', '.join(map(repr, self.args))
        attr_calls_str = ''.join(f'.with_attr({attr!r})'
                                 for attr in sorted(self.c_attributes))
        return f'CFuncType({self.returns!r}, [{arg_repr_str}]){attr_calls_str}'

    def __call__(self, init_obj=None, _depends_on_=None, logger=None):
        return self.COBJ_CLASS(self, init_obj, _depends_on_, logger=logger)


class CFunc(CObj):

    def __init__(self, cobj_type:CFuncType, init_obj=None, name:str=None,
                 logger=None, _depends_on_:CObj=None):
        cobj_type:CFuncType
        if not callable(init_obj):
            raise ValueError('expect callable as first parameter')
        self.name = name or (init_obj.__name__
                             if hasattr(init_obj, '__name__') else None)
        if isinstance_ctypes(init_obj):
            self.language = 'C'
            self.pyfunc = None
        elif isinstance(init_obj, CObj):
            pass
        else:
            self.language = 'PYTHON'
            self.pyfunc = init_obj
            init_obj = cobj_type.ctypes_type(self.wrapped_pyfunc(
                init_obj,
                self.name,
                cobj_type.args,
                cobj_type.returns,
                logger))
        self.logger = logger
        super(CFunc, self).__init__(cobj_type, init_obj, _depends_on_)

    @staticmethod
    def wrapped_pyfunc(pyfunc, name, arg_types, return_type, logger):
        def wrapper(*args):
            global last_tunnelled_exception
            if last_tunnelled_exception is not None:
                if logger:
                    logger.write('<call '+name+
                                 'failed due to preceeding exception>')
                return None if return_type is None else return_type.null_val
            params = [arg_type(arg)
                      for arg_type, arg in zip(arg_types, args)]
            try:
                if logger:
                    logger.write('    ' + (name or '<unknown>'))
                    logger.write('('+(', '.join(map(repr, params)))+')')
                result = pyfunc(*params)
                if return_type is not None:
                    result_obj = return_type(result)
                    if logger:
                        logger.write('->' + repr(result_obj) + '\n')
                    return result_obj.val
                else:
                    if logger:
                        logger.write('\n')
            except Exception:
                last_tunnelled_exception = sys.exc_info()
                if logger:
                    logger.write('!>'+repr(last_tunnelled_exception[1])+'\n')
                return None if return_type is None else return_type.null_val
        return wrapper

    def __call__(self, *args):
        global last_tunnelled_exception
        if len(args) != len(self.cobj_type.args):
            raise TypeError(f'{self.name}() requires {len(self.cobj_type.args)} '
                            f'parameters, but got {len(args)}')
        args = [arg_cls(arg) for arg_cls, arg in zip(self.cobj_type.args, args)]
        if self.logger:
            self.logger.write(self.name or '???')
            self.logger.write('(' + ', '.join(map(repr, args)) + ')\n')
        self.ctypes_obj.argtypes = self.cobj_type.ctypes_args
        self.ctypes_obj.restype = self.cobj_type.ctypes_returns
        result = self.ctypes_obj(*[a.ctypes_obj for a in args])
        if last_tunnelled_exception is not None:
            exc = last_tunnelled_exception
            last_tunnelled_exception = None
            raise exc[0](exc[1]).with_traceback(exc[2])
        elif self.cobj_type.returns is None:
            return None
        else:
            result = self.cobj_type.returns(result)
            if self.logger:
                self.logger.write('-> ' +  repr(result) + '\n')
            return result

    @property
    def _as_ctypes_int(self):
        ptr_ptr = ct.pointer(self.ctypes_obj)
        return ct.cast(ptr_ptr, ct.POINTER(ct.c_int)).contents

    @property
    def val(self):
        raise TypeError()

    @val.setter
    def val(self, new_val):
        raise TypeError()

    def __repr__(self):
        if self.language == 'C':
            return f"<CFunc of C Function {self.name or '???'!r}>"
        elif self.language == 'PYTHON':
            return f"<CFunc of Python Callable {self.name or '???'!r}>"

    @property
    def adr(self):
        ctypes_ptr = ct.cast(ct.pointer(self.ctypes_obj), ct.POINTER(ct.c_int))
        return self.cobj_type.ptr(ctypes_ptr.contents.value, _depends_on_=self)

CFuncType.COBJ_CLASS = CFunc


class CFuncPointerType(CPointerType):

    def __init__(self, base_type:CObjType, ctypes_type=None):
        if not isinstance(base_type, CFuncType):
            raise TypeError('Expect CFuncPointerType refer to CFuncType')
        super().__init__(base_type, ctypes_type or base_type.ctypes_type)

class CFuncPointer(CPointer):

    def __init__(self, cobj_type:CFuncPointerType, init_obj, _depends_on_=None):
        if callable(init_obj) and not isinstance_ctypes(init_obj) and \
                not isinstance(init_obj, CObj):
            cfunc_obj = cobj_type.base_type(init_obj)
            if _depends_on_ is None:
                _depends_on_ = cfunc_obj
            init_obj = cfunc_obj.ctypes_obj
        super().__init__(cobj_type, init_obj, _depends_on_=_depends_on_)

    def __call__(self, *args):
        return self.ref(*args)

    @property
    def ref(self):
        return self.base_type(self.ctypes_obj)

CFuncPointerType.COBJ_CLASS = CFuncPointer


class BuildInDefs:

    long_long = CIntType('long long', 64, True, ct.c_int64)
    signed_long_long = CIntType('signed long long', 64, True, ct.c_int64)
    unsigned_long_long = CIntType('unsigned long long', 64, False, ct.c_uint64)

    int = CIntType('int', 32, True, ct.c_int32)
    signed_int = CIntType('signed int', 32, True, ct.c_int32)
    unsigned_int = CIntType('unsigned int', 32, False, ct.c_uint32)

    short = CIntType('short', 16, True, ct.c_int16)
    signed_short = CIntType('signed short', 16, True, ct.c_int16)
    unsigned_short = CIntType('unsigned short', 16, False, ct.c_uint16)

    long = CIntType('long', 32, True, ct.c_int32)
    signed_long = CIntType('signed long', 32, True, ct.c_int32)
    unsigned_long = CIntType('unsigned long', 32, False, ct.c_uint32)

    char = CIntType('char', 8, False, ct.c_char)
    signed_char = CIntType('signed char', 8, False, ct.c_char)
    unsigned_char = CIntType('unsigned char', 8, False, ct.c_ubyte)

    float = CFloatType('float', 32, ct.c_float)

    double = CFloatType('double', 64, ct.c_double)

    long_double = CFloatType('long double', 80, ct.c_longdouble)

    _Bool = CIntType('_Bool', 8, False, ct.c_bool)

    void = CVoidType()


# add names with '__' in front manually...
setattr(BuildInDefs, '__builtin_va_list', BuildInDefs.void.ptr)