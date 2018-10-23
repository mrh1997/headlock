import functools
import ctypes as ct
import itertools


class WriteProtectError(Exception):
    """
    This exception is raised, if a const memory object shall be modified
    """


@functools.total_ordering
class CMemory:

    def __init__(self, addr, max_size=None, readonly=False):
        super().__init__()
        self.addr = addr
        self.max_size = max_size
        self.readonly = readonly

    @property
    def _ctypes_obj(self):
        ptr_size_int = ct.c_uint64 if ct.sizeof(ct.c_void_p)==8 else ct.c_uint32
        ptr = ct.POINTER(ct.c_ubyte)()
        ptr_ptr = ct.cast(ct.pointer(ptr), ct.POINTER(ptr_size_int))
        ptr_ptr.contents.value = self.addr
        return ptr

    def __check_ndx(self, ndx):
        if isinstance(ndx, slice):
            if ndx.stop is None:
                raise IndexError(f'End of slice has to be defined ({ndx})')
            if (ndx.start or 0) < 0 or ndx.stop < 0 or (ndx.step or 1) < 0:
                raise IndexError(f'Negative values are not supported in '
                                 f'slices ({ndx})')
            if self.max_size is not None and ndx.stop > self.max_size:
                raise IndexError(f'End of slice ({ndx.stop}) '
                                 f'exceeds max_size ({self.max_size})')
        else:
            if ndx < 0:
                raise IndexError(f'Negative Indices are not supported ({ndx})')
            if self.max_size is not None and ndx >= self.max_size:
                raise IndexError(f'Index ({ndx}) '
                                 f'exceeds max_size ({self.max_size})')

    def __getitem__(self, ndx):
        self.__check_ndx(ndx)
        result = self._ctypes_obj[ndx]
        if isinstance(ndx, slice):
            return bytes(result)
        else:
            return result

    def __setitem__(self, ndx, value):
        if self.readonly:
            raise WriteProtectError()
        self.__check_ndx(ndx)
        if isinstance(ndx, slice):
            ctypes_obj = self._ctypes_obj
            indeces = range(ndx.start or 0, ndx.stop, ndx.step or 1)
            for n, v in zip(indeces, value):
                ctypes_obj[n] = v
        else:
            self._ctypes_obj[ndx] = value

    def __iter__(self):
        return map(self.__getitem__, itertools.count(0))

    def __repr__(self):
        result = f"{type(self).__name__}({hex(self.addr)}"
        if self.max_size is not None:
            result += f', {self.max_size}'
        if self.readonly:
            result += f', readonly=True'
        return result + ')'

    def __eq__(self, other):
        try:
            other_as_bytes = bytes(other)
            other_len = len(other)
        except TypeError:
            return False
        else:
            return self[:other_len] == other_as_bytes

    def __gt__(self, other):
        return self[:len(other)] > bytes(other)


