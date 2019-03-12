import copy
from ..address_space import AddressSpace
from .memory_access import CMemory, WriteProtectError
from typing import Any, Iterable


class InvalidAddressSpaceError(Exception):
    """
    This error is raised, when instantiating a type, that is not yet bound to
    an address space (see CProxyType.bind() )
    """


class CProxyType:

    CPROXY_CLASS:type = None

    PRECEDENCE = 0

    def __init__(self, size:int, addrspace:AddressSpace=None):
        self.__c_attribs__ = frozenset()
        self.__addrspace__ = addrspace
        self.sizeof = size

    def bind(self, addrspace:AddressSpace):
        if addrspace is self.__addrspace__:
            return self
        elif self.__addrspace__ is not None:
            raise ValueError('Must not bind an AddressSpace to an already '
                             'bound CProxyType')
        bound_obj = copy.copy(self)
        bound_obj.__addrspace__ = addrspace
        return bound_obj

    def __get__(self, instance, owner):
        if instance is None:
            return self
        else:
            return self.bind(instance.__addrspace__)

    def convert_to_c_repr(self, py_val:Any) -> bytes:
        """
        This method converts a python object to a bytes object that matches
        the C representation of the python object.
        It is the inverse function of convert_from_c_repr().
        """
        if py_val is None:
            return self.convert_to_c_repr(self.null_val)
        elif isinstance(py_val, CProxy):
            return self.convert_to_c_repr(py_val.val)
        else:
            raise NotImplementedError()

    def convert_from_c_repr(self, c_repr:bytes):
        """
        This method interprets a bytes object as a C representation of this
        c-type and returns the corresponding python object.
        """
        raise NotImplementedError()

    def __call__(self, init_val:Any=None) -> 'CProxy':
        if self.__addrspace__ is None:
            raise InvalidAddressSpaceError(
                'CProxyType is not bound to AddressSpace yet and thus cannot '
                'be instantiated')
        address = self.__addrspace__.alloc_memory(self.sizeof)
        init_c_repr = self.convert_to_c_repr(init_val)
        self.__addrspace__.write_memory(address, init_c_repr)
        return self.create_cproxy_for(address)

    def __bool__(self):
        return True

    def __eq__(self, other:'CProxyType') -> bool:
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

    def shallow_eq(self, other:'CProxyType') -> bool:
        return self.__c_attribs__ == other.__c_attribs__ \
               and self.sizeof == other.sizeof \
               and self.__addrspace__ == other.__addrspace__

    def __hash__(self):
        return sum(map(hash, self), hash(self.c_definition()))

    def __iter__(self):
        return self.shallow_iter_subtypes()

    @property
    def ptr(self):
        raise NotImplementedError()

    def array(self, element_count):
        raise NotImplementedError()

    def alloc_array(self, initval:Iterable) -> 'CProxy':
        raise NotImplementedError()

    def alloc_ptr(self, initval:Iterable) -> 'CProxy':
        raise NotImplementedError()

    @property
    def null_val(self):
        raise NotImplementedError('this is an abstract base class')

    def c_definition(self, refering_def=''):
        raise NotImplementedError('this is an abstract base class')

    def _decorate_c_definition(self, c_def):
        return ''.join(attr + ' ' for attr in sorted(self.__c_attribs__)) + c_def

    def with_attr(self, attr_name):
        if attr_name in self.__c_attribs__:
            raise ValueError(f'attribute {attr_name} is already set')
        derived = copy.copy(self)
        derived.__c_attribs__ = self.__c_attribs__ | {attr_name}
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

    def ident(self) -> int:
        return id(self)

    def shallow_iter_subtypes(self) -> Iterable:
        return iter([])

    def has_attr(self, attr_name) -> bool:
        return attr_name in self.__c_attribs__

    @property
    def alignment(self) -> int:
        raise NotImplementedError()

    def create_cproxy_for(self, adr):
        return self.CPROXY_CLASS(self, adr)


class CProxy:

    def __init__(self, ctype:CProxyType, address:int):
        super(CProxy, self).__init__()
        self.ctype =  ctype
        self.__address__ = address

    def __repr__(self):
        return f'{self.ctype!r}({self.val!r})'

    def __bool__(self):
        return self.val != self.ctype.null_val

    @property
    def adr(self):
        cptr_type = self.ctype.ptr
        return cptr_type(self.__address__)

    @property
    def sizeof(self):
        return self.ctype.sizeof

    @property
    def val(self):
        ctype = self.ctype
        c_repr = ctype.__addrspace__.read_memory(self.__address__, self.sizeof)
        return ctype.convert_from_c_repr(c_repr)

    @val.setter
    def val(self, py_val):
        if self.ctype.has_attr('const'):
            raise WriteProtectError('must not change const variable')
        c_repr = self.ctype.convert_to_c_repr(py_val)
        self.ctype.__addrspace__.write_memory(self.__address__, c_repr)

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
        if isinstance(other, CProxy):
            other = other.val
        return self.ctype(self.val + other)

    def __sub__(self, other):
        if isinstance(other, CProxy):
            other = other.val
        return self.ctype(self.val - other)

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
        addrspace = self.ctype.__addrspace__
        new_block = addrspace.alloc_memory(self.sizeof)
        rawdata = addrspace.read_memory(self.__address__, self.sizeof)
        addrspace.write_memory(new_block, rawdata)
        return type(self)(self.ctype, new_block)

    @property
    def mem(self):
        readonly = self.ctype.has_attr('const')
        return CMemory(
            self.ctype.__addrspace__, self.__address__, None, readonly)

    @mem.setter
    def mem(self, new_val):
        mem = self.mem
        new_val = bytes(new_val)
        mem[:len(new_val)] = new_val
