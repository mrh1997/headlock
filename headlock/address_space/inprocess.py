from platform import architecture
from typing import Dict
import ctypes as ct
import sys

from . import AddressSpace

MACHINE_WORDSIZE = 32 if architecture()[0] == '32bit' else 64
ENDIANESS = 'little'


def free_cdll(cdll):
    if sys.platform == 'win32':
        ct.windll.kernel32.FreeLibrary(cdll._handle)
    elif sys.platform == 'linux':
        libdl = ct.CDLL('libdl.so')
        libdl.dlclose(cdll._handle)
    else:
        raise NotImplementedError('the platform is not supported yet')

ptr_t = ct.c_uint32 if ct.sizeof(ct.CFUNCTYPE(None)) == 4 else ct.c_uint64

class InprocessAddressSpace(AddressSpace):
    """
    This address space implementation represents the process of the
    current python interpreter and uses ctypes for accessing it.
    """

    def __init__(self, cdll_name:str,
                 py2c_bridge_ndxs:Dict[str, int]=None,
                 c2py_bridge_ndxs:Dict[str, int]=None,
                 max_c2py_instances:int=1):
        super().__init__()
        self.cdll = ct.CDLL(cdll_name)
        try:
            bridge_t = ct.c_uint32 if ct.sizeof(ct.CFUNCTYPE(None)) == 4 \
                else ct.c_uint64
            bridge_array_t = bridge_t *max_c2py_instances *len(c2py_bridge_ndxs)
            self.__bridge_array = bridge_array_t.in_dll(
                self.cdll, '_c2py_bridge_')

            self.cdll._py2c_bridge_.argtypes = [ct.c_int, ptr_t, ptr_t, ptr_t]
            self.py2c_bridge_ndxs = py2c_bridge_ndxs or {}

            c2py_pyfuncs = self.__c2py_pyfuncs = {}
            bridge_handler_t = ct.CFUNCTYPE(None,
                                            ct.c_int, ct.c_int, ptr_t, ptr_t)
            def my_bridge_handler(sig_id, instance_ndx, param_adr, retval_adr):
                func = c2py_pyfuncs[sig_id, instance_ndx]
                func(param_adr, retval_adr)
            self.__my_bridge_handler = bridge_handler_t(my_bridge_handler)
            bridge_handler = ptr_t.in_dll(self.cdll, '_c2py_bridge_handler')
            bridge_handler.value = ct.cast(
                ct.pointer(self.__my_bridge_handler),
                ct.POINTER(ptr_t)).contents.value
            self.c2py_bridge_ndxs = c2py_bridge_ndxs or {}
            self.__max_c2py_instances = max_c2py_instances

            self.__mempool = {}
            self.__symbol_map = {}
        except:
            free_cdll(self.cdll)
            raise

    def read_memory(self, address, length):
        return ct.string_at(address, length)

    def write_memory(self, address, data):
        ct.memmove(address, ct.create_string_buffer(data), len(data))

    def alloc_memory(self, length:int) -> int:
        memblock = ct.create_string_buffer(length)
        address = ct.addressof(memblock)
        self.__mempool[address] = memblock
        return address

    def get_symbol_adr(self, symbol_name):
        try:
            cdll_obj = ct.c_byte.in_dll(self.cdll, symbol_name)
        except ValueError:
            try:
                cdll_obj = getattr(self.cdll, symbol_name)
            except AttributeError:
                raise ValueError(
                    f'There is no C Function/Variable named {symbol_name!r}')
        adr = ct.addressof(cdll_obj)
        self.__symbol_map[adr] = symbol_name
        return adr

    def get_symbol_name(self, adr:int) -> str:
        try:
            return self.__symbol_map[adr]
        except KeyError:
            raise ValueError('no known symbol at address')

    def invoke_c_code(self, func_adr:int, sig_id:str,
                      args_adr:int, retval_adr:int):
        try:
            bridge_ndx = self.py2c_bridge_ndxs[sig_id]
        except (AttributeError, KeyError):
            raise ValueError(f'No Bridge for signature {sig_id!r} found')
        else:
            if not self.cdll._py2c_bridge_(bridge_ndx, func_adr,
                                           args_adr, retval_adr):
                raise ValueError('Internal Error '
                                 '(bridge index map does not match binary)')

    def create_c_code(self, sig_id, pyfunc):
        try:
            bridge_ndx = self.c2py_bridge_ndxs[sig_id]
        except KeyError:
            raise ValueError(f'No Bridge for signature {sig_id!r} found')
        else:
            inst_ndx = 1 + max([indx for bndx, indx in self.__c2py_pyfuncs
                                if bndx == bridge_ndx],
                               default=-1)
            if inst_ndx == self.__max_c2py_instances:
                raise ValueError(f'Created too much C-to-Python Bridges for '
                                 f'Signature {sig_id!r}')
            self.__c2py_pyfuncs[bridge_ndx, inst_ndx] = pyfunc
            return self.__bridge_array[bridge_ndx][inst_ndx]


    def close(self):
        free_cdll(self.cdll)
