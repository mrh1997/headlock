from platform import architecture
from typing import Callable, List, Set
import ctypes as ct
import sys
from threading import local
from collections import defaultdict

from . import AddressSpace

MACHINE_WORDSIZE = 32 if architecture()[0] == '32bit' else 64
ENDIANESS = 'little'


def free_cdll(cdll):
    if sys.platform == 'win32':
        ct.windll.kernel32.FreeLibrary.argtypes = [ct.wintypes.HMODULE]
        ct.windll.kernel32.FreeLibrary(cdll._handle)
    elif sys.platform == 'linux':
        libdl = ct.CDLL('libdl.so')
        libdl.dlclose(cdll._handle)
    else:
        raise NotImplementedError('the platform is not supported yet')


fptr_t = ct.c_uint32 if ct.sizeof(ct.CFUNCTYPE(None)) == 4 else ct.c_uint64


class InprocessAddressSpace(AddressSpace):
    """
    This address space implementation represents the process of the
    current python interpreter and uses ctypes for accessing it.
    """

    class CallStacks(local):
        """
        As every thread has its own callstack, the callstacks are managed
        as thread local storage object.
        """
        def __init__(self):
            self.exc = None
            self.jump_dests = []

    ### 'mock_bridge_names' should be removed in future and 'mock_bridge'
    ### should get an index instead of a name as first param. This index has
    ### to start at a fix offset (not at funcptrsigs * max_c2py_instances!).
    ### furthermore py2c_bridge_ndxs and c2py_bridge_ndxs shall be fused to a
    ### singleList[str] and renamed to bridge_sigs and c2py_bridge_sigs (Set[str]).
    ### max_c2py_instances shall be renamed to c2py_bridges_per_sig
    def __init__(self, cdll_name:str,
                 bridge_sigs:List[str]=None,
                 c2py_bridge_sig_ids:Set[int]=None,
                 c2py_bridges_per_sig:int=1,
                 mock_pyfunc:Callable[[int, int, int], None]=None):
        super().__init__()
        self.__callstacks = self.CallStacks()
        self.__mempool = {}
        self.__symbol_map = {}
        self.cdll = ct.CDLL(cdll_name)
        try:
            c2py_bridge_sig_cnt = (1 + max(c2py_bridge_sig_ids, default=0))
            bridges_t = ct.POINTER(fptr_t) * c2py_bridge_sig_cnt
            self.__c2py_bridges = bridges_t.in_dll(self.cdll, '_c2py_bridges')
            self.cdll._py2c_bridge_.argtypes = [ct.c_int, fptr_t, ct.c_void_p,
                                                ct.c_void_p, ct.c_void_p]

            self.__bridge_sigs = bridge_sigs or []
            self.__bridge_sig_map = {
                c_sig: sig_id for sig_id,c_sig in enumerate(self.__bridge_sigs)}

            self.__c2py_bridge_sig_ids = c2py_bridge_sig_ids or set()
            self.__c2py_bridges_per_sig = c2py_bridges_per_sig
            self.__c2py_bridge_insts = defaultdict(int)
            self.__c2py_pyfuncs = {}

            self.__c2py_bridge_handler = self.create_c2py_bridge_handler(
                self.__c2py_pyfuncs, mock_pyfunc, self.__callstacks)
            c2py_bridge_handler_ptr = fptr_t.in_dll(self.cdll,
                                                    '_c2py_bridge_handler')
            c2py_bridge_handler_ptr.value = ct.cast(
                ct.pointer(self.__c2py_bridge_handler),
                ct.POINTER(fptr_t)).contents.value
        except:
            free_cdll(self.cdll)
            raise

    @staticmethod
    def create_c2py_bridge_handler(c2py_pyfuncs, mock_pyfunc, callstacks):
        @ct.CFUNCTYPE(ct.c_void_p, ct.c_int, ct.c_int, ct.c_void_p, ct.c_void_p)
        def c2py_bridge_handler(sig_id, inst_ndx, param_adr, retval_adr):
            try:
                if inst_ndx < 0:
                    mock_pyfunc(-inst_ndx-1, param_adr, retval_adr)
                else:
                    c2py_pyfuncs[sig_id, inst_ndx](param_adr, retval_adr)
            except Exception:
                if len(callstacks.jump_dests) == 0:
                    # Special case if this callback was called from a C
                    # function that was NOT called via invoke_c_func().
                    return None
                callstacks.exc = sys.exc_info()
                # This is a workaround, as "return callstacks.jump_dests[-1]"
                # does not work for some reason
                jump_dest_p = ct.pointer(callstacks.jump_dests[-1])
                return ct.cast(jump_dest_p, ct.POINTER(fptr_t)).contents.value
            else:
                return None
        return c2py_bridge_handler

    def read_memory(self, address, length):
        return ct.string_at(address, length)

    def write_memory(self, address, data):
        if isinstance(data, bytearray):
            data = bytes(data)
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

    def invoke_c_func(self, func_adr:int, c_sig:str,
                      args_adr:int, retval_adr:int):
        try:
            sig_id = self.__bridge_sig_map[c_sig]
        except (AttributeError, KeyError):
            raise ValueError(f'No Bridge for signature {c_sig!r} found')
        else:
            jump_dest = ct.c_void_p()
            self.__callstacks.jump_dests.append(jump_dest)
            status = self.cdll._py2c_bridge_(sig_id,
                                             func_adr,
                                             args_adr,
                                             retval_adr,
                                             ct.byref(jump_dest))
            self.__callstacks.jump_dests.pop()
            if status == 0:
                raise ValueError('Internal Error '
                                 '(bridge index map does not match binary)')
            elif status == 2:
                exc = self.__callstacks.exc
                assert exc is not None
                self.__callstacks.exc = None
                raise exc[0](exc[1]).with_traceback(exc[2])

    def create_c_callback(self, c_sig, pyfunc):
        try:
            sig_id = self.__bridge_sig_map[c_sig]
        except KeyError:
            raise ValueError(f'No Bridge for signature {c_sig!r} found')
        else:
            inst_ndx = self.__c2py_bridge_insts[sig_id]
            if inst_ndx == self.__c2py_bridges_per_sig:
                raise ValueError(
                    f"Created too much C-to-Python Bridges for "
                    f"Signature {c_sig!r}. Increase TestSetup's "
                    f"C2PY_BRIDGES_PER_SIG (current value is "
                    f"{self.__c2py_bridges_per_sig})")
            self.__c2py_bridge_insts[sig_id] = inst_ndx + 1
            self.__c2py_pyfuncs[sig_id, inst_ndx] = pyfunc
            return self.__c2py_bridges[sig_id][inst_ndx]


    def close(self):
        free_cdll(self.cdll)
