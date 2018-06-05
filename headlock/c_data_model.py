import ctypes as ct
import itertools
import sys
import collections, collections.abc


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
    return cls.__mro__[-2].__name__ == '_CData'

def isinstance_ctypes(obj):
    return issubclass_ctypes(type(obj))


class CObjType(type):

    def __init__(self, *args, **argv):
        super(CObjType, self).__init__(*args, **argv)
        self._ptr = None

    def __len__(self):
        return self._get_len()

    def __bool__(self):
        return True

    def __eq__(self, other):
        return self._type_equality(other, frozenset())

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return id(self)

    @property
    def ptr(self):
        return self._get_ptr_type()

    def array(self, element_count):
        return CArray.typedef(self, element_count)

    @property
    def sizeof(self):
        return self._get_sizeof()

    @property
    def null_val(self):
        return self._get_null_val()

    def with_attr(self, attr_name):
        if attr_name in self.c_attributes:
            raise TypeError(f'attribute {self.__name__} is already set')
        if self.c_attributes:
            parent = self.__mro__[1]
        else:
            parent = self
        prefix = (attr_name+'_') if attr_name in ('volatile', 'const') else ''
        c_attributes = parent.c_attributes | {attr_name}
        return type(prefix + self.__name__,
                    (parent,),
                    {'c_attributes': c_attributes,
                     'c_name': parent.c_name or parent.__name__})


class CRawAccess:
    """
    This class is *not* derived from collections.abc.Sequence as it is not
    cmpletely compatible as __getitem__ works also on greater addresses
    """

    def __init__(self, ctypes_obj, readonly=False):
        super().__init__()
        self.ctypes_obj = ctypes_obj
        self.readonly = readonly

    def __len__(self):
        x = ct.sizeof(self.ctypes_obj)
        return x

    def __getitem__(self, ndx):
        ptr = ct.cast(ct.pointer(self.ctypes_obj), ct.POINTER(ct.c_ubyte))
        if isinstance(ndx, slice):
            return bytes(ptr[ndx])
        else:
            return ptr[ndx]

    def __setitem__(self, ndx, value):
        if self.readonly:
            raise WriteProtectError()
        ptr = ct.cast(ct.pointer(self.ctypes_obj), ct.POINTER(ct.c_ubyte))
        if not isinstance(ndx, slice):
            ptr[ndx] = value
        else:
            assert ndx.step is None
            start = ndx.start or 0
            if start < 0:
                start += ct.sizeof(self.ctypes_obj)
            stop = ndx.stop or ct.sizeof(self.ctypes_obj)
            if stop < 0:
                stop += ct.sizeof(self.ctypes_obj)
            slice_range = range(start, stop)
            for rel_ndx, abs_ndx in enumerate(slice_range):
                ptr[abs_ndx] = value[rel_ndx]

    def __iter__(self):
        ptr = ct.cast(ct.pointer(self.ctypes_obj), ct.POINTER(ct.c_ubyte))
        return (ptr[ndx] for ndx in range(ct.sizeof(self.ctypes_obj)))

    def __bytes__(self):
        return bytes(memoryview(self.ctypes_obj))

    def __repr__(self):
        bytes_as_hex = ' '.join(format(b, '02X') for b in self)
        return f"{type(self).__name__}('{bytes_as_hex}')"

    def __eq__(self, other):
        return bytes(self) == other

    def __ne__(self, other):
        return bytes(self) != other

    def __add__(self, other):
        return bytes(self) + other

    def __radd__(self, other):
        return other + bytes(self)

    def __mul__(self, other):
        return bytes(self) * other

    def hex(self):
        return bytes(self).hex()


