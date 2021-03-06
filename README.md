# Headlock - Python/C Bridge for Unittesting

[![buildstate](https://api.travis-ci.com/mrh1997/headlock.svg?branch=master "Build State")](https://travis-ci.com/mrh1997/headlock)
[![docstate](https://readthedocs.org/projects/headlock/badge/?version=latest "Documentation Generation State")](https://headlock.readthedocs.io/en/latest/)

## About

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


## Sample

This piece of C-code contains a macros, a struct a function
implementation and a function that is relying on
(which should be mocked):

```c
#include "underlying_module.h"

struct ops_t
{
    int a, b;
} ;

#define MACRO_2   (MACRO_1 + 1)

int func(struct ops_t * p)
{
    return underlying_func(p->a + p->b + MACRO_1);
}
```

You can access it from python through *headlock* like:

```python
from headlock.testsetup import TestSetup, CModule

@CModule('dummy.c', MACRO_1=1)
class TSSample(TestSetup):
    def underlying_func_mock(self, param):
        return param.val + 4000

with TSSample() as ts:
    ops = ts.struct.ops_t(a=ts.MACRO_2, b=20)
    assert ts.func(ops.ptr).val == 4021
```

This demonstrates how:
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

## Status

Currently this is alpha.

For a list of planned but not yet implemented features please refer to
[Development Status](https://headlock.readthedocs.io/en/latest/development-status.html)