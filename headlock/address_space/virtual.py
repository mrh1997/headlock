from . import AddressSpace
from collections import namedtuple


class VirtualAddressSpace(AddressSpace):
    """
    This is a dummy address space implementation. Maps all memory operations
    to the python bytearray .content.
    Its main purpose is for testing.

    ATTENTION: For simplicity this implementation does not actually
               release memory blocks but only append new onces at the end.
    """

    def __init__(self, content=b''):
        super().__init__()
        self.content = bytearray(content)

    def read_memory(self, address, length):
        assert address >= 0 and length > 0
        assert address + length <= len(self.content)
        return bytes(self.content[address:address+length])

    def write_memory(self, address, data):
        data = bytes(data)
        assert address >= 0
        assert address + len(data) <= len(self.content)
        self.content[address:address+len(data)] = data

    def alloc_memory(self, length:int):
        address = len(self.content)
        self.content += b'\0'*length
        return address

    def get_symbol_adr(self, symbol_name):
        return 0

    def _get_symbol_name(self, adr):
        raise ValueError()