# About

This is an adapter for testing C code via tests written in python.
When being combined i.e. with pytest it provides a very powerful and
convinient way of writing (unit-/integration-) tests for C code.

In contrary to other C/Python bridges (like ctypes, cffi, swing, ...)
the goals of this projects are:

 - Run (and Compile) a piece of C code (Module Under Test)
   out of the box with as less lines of Python code as possible.
   No need to create Makefile, no need to run extra build steps.
 - Provide a simple, intuitive API for accessing C objects
 - Allow to quickly:
   - mock the underlying C modules in Python
   - work with different binaries of a Module Under Test at
     the same time.
   - testing a Module Under Test with binaries compiled with
     different preprocessor defines
 - Run the C code in a separate Address Space to avoid that a crashing
   Module Under Test crashes also the testing python code
   (Not implemented yet!).
 - Especially make it work with embedded systems, so that
   - C code can be run on *real hardware* while python tests run on PC.
     (Mainly useful for integration tests)
     This is not implemented yet!
   - C code can be run on PC instead of embedded environment.
    (Mainly useful for unittests)

Explicitly Non-Goals Are:

 - Supporting C++ is not planned
 - Performance has a very low priority. This does not mean that it is
   slow. But if speed conflicts with one of the goals of this project,
   there will be no compromises in favour of speed.
 - Being self-contained is not planned. A C-compiler is required
   to be installed. Furthermore currently LLVM has to be installed
   at it is used for parsing the file.
 - Python < 3.6 will never be supported


# Sample

If your dummy.c (Module Under Test) looks like

```c
#include "underlying_module.h"

struct ops_t
{
    int a, b;
} ;

#define C_MACRO   1

int func(struct ops_t * p)
{
    return underlying_func(p->a + p->b + PY_MACRO);
}
```

You can access it from python like:

```python
from headlock.testsetup import TestSetup

class TSSample(TestSetup.c_mixin('dummy.c', PY_MACRO=300)):
    def underlying_func_mock(self, param):
        return param.val + 4000

with TSSample().__execute__() as ts:
    ops = ts.struct.ops_t(a=ts.C_MACRO, b=20)
    assert ts.func(ops.ptr).val == 4321
```

This demonstrates:
 * You can handle different binaries of the same C-source per .py file
   (as each one is a TestSetup derived class instead of a module)
 * Every binary can be compiled with other parameters
   (PY_MACRO can be set differently per testsetup)
 * structures/unions/enums/typedefs can be accessed from Python without
   extra declarations (```struct ops_t``` in this case).
 * You can access C-functions from Python without extra declarations
   (```func``` in this case)
 * You can access C-macros from Python without extra declarations
   (```C_MACRO``` in this case)
 * You can call python-methods from C (=mocking C functions that are
   not part of the Module Under Test;
   ```underlying_func``` in this case). It is even possible to
   dynamicially replace mocks (i.e. by unittest.mock.Mock())

# Status

Currently this is pre-alpha (although it is already in production
use). This means the API is **not** stable and currently has a lot of
rough edges.

Furthermore currently there is no documentation at all,
although this has the highest priority on the roadmap.

The current limitations are

 - Works only with 32bit (Python and C)
 - Works only on Windows with MingW64
   (the installation had to be configured as
   ```i686-*-*-dwarf-rt_v5-*```)
 - Requires LLVM. Has to be installed to
   ```C:\Program Files (x86)\LLVM```.
 - Requires CMake for creating the Makefiles. Has to be on ```PATH```.
 - Does not support specifying packing of structures
   (```#pragma pack```). As the current application (embedded C)
   requires a packing of 1 *headlock* assumes that **all** structues
   are packed by a packing of 1.
 - No Support yet for:
    - enum
    - union
    - float/double