class CObj(metaclass=CObjType):

    c_name = None

    c_attributes = frozenset()

    ctypes_type = None

    PRECEDENCE = 0

    def __init__(self, init_obj=None, _depends_on_=None):
        super(CObj, self).__init__()
        self._initialized = False
        self._depends_on_ = _depends_on_
        if isinstance_ctypes(init_obj):
            self.ctypes_obj = init_obj
        else:
            self.ctypes_obj = self.ctypes_type()
            if init_obj is None:
                self.val = self.null_val
            elif isinstance(init_obj, CObj):
                self._cast_from(init_obj)
            else:
                self.val = init_obj
        self._initialized = True

    def __repr__(self):
        return type(self).__name__ + '(' + repr(self.val) + ')'

    def __len__(self):
        return self._get_len()

    def __bool__(self):
        return self.val != self.null_val

    @classmethod
    def _get_ptr_type(cls):
        if cls._ptr is None:
            cls._ptr = CPointer.typedef(cls)
        return cls._ptr

    @property
    def ptr(self):
        # type: () -> CPointer
        ptr = self._get_ptr_type()
        return ptr(ptr.ctypes_type(self.ctypes_obj), _depends_on_=self)

    @property
    def sizeof(self):
        return self._get_sizeof()

    @classmethod
    def _get_sizeof(self):
        raise NotImplementedError('this is an abstract base class')

    @classmethod
    def _get_len(cls):
        raise TypeError(f"object of type '{cls.__name__}' has no len()")

    def _cast_from(self, cobj):
        self.val = cobj.val

    @property
    def null_val(self):
        return self._get_null_val()

    @classmethod
    def _get_null_val(cls):
        raise NotImplementedError('this is an abstract base class')

    @classmethod
    def c_definition(cls, refering_def=''):
        raise NotImplementedError('this is an abstract base class')

    @classmethod
    def _decorate_c_definition(cls, c_def):
        if cls.has_attr('const'):
            c_def = 'const ' + c_def
        if cls.has_attr('volatile'):
            c_def = 'volatile ' + c_def
        return c_def

    def _get_val(self):
        raise NotImplementedError('this is an abstract base class')

    def _set_val(self, pyobj):
        if isinstance(pyobj, CObj):
            self.val = pyobj.val
        else:
            try:
                self.raw = pyobj
            except TypeError:
                raise ValueError(f'{pyobj!r} cannot be converted to {self!r}')

    @property
    def val(self):
        return self._get_val()

    @val.setter
    def val(self, pyobj):
        self._set_val(pyobj)

    def __eq__(self, other):
        if isinstance(other, CObj):
            return self.val == other.val
        else:
            return self.val == other

    def __ne__(self, other):
        return not self == other

    def __gt__(self, other):
        if isinstance(other, CObj):
            return type(self) == type(other) and self.val > other.val
        else:
            return self.val > other

    def __lt__(self, other):
        if isinstance(other, CObj):
            return type(self) == type(other) and self.val < other.val
        else:
            return self.val < other

    def __ge__(self, other):
        if isinstance(other, CObj):
            return type(self) == type(other) and self.val >= other.val
        else:
            return self.val >= other

    def __le__(self, other):
        if isinstance(other, CObj):
            return type(self) == type(other) and self.val <= other.val
        else:
            return self.val <= other

    def __add__(self, other):
        return type(self)(self.val + int(other))

    def __sub__(self, other):
        return type(self)(self.val - int(other))

    def __radd__(self, other):
        return type(self)(int(other) + self.val)

    def __rsub__(self, other):
        return type(self)(int(other) - self.val)

    def __iadd__(self, other):
        self.val += int(other)
        return self

    def __isub__(self, other):
        self.val -= int(other)
        return self

    def copy(self):
        return type(self)(self.val)

    @classmethod
    def _type_equality(cls, other, recursions):
        return other is cls

    @property
    def raw(self):
        return CRawAccess(self.ctypes_obj, readonly=self.has_attr('const'))

    @raw.setter
    def raw(self, new_val):
        if self.has_attr('const'):
            raise WriteProtectError()
        ptr = ct.cast(ct.pointer(self.ctypes_obj), ct.POINTER(ct.c_ubyte))
        for ndx in range(len(new_val)):
            ptr[ndx] = new_val[ndx]

    @classmethod
    def iter_req_custom_types(cls, only_full_defs=False,already_processed=None):
        return iter([])

    @classmethod
    def has_attr(cls, attr_name):
        return attr_name in cls.c_attributes


class CVoid(CObj):

    c_name = 'void'

    @classmethod
    def _get_sizeof(cls):
        raise NotImplementedError('.sizeof does not work on void')

    @classmethod
    def c_definition(cls, refering_def=''):
        result = cls._decorate_c_definition('void')
        if refering_def:
            result += ' ' + refering_def
        return result

