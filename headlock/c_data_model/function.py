import sys
import ctypes as ct
from .core import CProxyType, CProxy, issubclass_ctypes_ptr, isinstance_ctypes
from .void import CVoidType


last_tunnelled_exception = None

class CFuncType(CProxyType):

    PRECEDENCE = 20

    def __init__(self, returns:CProxyType=None, args:list=None):
        self.returns = returns
        self.args = args or []
        self.language = "C"
        if returns is None:
            self.ctypes_returns = None
        elif issubclass_ctypes_ptr(returns.ctypes_type):
            self.ctypes_returns = ct.c_void_p
        else:
            self.ctypes_returns = returns.ctypes_type
        self.ctypes_args = tuple(ctype.ctypes_type
                                 for ctype in self.args)
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
        raise NotImplementedError()

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
        return self.CPROXY_CLASS(self, init_obj, _depends_on_, logger=logger)


class CFunc(CProxy):

    def __init__(self, ctype:CFuncType, init_obj=None, name:str=None,
                 logger=None, _depends_on_:CProxy=None):
        ctype:CFuncType
        if not callable(init_obj):
            raise ValueError('expect callable as first parameter')
        self.name = name or (init_obj.__name__
                             if hasattr(init_obj, '__name__') else None)
        if isinstance_ctypes(init_obj):
            self.language = 'C'
            self.pyfunc = None
        elif isinstance(init_obj, CProxy):
            pass
        else:
            self.language = 'PYTHON'
            self.pyfunc = init_obj
            init_obj = ctype.ctypes_type(self.wrapped_pyfunc(
                init_obj,
                self.name,
                ctype.args,
                ctype.returns,
                logger))
        self.logger = logger
        super(CFunc, self).__init__(ctype, init_obj, _depends_on_)

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
        if len(args) != len(self.ctype.args):
            raise TypeError(f'{self.name}() requires {len(self.ctype.args)} '
                            f'parameters, but got {len(args)}')
        args = [arg_cls(arg) for arg_cls, arg in zip(self.ctype.args, args)]
        if self.logger:
            self.logger.write(self.name or '???')
            self.logger.write('(' + ', '.join(map(repr, args)) + ')\n')
        self.ctypes_obj.argtypes = self.ctype.ctypes_args
        self.ctypes_obj.restype = self.ctype.ctypes_returns
        result = self.ctypes_obj(*[a.ctypes_obj for a in args])
        if last_tunnelled_exception is not None:
            exc = last_tunnelled_exception
            last_tunnelled_exception = None
            raise exc[0](exc[1]).with_traceback(exc[2])
        elif self.ctype.returns is None:
            return None
        else:
            result = self.ctype.returns(result)
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
        ptr_size_int = ct.c_uint64 if ct.sizeof(ct.c_void_p)==8 else ct.c_uint32
        ctypes_ptr = ct.cast(ct.pointer(self.ctypes_obj),
                             ct.POINTER(ptr_size_int))
        return self.ctype.ptr(ctypes_ptr.contents.value, _depends_on_=self)

CFuncType.CPROXY_CLASS = CFunc
