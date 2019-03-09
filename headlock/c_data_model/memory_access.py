import functools
import itertools
from typing import Union
from collections.abc import ByteString

from ..address_space import AddressSpace


class WriteProtectError(Exception):
    """
    This exception is raised, if a const memory object shall be modified
    """


@functools.total_ordering
class CMemory:
    """
    This class provides a pythonic interface to C memory blocks.
    This includes array like access, iterating, comparing, ...

    CMemory block has a start address and optionally (!) a specified size.
    All access operations must be within this range. Furthermore CMemory
    may be declared as readonly, in which case modfications of the underlying
    memory are not allowed at all.

    Internally every CMemory object is backed by a (pluggable)
    AddressSpace object, which is reponsible for the actual memory access.
    """

    def __init__(self, addrspace:AddressSpace, addr:int, max_addr:int=None,
                 readonly=False):
        super().__init__()
        self.addrspace = addrspace
        self.address = addr
        self.max_address = max_addr
        self.readonly = readonly

    def __check_slice(self, ndx):
        if ndx.stop is None:
            raise IndexError(f'End of slice has to be defined ({ndx})')
        if (ndx.start or 0) < 0 or ndx.stop < 0 or (ndx.step or 1) < 0:
            raise IndexError(f'Negative values are not supported in '
                             f'slices ({ndx})')
        if self.max_address is not None \
                and self.address + ndx.stop > self.max_address:
            raise IndexError(f'End of slice ({ndx.stop}) exceeds size of '
                             f'memory block ({self.max_address-self.address})')

    def __ndx_to_slice(self, ndx):
        return slice(ndx, ndx+1, None)

    def __getitem__(self, ndx:Union[int, slice]):
        if isinstance(ndx, slice):
            self.__check_slice(ndx)
            start = ndx.start or 0
            if ndx.step is None or ndx.step == 1:
                return self.addrspace.read_memory(self.address + start,
                                                  ndx.stop - start)
            else:
                return b''.join(
                    self.addrspace.read_memory(self.address + ndx, 1)
                    for ndx in range(start, ndx.stop, ndx.step))
        else:
            self.__check_slice(self.__ndx_to_slice(ndx))
            return self.addrspace.read_memory(self.address + ndx, 1)[0]

    def __setitem__(self, ndx:Union[int, slice], value:Union[int, ByteString]):
        if self.readonly:
            raise WriteProtectError()
        if isinstance(ndx, slice):
            self.__check_slice(ndx)
            start = ndx.start or 0
            step = ndx.step or 1
            if (ndx.stop - start + step - 1) // step != len(value):
                raise ValueError('length of value to write must match length '
                                 'of given slice')
            if ndx.step is None:
                return self.addrspace.write_memory(self.address + start, value)
            else:
                for rel_ndx, val in enumerate(value):
                    self.addrspace.write_memory(
                        self.address + start + rel_ndx * ndx.step, bytes([val]))
        else:
            self.__check_slice(self.__ndx_to_slice(ndx))
            self.addrspace.write_memory(self.address + ndx, bytes([value]))

    def __iter__(self):
        return map(self.__getitem__, itertools.count(0))

    def __repr__(self):
        result = f"{type(self).__name__}({hex(self.address)}"
        if self.max_size is not None:
            result += f', {self.max_size}'
        if self.readonly:
            result += f', readonly=True'
        return result + ')'

    def __eq__(self, other:'CMemory'):
        try:
            other_as_bytes = bytes(other)
            other_len = len(other)
        except TypeError:
            return False
        else:
            return self[:other_len] == other_as_bytes

    def __gt__(self, other:'CMemory'):
        return self[:len(other)] > bytes(other)