class CInt(CObj):

    bits = None
    signed = None

    @classmethod
    def _get_sizeof(cls):
        return cls.bits // 8

    @classmethod
    def _get_null_val(cls):
        return 0

    def _get_val(self):
        return self.ctypes_obj.value

    def _set_val(self, pyobj):
        if self.has_attr('const') and self._initialized:
            raise WriteProtectError()
        if pyobj is None:
            pyobj = 0

        if isinstance(pyobj, int):
            self.ctypes_obj.value = pyobj
        else:
            super(CInt, self)._set_val(pyobj)

    @classmethod
    def _type_equality(cls, other, recursions):
        return isinstance(other, CObjType) \
               and issubclass(other, CInt) \
               and cls.bits == other.bits \
               and cls.signed == other.signed \
               and cls.c_attributes == other.c_attributes

    @classmethod
    def c_definition(cls, refering_def=''):
        result = cls._decorate_c_definition(cls.c_name or cls.__name__)
        if refering_def:
            result += ' ' + refering_def
        return result

    def __int__(self):
        return self.val

    def __index__(self):
        return self.val


class CFloat(CObj):
    """This is a dummy yet"""


class CPointer(CObj):

    base_type = CObj

    PRECEDENCE = 10

    @classmethod
    def typedef(cls, base_type):
        return type(base_type.__name__ + '_ptr',
                    (cls,),
                    dict(base_type=base_type,
                         ctypes_type=ct.POINTER(base_type.ctypes_type)))

    @property
    def ref(self):
        if self.ctypes_type == ct.c_void_p:
            ptr = ct.cast(self.ctypes_obj, ct.POINTER(ct.c_ubyte))
        else:
            ptr = self.ctypes_obj
        return self.base_type(ptr.contents, _depends_on_=self._depends_on_)

    @property
    def _as_ctypes_int(self):
        ptr_ptr = ct.pointer(self.ctypes_obj)
        return ct.cast(ptr_ptr, ct.POINTER(ct.c_int)).contents

    @classmethod
    def _get_sizeof(cls):
        return ct.sizeof(cls.ctypes_type)

    @classmethod
    def _get_null_val(cls):
        return 0

    @classmethod
    def _type_equality(cls, other, recursions):
        return isinstance(other, CObjType) \
               and issubclass(other, CPointer) \
               and cls.c_attributes == other.c_attributes \
               and cls.base_type._type_equality(other.base_type, recursions) \
               and cls.c_attributes == other.c_attributes

    def _get_val(self):
        return self._as_ctypes_int.value

    def _set_val(self, pyobj):
        if self.has_attr('const') and self._initialized:
            raise WriteProtectError()
        elif isinstance(pyobj, int):
            self._as_ctypes_int.value = pyobj
        elif isinstance(pyobj, CArray) and self.base_type == pyobj.base_type:
            self.val = pyobj.ptr.val
        elif isinstance(pyobj, str):
            for pos, val in enumerate(pyobj):
                self[pos].val = ord(val)
        elif isinstance(pyobj, collections.Iterable) \
            and not isinstance(pyobj, (CObj,
                                       CRawAccess,
                                       collections.abc.ByteString,
                                       memoryview)):
            lst = list(pyobj)
            array_type = self.base_type.array(len(lst))
            array = array_type(lst)
            self.val = array
            self._depends_on_ = array
        else:
            super()._set_val(pyobj)

    @property
    def cstr(self):
        for terminator_pos in itertools.count():
            if self[terminator_pos] == 0:
                return ''.join(chr(c) for c in self[:terminator_pos])

    @cstr.setter
    def cstr(self, new_val):
        self.val = new_val

    def _cast_from(self, cobj):
        if isinstance(cobj, CArray):
            self.val = cobj.ptr.val
            self._depends_on_ = cobj
        else:
            super(CPointer, self)._cast_from(cobj)
            if isinstance(cobj, CPointer):
                self._depends_on_ = cobj._depends_on_

    def __repr__(self):
        digits = ct.sizeof(ct.c_int) * 2
        fmt_str = '{}(0x{:0' + str(digits) + 'X})'
        return fmt_str.format(type(self).__name__, self.val)

    def __add__(self, offs):
        newobj = self.copy()
        newobj += offs
        return newobj

    def __iadd__(self, offs):
        self.val += int(offs) * self.base_type.sizeof
        return self

    def __sub__(self, other):
        if isinstance(other, CPointer):
            if type(self) != type(other):
                raise TypeError(
                    f'Cannot subtract pointers of different types '
                    f'({type(self).__name__} and {type(other).__name__})')
            return (self.val - other.val) // self.base_type.sizeof
        if isinstance(other, CArray):
            if self.base_type != other.base_type:
                raise TypeError(
                    f'Cannot subtract array from pointer of different '
                    f'types ({type(self).__name__} and {type(other).__name__})')
            return (self.val - other[0].ptr.val) // self.base_type.sizeof
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

    @classmethod
    def c_definition(cls, refering_def=''):
        result = '*' + cls._decorate_c_definition(refering_def)
        if cls.base_type.PRECEDENCE > cls.PRECEDENCE:
            result = '(' + result + ')'
        return cls.base_type.c_definition(result)

    @classmethod
    def iter_req_custom_types(cls, only_full_defs=False,already_processed=None):
        if not only_full_defs:
            yield from cls.base_type.iter_req_custom_types(only_full_defs,
                                                           already_processed)


