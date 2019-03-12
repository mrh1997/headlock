import sys
from .core import CProxyType, CProxy, InvalidAddressSpaceError
from .void import CVoidType
from ..address_space import AddressSpace
from typing import Union


last_tunnelled_exception = None


class CFuncType(CProxyType):

    PRECEDENCE = 20

    def __init__(self, returns:CProxyType=None, args:list=None,
                 addrspace:AddressSpace=None):
        self.returns = returns
        self.args = args or []
        if returns is not None and addrspace is not self.returns.__addrspace__:
            raise InvalidAddressSpaceError(
                'Return type of function has different addressspace than '
                'function type')
        if any(addrspace is not a.__addrspace__ for a in self.args):
            raise InvalidAddressSpaceError(
                'A argument type of function has different addressspace than '
                'function type')
        self.language = "C"
        super().__init__(None, addrspace)

    def bind(self, addrspace:AddressSpace):
        bound_ctype = super().bind(addrspace)
        if bound_ctype.returns is not None:
            bound_ctype.returns = bound_ctype.returns.bind(addrspace)
        bound_ctype.args = [a.bind(addrspace) for a in bound_ctype.args]
        return bound_ctype

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
    def ptr(self):
        raise NotImplementedError()

    @property
    def null_val(cls):
        raise TypeError('Function objects do not support null vals')

    def _decorate_c_definition(self, c_def):
        if self.has_attr('cdecl'):
            return '__cdecl ' + super()._decorate_c_definition(c_def)
        else:
            return super()._decorate_c_definition(c_def)

    def c_definition(self, refering_def='f'):
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
                                 for attr in sorted(self.__c_attribs__))
        return f'CFuncType({self.returns!r}, [{arg_repr_str}]){attr_calls_str}'

    @staticmethod
    def wrapped_pyfunc(pyfunc, name, arg_types, return_type, addrspace):
        logger = None
        def wrapper(params_adr, retval_adr):
            global last_tunnelled_exception
            if last_tunnelled_exception is not None:
                if logger:
                    logger.write('<call ' + name +
                                 'failed due to preceeding exception>')
                return None if return_type is None else return_type.null_val
            next_param_adr = params_adr
            params = []
            for arg_type in arg_types:
                params.append(arg_type.create_cproxy_for(next_param_adr))
                next_param_adr += arg_type.sizeof
            try:
                if logger:
                    logger.write('    ' + (name or '<unknown>'))
                    logger.write('('+(', '.join(map(repr, params)))+')')
                retval = pyfunc(*params)
                if return_type is not None:
                    passed_retval = return_type.create_cproxy_for(retval_adr)
                    passed_retval.val = retval
                    if logger:
                        logger.write('->' + repr(retval) + '\n')
                else:
                    if logger:
                        logger.write('\n')
            except Exception:
                last_tunnelled_exception = sys.exc_info()
                if logger:
                    logger.write('!>'+repr(last_tunnelled_exception[1])+'\n')
                if return_type is not None:
                    passed_retval = return_type.create_cproxy_for(retval_adr)
                    passed_retval.val = return_type.null_val
        return wrapper

    def __call__(self, init_val:Union[str, callable, int]) -> 'CFunc':
        if self.__addrspace__ is None:
            raise InvalidAddressSpaceError(
                'CFuncType is not bound to AddressSpace yet and thus cannot '
                'be instantiated')
        if isinstance(init_val, str):
            adr = self.__addrspace__.get_symbol_adr(init_val)
        elif isinstance(init_val, CFunc):
            adr = init_val.__address__
        elif callable(init_val):
            name = init_val.__name__ if hasattr(init_val, '__name__') \
                   else 'py-callable'
            wrapped_func = self.wrapped_pyfunc(init_val, name,
                                               self.args, self.returns,
                                               self.__addrspace__)
            adr = self.__addrspace__.create_c_code(self.sig_id, wrapped_func)
        else:
            adr = init_val
        return self.create_cproxy_for(adr)

    @property
    def sig_id(self) -> str:
        """
        returns unique identification string for this function signature
        """
        return self.c_definition()


class CFunc(CProxy):

    @property
    def val(self):
        return self.__address__

    @property
    def name(self):
        addrspace = self.ctype.__addrspace__
        try:
            pyfunc, bridge_obj = addrspace.bridgepool[self.__address__]
            return pyfunc.__name__
        except KeyError:
            try:
                return addrspace.get_symbol_name(self.__address__)
            except ValueError:
                return None

    def __call__(self, *args):
        global last_tunnelled_exception
        if len(args) != len(self.ctype.args):
            raise TypeError(f'{self.name}() requires {len(self.ctype.args)} '
                            f'parameters, but got {len(args)}')
        addrspace = self.ctype.__addrspace__
        return_ctype = self.ctype.returns
        params_bytes = b''.join(carg_type.convert_to_c_repr(arg)
                          for carg_type, arg in zip(self.ctype.args, args))
        params_bufadr = addrspace.alloc_memory(len(params_bytes))
        addrspace.write_memory(params_bufadr, params_bytes)
        if return_ctype is None:
            retval = None
            retval_address = 0
        else:
            retval = return_ctype()
            retval_address = retval.__address__
        addrspace.invoke_c_code(self.__address__, self.ctype.sig_id,
                                params_bufadr, retval_address)
        if last_tunnelled_exception is not None:
            exc = last_tunnelled_exception
            last_tunnelled_exception = None
            raise exc[0](exc[1]).with_traceback(exc[2])
        else:
            return retval

    def __repr__(self):
        return f"<CFunc of {self.name or '???'!r}>"

CFuncType.CPROXY_CLASS = CFunc
