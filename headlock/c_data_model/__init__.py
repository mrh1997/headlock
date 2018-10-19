import collections
import ctypes as ct
from . import void, integer, float, enum, array, pointer, struct, union, \
    vector, function, funcpointer
from .memory_access import CMemory, WriteProtectError
from .core import CObjType, CObj
from .void import CVoid
from .integer import CInt
from .float import CFloat
from .enum import CEnum
from .array import CArray
from .pointer import CPointer
from .struct import CStruct
from .union import CUnion
from .vector import CVector
from .function import CFunc
from .funcpointer import CFuncPointer


class PtrArrFactoryMixIn:
    """
    This mixin adds implementations of the convinience
    properties(methods .ptr, .array(), .alloc_array() and .alloc_ptr()
    to all types.
    """

    def __init__(self, *args, **argv):
        self._ptr = None
        super().__init__(*args, **argv)

    @property
    def ptr(self):
        # this is an optimization to avoid creating a new Pointer type
        # everytime a pointer to this type is required
        if self._ptr is None:
            self._ptr = CPointerType(self)
        return self._ptr

    def array(self, element_count):
        return CArrayType(self, element_count)

    def alloc_array(self, initval):
        if isinstance(initval, collections.abc.Iterable):
            if not isinstance(initval, collections.abc.Collection):
                initval = list(initval)
            elif isinstance(initval, str):
                initval = array.map_unicode_to_list(initval, self)
            elif isinstance(initval, collections.abc.ByteString):
                initval = initval + b'\0'
            return self.array(len(initval))(initval)
        else:
            return self.array(initval)()

    def alloc_ptr(self, initval):
        array = self.alloc_array(initval)
        return self.ptr(array.adr, _depends_on_=array)


class CVoidType(PtrArrFactoryMixIn, void.CVoidType):
    def alloc_ptr(self, initval):
        array = BuildInDefs.unsigned_char.alloc_array(initval)
        return self.ptr(array.adr, _depends_on_=array)
class CIntType(PtrArrFactoryMixIn, integer.CIntType): pass
class CFloatType(PtrArrFactoryMixIn, float.CFloatType): pass
class CEnumType(PtrArrFactoryMixIn, enum.CEnumType): pass
class CArrayType(PtrArrFactoryMixIn, array.CArrayType): pass
class CPointerType(PtrArrFactoryMixIn, pointer.CPointerType): pass
class CStructType(PtrArrFactoryMixIn, struct.CStructType): pass
class CUnionType(PtrArrFactoryMixIn, union.CStructType): pass
class CVectorType(PtrArrFactoryMixIn, vector.CVectorType): pass
class CFuncType(PtrArrFactoryMixIn, function.CFuncType):
    @property
    def ptr(self):
        return CFuncPointerType(self)
class CFuncPointerType(PtrArrFactoryMixIn, funcpointer.CFuncPointerType): pass


class BuildInDefs:

    long_long = CIntType('long long', 64, True, ct.c_int64)
    signed_long_long = CIntType('signed long long', 64, True, ct.c_int64)
    unsigned_long_long = CIntType('unsigned long long', 64, False, ct.c_uint64)

    int = CIntType('int', 32, True, ct.c_int32)
    signed_int = CIntType('signed int', 32, True, ct.c_int32)
    unsigned_int = CIntType('unsigned int', 32, False, ct.c_uint32)

    short = CIntType('short', 16, True, ct.c_int16)
    signed_short = CIntType('signed short', 16, True, ct.c_int16)
    unsigned_short = CIntType('unsigned short', 16, False, ct.c_uint16)

    long = CIntType('long', 32, True, ct.c_int32)
    signed_long = CIntType('signed long', 32, True, ct.c_int32)
    unsigned_long = CIntType('unsigned long', 32, False, ct.c_uint32)

    char = CIntType('char', 8, False, ct.c_char)
    signed_char = CIntType('signed char', 8, False, ct.c_char)
    unsigned_char = CIntType('unsigned char', 8, False, ct.c_ubyte)

    float = CFloatType('float', 32, ct.c_float)

    double = CFloatType('double', 64, ct.c_double)

    long_double = CFloatType('long double', 80, ct.c_longdouble)

    _Bool = CIntType('_Bool', 8, False, ct.c_bool)

    void = CVoidType()


# add names with '__' in front manually...
setattr(BuildInDefs, '__builtin_va_list', BuildInDefs.void.ptr)
