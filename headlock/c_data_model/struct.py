import collections
from .core import CProxyType, CProxy, InvalidAddressSpaceError
from ..address_space import AddressSpace
from typing import List, Tuple, Union, Dict
from collections.abc import Sequence


MembersDefinition = Union[Dict[str, CProxyType], List[Tuple[str,CProxyType]]]


class CStructType(Sequence, CProxyType):

    __NEXT_ANONYMOUS_ID__ = 1

    _members_:Dict[str, CProxyType] = {}
    _members_order_:List[str] = []

    def __init__(self, struct_name:str,
                 members:MembersDefinition=None,
                 packing:int=None, addrspace:AddressSpace=None):
        super().__init__(-1, addrspace)
        if not struct_name:
            struct_name = f'__anonymous_{CStructType.__NEXT_ANONYMOUS_ID__}__'
            CStructType.__NEXT_ANONYMOUS_ID__ += 1
        self._packing_ = packing or 4
        self.struct_name = struct_name
        self._members_ = None
        self._members_order_ = None
        if members is not None:
            self.delayed_def(members)

    def __getitem__(self, item:Union[str,int]):
        if self._members_ is None:
            raise IndexError('Struct not defined yet')
        if isinstance(item, str):
            member_name = item
        else:
            member_name = self._members_order_[item]
        sub_ctype = self._members_[member_name]
        if self.__addrspace__ is None:
            return sub_ctype
        else:
            return sub_ctype.bind(self.__addrspace__)

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as e:
            raise AttributeError(f'struct has no attribute named {item!r}')

    def delayed_def(self, member_types:MembersDefinition):
        if isinstance(member_types, dict):
            member_types = member_types.items()
        if any(m.__addrspace__ is not self.__addrspace__
               for nm, m in member_types):
            raise InvalidAddressSpaceError('members must have same address '
                                           'space then struct')
        self._members_ = dict(member_types)
        self._members_order_ = [nm for nm, tp in member_types]
        next_offset = 0
        self.offsetof = {}
        for member_name, member in member_types:
            alignment = min(member.alignment, self._packing_)
            next_offset += (-next_offset % alignment)
            self.offsetof[member_name] = next_offset
            next_offset += member.sizeof
        self.sizeof = next_offset + (-next_offset % self._packing_)

    def __call__(self, *args, **argv):
        argv.update(zip(self._members_order_, args))
        return super().__call__(argv)

    def __len__(self):
        return len(self._members_) if self._members_ else 0

    @property
    def null_val(cls):
        return {name: ctype.null_val
                for name, ctype in cls._members_.items()}

    def shallow_eq(self, other):
        return super().shallow_eq(other) \
               and self._packing_ == other._packing_ \
               and self._members_order_ == other._members_order_

    def __hash__(self):
        return sum(map(hash, self),
                   hash(self.c_definition_full()) + self._packing_)

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
                                 self._members_[mname].c_definition(mname)+';')
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
                + ''.join(a+'_' for a in sorted(self.__c_attribs__))
                + self.struct_name.replace(' ', '_'))

    @property
    def alignment(self):
        if self._members_:
            return min(self._packing_,
                       max(m.alignment for m in self._members_.values()))
        else:
            return self._packing_

    def convert_to_c_repr(self, py_val):
        try:
            return super().convert_to_c_repr(py_val)
        except NotImplementedError:
            if not isinstance(py_val, collections.abc.Mapping):
                if isinstance(py_val, collections.abc.Iterable):
                    py_val = dict(zip(self._members_order_, py_val))
                else:
                    raise
            unknown_member_names = set(py_val) - set(self._members_)
            if unknown_member_names:
                raise ValueError('unknown struct members ' +
                                 ', '.join(unknown_member_names))
            result = b''
            for member_name in self._members_order_:
                member = self._members_[member_name]
                try:
                    val = py_val[member_name]
                except KeyError:
                    val = member.null_val
                result += b'\x00' * (self.offsetof[member_name] - len(result)) \
                          + member.convert_to_c_repr(val)
            return result

    def convert_from_c_repr(self, c_repr):
        return {mname: m.convert_from_c_repr(c_repr[
                         self.offsetof[mname]:self.offsetof[mname] + m.sizeof])
                for mname, m in self._members_.items()}


class CStruct(CProxy):

    def __repr__(self):
        params = (name + '=' + repr(cproxy.val)
                  for name, cproxy in zip(self.ctype._members_order_, self))
        return repr(self.ctype) + '(' + ', '.join(params) + ')'

    def __getitem__(self, item):
        if isinstance(item, str):
            member_name = item
        else:
            member_name = self.ctype._members_order_[item]
        member_ctype = self.ctype[member_name]
        offset = self.ctype.offsetof[member_name]
        return member_ctype.create_cproxy_for(self.__address__ + offset)

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    @property
    def tuple(self):
        return tuple(cproxy.val for cproxy in self)

    @tuple.setter
    def tuple(self, new_tuple):
        if len(new_tuple) > len(self.ctype._members_):
            raise ValueError('too much entries in tuple')
        else:
            self.val = dict(zip(self.ctype._members_order_, new_tuple))

    @property
    def val(self):
        return {name: cproxy.val
                for name, cproxy in zip(self.ctype._members_order_, self)}

    @val.setter
    def val(self, new_val):
        if isinstance(new_val, (collections.Sequence, collections.Iterator)):
            new_val = dict(zip(self.ctype._members_order_, new_val))
        for name in self.ctype._members_order_:
            member = self[name]
            try:
                val = new_val[name]
            except KeyError:
                member.val = member.ctype.null_val
            else:
                member.val = val

    def __len__(self):
        return len(self.ctype._members_)


CStructType.CPROXY_CLASS = CStruct
