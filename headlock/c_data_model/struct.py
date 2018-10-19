import collections
import ctypes as ct
from .core import CObjType, CObj


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


