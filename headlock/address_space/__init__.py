"""
This is for headlock internal use only!
"""
from typing import Dict, Tuple
import abc
from collections.abc import ByteString


class MemoryManagementError(Exception):
    """
    This exception occurs, when if memory allocation/release failed.
    """


class AddressSpace:
    """
    An address space provides an interface to running C code at ABI (not API!)
    layer.

    This class is only the abstract base class. Descendants have to implement
    the communication between this python process/machine and some spefic
    kind of "running code" (i.e. an OS user process, an OS kernel or an
    embedded system running on a remote machine).

    This class is not responsible to instanciate C code or stop it!
    The the code has to be loaded somewhere else and a handle/ID has to be
    passed to the constructor of the subclass.
    """

    def __int__(self):
        self.__mempool__ = {}

    def _register_memory_block(self, address, len):
        pass

    @abc.abstractmethod
    def find_memory_block(self, address:int) -> Tuple[int, int]:
        """
        returns the start address and the length of the memory block which
        contains this address. raises ValueError if no containing memory block
        exists
        """

    @abc.abstractmethod
    def read_memory(self, address:int, length:int) -> bytes:
        """
        Reads a specific amount of Memory (in bytes) of the address space.
        The caller has to ensure that the specified memory range is valid,
        otherwise the connected process could crash
        """

    @abc.abstractmethod
    def write_memory(self, address:int, data:ByteString):
        """
        Writes a specific amount of Memory (in bytes) to the address space.
        The caller has to ensure that the specified memory range is valid,
        otherwise the connected process could crash
        """

    @abc.abstractmethod
    def alloc_memory(self, length:int) -> int:
        """
        Allocated length bytes of contiguous memory and returns a reference to
        it.
        """

    @abc.abstractmethod
    def get_symbol_adr(self, symbol_name:str) -> int:
        """
        returns the address of a specific symbol.
        Symbol may be a global variable or a function.
        """

    @abc.abstractmethod
    def get_symbol_name(self, adr:int) -> str:
        """
        returns the name of a symbol or raises ValueError is adr does not
        refer to a valid C symbol
        """

    @abc.abstractmethod
    def invoke_c_code(self, func_adr:int, sig_id:str,
                      args_adr:int, retval_adr:int) -> bytes:
        """
        invokes a piece of C code via the bridge for signature of name
        "sig_id".
        """