class CArray(CObj):

    element_count = 0
    base_type = CObj

    PRECEDENCE = 20

    @classmethod
    def typedef(cls, base_type, element_count):
        return type(base_type.__name__ + '_' + str(element_count),
                    (cls,),
                    dict(base_type=base_type,
                         element_count=element_count,
                         ctypes_type=base_type.ctypes_type * element_count))

    @classmethod
    def _get_sizeof(cls):
        return cls.base_type.sizeof * cls.element_count

    @classmethod
    def _get_null_val(cls):
        return [cls.base_type.null_val] * cls.element_count

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
                self.ctypes_type.from_address(adr(start)),
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

    def _get_val(self):
        return [self[ndx].val for ndx in range(self.element_count)]

    def _set_val(self, new_val):
        if isinstance(new_val, str):
            if len(new_val) > len(self):
                raise ValueError('string is too long')
            self.val = list(map(ord, new_val)) + [0]*(len(self) - len(new_val))
        else:
            try:
                super()._set_val(memoryview(new_val))
            except TypeError:
                ndx = 0
                for ndx, val in enumerate(new_val):
                    self[ndx].val = val
                for ndx2 in range(ndx+1, self.element_count):
                    self[ndx2].val = self.base_type.null_val

    @property
    def cstr(self):
        val = self.val
        terminator_pos = val.index(0)
        return ''.join(chr(c) for c in val[0:terminator_pos])

    @cstr.setter
    def cstr(self, new_val):
        if len(new_val) >= len(self):
            raise ValueError('string is too long')
        self.val = new_val

    def __add__(self, other):
        return self[0].ptr + other

    def __str__(self):
        return ''.join(chr(c) for c in self.val[0:self.element_count])

    @classmethod
    def _type_equality(cls, other, recursions):
        return isinstance(other, CObjType) \
               and issubclass(other, CArray) \
               and cls.c_attributes == other.c_attributes \
               and other.element_count == cls.element_count \
               and other.base_type._type_equality(cls.base_type, recursions)

    @classmethod
    def c_definition(cls, refering_def=''):
        result = f'{refering_def}[{cls.element_count}]'
        result = cls._decorate_c_definition(result)
        if cls.base_type.PRECEDENCE > cls.PRECEDENCE:
            result = '(' + result + ')'
        return cls.base_type.c_definition(result)

    @classmethod
    def iter_req_custom_types(cls, only_full_defs=False,already_processed=None):
        yield from cls.base_type.iter_req_custom_types(only_full_defs,
                                                       already_processed)


class CMember(object):

    def __init__(self, name):
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:
            return owner._members_[self.name]
        else:
            return instance[self.name]


