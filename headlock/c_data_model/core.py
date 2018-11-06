import collections, copy
import ctypes as ct
from .memory_access import CMemory, WriteProtectError



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


class CProxyType:

    CPROXY_CLASS:type = None

    PRECEDENCE = 0

    def __init__(self, ctypes_type):
        self.c_attributes = frozenset()
        self.ctypes_type = ctypes_type

    def __call__(self, init_obj=None, _depends_on_=None):
        return self.CPROXY_CLASS(self, init_obj, _depends_on_)

    def __bool__(self):
        return True

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return NotImplemented
        else:
            remaining = [(self, other)]
            processed = set()
            while remaining:
                (self_ctype, other_ctype) = remaining.pop()
                if (id(self_ctype), id(other_ctype)) not in processed:
                    if not self_ctype.shallow_eq(other_ctype):
                        return False
                    remaining += zip(self_ctype.shallow_iter_subtypes(),
                                     other_ctype.shallow_iter_subtypes())
                    processed.add( (id(self_ctype), id(other_ctype)) )
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
        raise NotImplementedError()

    def array(self, element_count):
        raise NotImplementedError()

    def alloc_array(self, initval):
        raise NotImplementedError()

    def alloc_ptr(self, initval):
        raise NotImplementedError()

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


class CProxy:

    def __init__(self, ctype:CProxyType, init_obj=None, _depends_on_=None):
        super(CProxy, self).__init__()
        self.ctype =  ctype
        self._initialized = False
        self._depends_on_ = _depends_on_
        if isinstance_ctypes(init_obj):
            self.ctypes_obj = init_obj
        else:
            self.ctypes_obj = self.ctype.ctypes_type()
            if init_obj is None:
                self.val = self.ctype.null_val
            elif isinstance(init_obj, CProxy):
                self._cast_from(init_obj)
            else:
                self.val = init_obj
        self._initialized = True

    def __repr__(self):
        return f'{self.ctype!r}({self.val!r})'

    def __bool__(self):
        return self.val != self.ctype.null_val

    @property
    def adr(self):
        ptr = self.ctype.ptr
        return ptr(ptr.ctypes_type(self.ctypes_obj), _depends_on_=self)

    @property
    def sizeof(self):
        return self.ctype.sizeof

    def _cast_from(self, cproxy):
        self.val = cproxy.val

    @property
    def val(self):
        raise NotImplementedError('this is an abstract base class')

    @val.setter
    def val(self, pyobj):
        if isinstance(pyobj, CProxy):
            self.val = pyobj.val
        else:
            try:
                self.mem = pyobj
            except TypeError:
                raise ValueError(f'{pyobj!r} cannot be converted to {self!r}')

    def __eq__(self, other):
        if isinstance(other, CProxy):
            return self.val == other.val
        else:
            return self.val == other

    def __ne__(self, other):
        return not self == other

    def __gt__(self, other):
        if isinstance(other, CProxy):
            return self.ctype == self.ctype and self.val > other.val
        else:
            return self.val > other

    def __lt__(self, other):
        if isinstance(other, CProxy):
            return self.ctype == self.ctype and self.val < other.val
        else:
            return self.val < other

    def __ge__(self, other):
        if isinstance(other, CProxy):
            return self.ctype == self.ctype and self.val >= other.val
        else:
            return self.val >= other

    def __le__(self, other):
        if isinstance(other, CProxy):
            return self.ctype == self.ctype and self.val <= other.val
        else:
            return self.val <= other

    def __add__(self, other):
        return self.ctype(self.val + int(other))

    def __sub__(self, other):
        return self.ctype(self.val - int(other))

    def __radd__(self, other):
        return self.ctype(int(other) + self.val)

    def __rsub__(self, other):
        return self.ctype(int(other) - self.val)

    def __iadd__(self, other):
        self.val += int(other)
        return self

    def __isub__(self, other):
        self.val -= int(other)
        return self

    def copy(self):
        return self.ctype(self.val)

    @property
    def mem(self):
        readonly = self.ctype.has_attr('const')
        return CMemory(ct.addressof(self.ctypes_obj), None, readonly)

    @mem.setter
    def mem(self, new_val):
        if self.ctype.has_attr('const'):
            raise WriteProtectError()
        ptr = ct.cast(ct.pointer(self.ctypes_obj), ct.POINTER(ct.c_ubyte))
        for ndx in range(len(new_val)):
            ptr[ndx] = new_val[ndx]


