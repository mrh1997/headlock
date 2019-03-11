from platform import architecture
from typing import List
import ctypes as ct

from . import AddressSpace, MemoryManagementError

MACHINE_WORDSIZE = 32 if architecture()[0] == '32bit' else 64
ENDIANESS = 'little'

class InprocessAddressSpace(AddressSpace):
    """
    This address space implementation represents the process of the
    current python interpreter and uses ctypes for accessing it.
    """

    def __init__(self, cdlls:List[ct.CDLL], py2c_bridge_ndxs=None):
        super().__init__()
        self.__cdlls = cdlls
        self.__mempool = {}
        self.bridgepool = {}
        self.__symbol_map = {}
        self.py2c_bridge_ndxs = py2c_bridge_ndxs or {}

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
        for cdll in self.__cdlls:
            try:
                cdll_obj = ct.c_byte.in_dll(cdll, symbol_name)
            except ValueError:
                try:
                    cdll_obj = getattr(cdll, symbol_name)
                except AttributeError:
                    pass
                else:
                    break
            else:
                break
        else:
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

    def invoke_c_code(self, sig_id:str, func_adr:int,
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

    @property
    def cdll(self):
        if len(self.__cdlls) != 1:
            raise ValueError('property cdll works only if AddressSpace refers '
                             'exactly one CDLL')
        return self.__cdlls[0]