class CStruct(CObj):

    c_name = None
    _packing_ = None
    _members_ = {}
    _members_order_ = []
    __NEXT_ANONYMOUS_ID__ = 1

    def __init__(self, *args, _depends_on_=None, **argv):
        if len(args) == 1 and isinstance_ctypes(args[0]):
            super(CStruct, self).__init__(*args, **argv)
        else:
            super(CStruct, self).__init__(_depends_on_=_depends_on_)
            argv.update(zip(self._members_order_, args))
            self.val = argv

    def __repr__(self):
        params = (name + '=' + repr(cobj.val)
                  for name, cobj in zip(self._members_order_, self))
        return type(self).__name__ + '(' + ', '.join(params) + ')'

    @classmethod
    def typedef(cls, name, *members, packing=None):
        ct_dct = dict()
        if packing is not None:
            ct_dct['_pack_'] = packing
        ct_type = type(cls.__name__ + '_ctype', (ct.Structure,), ct_dct)
        if not name:
            name = f'__anonymous_{cls.__NEXT_ANONYMOUS_ID__}__'
            cls.__NEXT_ANONYMOUS_ID__ += 1
        new_type = type(name or '<anonymous>',
                        (cls,),
                        dict(_packing_=packing,
                             ctypes_type=ct_type,
                             c_name=name))
        if members:
            new_type.delayed_def(*members)
        return new_type

    def __getitem__(self, member_id):
        if isinstance(member_id, str):
            member_name = member_id
        else:
            member_name = self._members_order_[member_id]
        member_type = self._members_[member_name]
        struct_adr = ct.addressof(self.ctypes_obj)
        offset = getattr(self.ctypes_type, member_name).offset
        ctypes_obj = member_type.ctypes_type.from_address(struct_adr + offset)
        return member_type(ctypes_obj, _depends_on_=self)

    @classmethod
    def _get_len(cls):
        return len(cls._members_)

    @property
    def tuple(self):
        return tuple(cobj.val for cobj in self)

    @tuple.setter
    def tuple(self, new_tuple):
        if len(new_tuple) > len(self._members_):
            raise ValueError('too much entries in tuple')
        else:
            self.val = dict(zip(self._members_order_, new_tuple))

    def _get_val(self):
        return {name: cobj.val
                for name, cobj in zip(self._members_order_, self)}

    def _set_val(self, new_val):
        try:
            self.raw = memoryview(new_val)
        except TypeError:
            if isinstance(new_val, collections.Sequence):
                new_val = dict(zip(self._members_order_, new_val))
            for name in self._members_order_:
                member = self[name]
                try:
                    val = new_val[name]
                except KeyError:
                    member.val = member.null_val
                else:
                    member.val = val

    @classmethod
    def _get_sizeof(cls):
        return ct.sizeof(cls.ctypes_type)

    @classmethod
    def _get_null_val(cls):
        return {name: type.null_val
                for name, type in cls._members_.items()}

    @classmethod
    def _type_equality(cls, other, recursions):
        if (id(cls), id(other)) in recursions:
            return True
        else:
            new_recursions = recursions | {(id(cls), id(other))}
            return isinstance(other, CObjType) \
                   and issubclass(other, CStruct) \
                   and cls.c_attributes == other.c_attributes \
                   and other._packing_ == cls._packing_ \
                   and other._members_order_ == cls._members_order_ \
                   and all(cls_m._type_equality(other_m, new_recursions)
                           for cls_m, other_m in zip(cls._members_.values(),
                                                     other._members_.values()))

    @classmethod
    def c_definition(cls, refering_def=''):
        result = cls._decorate_c_definition(f'struct {cls.c_name}')
        if refering_def:
            result += ' ' + refering_def
        return result

    @classmethod
    def c_definition_full(cls, refering_def=''):
        space = ' ' if refering_def else ''
        body = '{\n' \
               + ''.join(f'\t{cls._members_[mname].c_definition(mname)};\n'
                         for mname in cls._members_order_) \
               + '}'
        return cls.c_definition(refering_def=body + space + refering_def)

    @classmethod
    def delayed_def(cls, *members):
        for name, _ in members:
            if not hasattr(cls, name):
                setattr(cls, name, CMember(name))
        cls.ctypes_type._fields_ = [(nm, cobj.ctypes_type)
                                    for nm, cobj in members]
        cls._members_ = dict(members)
        cls._members_order_ = [nm for nm,_ in members]

    @classmethod
    def iter_req_custom_types(cls, only_full_defs=False,already_processed=None):
        if already_processed is None:
            already_processed = set()
        if cls.c_name not in already_processed:
            already_processed.add(cls.c_name)
            for member in cls._members_.values():
                yield from member.iter_req_custom_types(only_full_defs,
                                                        already_processed)
            yield cls.c_name


class CEnum(CInt):
    """
    Dummy implementation for CEnum
    """
    bits = 32
    ctypes_type = ct.c_int
    c_name = 'enum'


last_tunnelled_exception = None

class CFunc(CObj):

    returns = CObj
    args = ()
    name = None
    pyfunc = None
    language = "C"
    PRECEDENCE = 20

    def __init__(self, init_obj=None, logger=None, _depends_on_=None):
        if not callable(init_obj):
            raise ValueError('expect callable as first parameter')
        self.logger = logger
        if isinstance_ctypes(init_obj):
            self.language = 'C'
            self.pyfunc = None
        elif not isinstance(init_obj, CObj):
            self.language = 'PYTHON'
            self.pyfunc = init_obj
            init_obj = self.ctypes_type(self.wrapped_pyfunc(
                init_obj,
                init_obj.__name__ if hasattr(init_obj,'__name__')else '???',
                self.args,
                self.returns,
                logger))
        super(CFunc, self).__init__(init_obj, _depends_on_)

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
                    logger.write('    ' + name)
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

    @classmethod
    def typedef(cls, *args, returns=None):
        if returns is None:
            ctypes_returns = None
        elif issubclass_ctypes_ptr(returns.ctypes_type):
            ctypes_returns = ct.c_void_p
        else:
            ctypes_returns = returns.ctypes_type
        ctypes_args = [arg.ctypes_type for arg in args]
        dct = dict(
            args=args,
            returns=returns,
            ctypes_args=ctypes_args,
            ctypes_returns=ctypes_returns,
            ctypes_type=ct.CFUNCTYPE(ctypes_returns, *ctypes_args))
        return type(cls.__name__, (cls,), dct)

    def __call__(self, *args):
        global last_tunnelled_exception
        if len(args) != len(self.args):
            raise TypeError(f'{self.name}() requires {len(self.args)} '
                            f'parameters, but got {len(args)}')
        args = [arg_type(arg) for arg_type, arg in zip(self.args, args)]
        if self.logger:
            self.logger.write(self.name or '???')
            self.logger.write('(' + ', '.join(map(repr, args)) + ')\n')
        self.ctypes_obj.argtypes = self.ctypes_args
        self.ctypes_obj.restype = self.ctypes_returns
        result = self.ctypes_obj(*[a.ctypes_obj for a in args])
        if last_tunnelled_exception is not None:
            exc = last_tunnelled_exception
            last_tunnelled_exception = None
            raise exc[0](exc[1]).with_traceback(exc[2])
        elif self.returns is None:
            return None
        else:
            result = self.returns(result)
            if self.logger:
                self.logger.write('-> ' +  repr(result) + '\n')
            return result

    @classmethod
    def _type_equality(cls, other, recursions):
        if not isinstance(other, CObjType) or not issubclass(other, CFunc):
            return False
        if cls.c_attributes != other.c_attributes:
            return False
        if cls.returns is None:
            if other.returns is not None:
                return False
        else:
            if other.returns is None:
                return False
            if not cls.returns._type_equality(other.returns, recursions):
                return False
        return all(cls_a._type_equality(other_a, recursions)
                   for cls_a, other_a in zip(cls.args, other.args))

    @property
    def name(self):
        if self.language == 'PYTHON':
            return self.pyfunc.__name__
        elif self.language == 'C':
            try:
                return self.ctypes_obj.__name__
            except AttributeError:
                return f'_func_at_adr_{self.ptr.val}'

    @property
    def _as_ctypes_int(self):
        ptr_ptr = ct.pointer(self.ctypes_obj)
        return ct.cast(ptr_ptr, ct.POINTER(ct.c_int)).contents

    def _get_val(self):
        raise TypeError()

    def _set_val(self, new_val):
        raise TypeError()

    @property
    def sizeof(self):
        raise TypeError('cannot retrieve size of c/python function')

    def __repr__(self):
        if self.language == 'C':
            return f"{type(self).__name__}(<dll function '{self.name}')"
        elif self.language == 'PYTHON':
            return f'{type(self).__name__}({self.pyfunc})'

    @property
    def ptr(self):
        ptr_ptr = ct.cast(ct.pointer(self.ctypes_obj), ct.POINTER(ct.c_int))
        return type(self).ptr(ptr_ptr.contents.value, _depends_on_=self)

    @classmethod
    def _get_ptr_type(cls):
        return CFuncPointer.typedef(cls)

    @classmethod
    def _get_sizeof(self):
        raise TypeError('Function objects do not support sizeof')

    @classmethod
    def _get_null_val(cls):
        raise TypeError('Function objects do not support null vals')

    @classmethod
    def _decorate_c_definition(cls, c_def):
        if cls.has_attr('cdecl'):
            return '__cdecl ' + super()._decorate_c_definition(c_def)
        else:
            return super()._decorate_c_definition(c_def)

    @classmethod
    def c_definition(cls, refering_def=''):
        if len(cls.args) == 0:
            partype_strs = ('void',)
        else:
            partype_strs = (arg.c_definition(f'p{ndx}')
                 for ndx, arg in enumerate(cls.args))
        rettype = cls.returns or CVoid
        return rettype.c_definition(cls._decorate_c_definition(refering_def) +
                                    '('+', '.join(partype_strs)+')')

    @classmethod
    def iter_req_custom_types(cls, only_full_defs=False,already_processed=None):
        for arg in cls.args:
            yield from arg.iter_req_custom_types(only_full_defs,
                                                 already_processed)
        yield from (cls.returns or CVoid).iter_req_custom_types(
            only_full_defs, already_processed)


class CFuncPointer(CPointer):

    def __init__(self, init_obj, _depends_on_=None):
        if callable(init_obj) and not isinstance_ctypes(init_obj) and \
                not isinstance(init_obj, CObj):
            func_obj = self.base_type(init_obj)
            if _depends_on_ is None:
                _depends_on_ = func_obj
            super().__init__(func_obj.ptr, _depends_on_=_depends_on_)
        else:
            super().__init__(init_obj, _depends_on_=_depends_on_)

    def __call__(self, *args):
        return self.ref(*args)

    @classmethod
    def typedef(cls, base_type):
        return type(base_type.__name__ + '_ptr',
                    (cls,),
                    dict(base_type=base_type,
                         ctypes_type=base_type.ctypes_type))

    @property
    def ref(self):
        return self.base_type(self.ctypes_obj)


class BuildInDefs:

    class long_long(CInt):
        bits = 64
        signed = True
        ctypes_type = ct.c_longlong
        c_name = 'long long'

    class signed_long_long(long_long):
        c_name = 'signed long long'

    class unsigned_long_long(CInt):
        bits = 64
        signed = False
        ctypes_type = ct.c_ulonglong
        c_name = 'unsigned long long'

    class int(CInt):
        bits = 8*ct.sizeof(ct.c_int)
        signed = True
        ctypes_type = ct.c_int
        c_name = 'int'

    class unsigned_int(CInt):
        bits = 8*ct.sizeof(ct.c_int)
        signed = False
        ctypes_type = ct.c_uint
        c_name = 'unsigned int'

    class signed_int(int):
        c_name = 'signed int'

    class short(CInt):
        bits = 8*ct.sizeof(ct.c_short)
        signed = True
        ctypes_type = ct.c_short
        c_name = 'short'

    class unsigned_short(CInt):
        bits = 8*ct.sizeof(ct.c_short)
        signed = False
        ctypes_type = ct.c_ushort
        c_name = 'unsigned short'

    class signed_short(short):
        c_name = 'signed short'

    class long(CInt):
        bits = 8*ct.sizeof(ct.c_long)
        signed = True
        ctypes_type = ct.c_long
        c_name = 'long'

    class unsigned_long(CInt):
        bits = 8*ct.sizeof(ct.c_ulong)
        signed = False
        ctypes_type = ct.c_ulong
        c_name = 'unsigned long'

    class signed_long(long):
        c_name = 'signed long'

    class char(CInt):
        bits = 8
        signed = True
        ctypes_type = ct.c_byte
        c_name = 'char'

    class unsigned_char(CInt):
        bits = 8
        signed = False
        ctypes_type = ct.c_ubyte
        c_name = 'unsigned char'

    class signed_char(char):
        c_name = 'signed char'

    class float(CFloat):
        bits = 32
        ctypes_type = ct.c_float
        c_name = 'float'

    class double(CFloat):
        bits = 64
        ctypes_type = ct.c_double
        c_name = 'double'

    class long_double(double):
        pass

    class _Bool(CInt):
        bits = 8
        signed = False
        ctypes_type = ct.c_bool

    void = CVoid

    # the following definitions are not builtin -> they should be removed

    NULL = void.ptr(0)

    def __mem__(self, init, *args):
        mem = ct.create_string_buffer(bytes(init), *args)
        return self.void.ptr(ct.pointer(mem), _depends_on_=mem)


# add names with '__' in front manually...
setattr(BuildInDefs, '__builtin_va_list', BuildInDefs.void.ptr)