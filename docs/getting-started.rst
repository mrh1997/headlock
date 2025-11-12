###############
Getting Started
###############


Requirements
============

The following prerequisites are required by headlock and
thus have to be installed before using it.
Currently it is only explicitly tested  with the minimal version requirements.
Higher versions should work nevertheless.

 * Windows, Linux, or macOS are required
 * `CPython 3 <https://www.python.org/downloads/release>`_
   Version 3.6 or higher is required
 * `LLVM <http://releases.llvm.org/download.html>`_ (Version 7.0.0 or higher).
 * A C compiler is required:

   * **Windows:** `MinGW <https://winlibs.com/>`_ at `C:\Program Files\mingw64`
     respective `C:\Program Files (x86)\mingw32`
   * **Linux:** GCC
   * **macOS:** Clang (from Xcode Command Line Tools or Homebrew)

   Later other C compilers shall :ref:`be supported <dev-status>`!



Installation
============

The easiest way to install headlock is from
`PyPI <https://pypi.org/project/headlock/>`_ via pip. To Install the
most up-to-date stable release (|release|) run:

.. code-block:: sh

   pip install headlock

Alternatively one can install the latest development branch directly
from the `github repository <https://github.com/mrh1997/headlock>`_ via

.. code-block:: sh

   pip install git+https://github.com/mrh1997/headlock.git

.. attention::

   AVIRA and maybe also other virus scanners seems to delay loading DLLs
   compiled a moment ago by multiple seconds
   `(see this link) <https://hero.handmade.network/forums/code-discussion/t/2948-loadlibrary_very_slow>`_.
   As this feature is essential for headlock, you must add you project directory
   to the list of directories, that shall not be scanned by the realtime
   scanner. Otherwise the first instantiation of a testsetup will require
   10-30 seconds per run.

Usage
=====

The following sample demonstrates the basic features of headlock. That
is automaticially compile and load a piece of C code (including mocking and
prepocessor macros via command line) and calling it from python.

The following demo C code has 3 implementations for
incrementing a given integer by the macro ``INCREMENT_OFFSET``
(has to be set via compiler command line):

.. code-block:: C

    int increment(int number)
    {
        return number + INCREMENT_OFFSET;
    }

    void increment_inplace(int * number)
    {
        *number += INCREMENT_OFFSET;
        return;
    }

    struct add_operands_t {
        int op1, op2;
    };
    extern int external_adder(struct add_operands_t * ops);

    int increment_via_extfunc(int number)
    {
        // adder_from_other_module() is not part of this file!
        struct add_operands_t ops = { number, INCREMENT_OFFSET };
        return external_adder(&ops);
    }

Lets assume this code is stored in ``test.c`` and shall be tested from python.
Then the following python file (in this case in the same directory)
will call the ``increment*()`` functions and
test if their result is correct::

   from headlock.testsetup import TestSetup, CModule

   @CModule('test.c', INCREMENT_OFFSET=1)
   class TSSample(TestSetup):
       def external_adder_mock(self, ops):
           return ops.ref.op1 + ops.ref.op2

   ts = TSSample()

   # test increment():
   assert ts.increment(10) == 11

   # test increment_inplace()
   int_var = ts.int(10)
   ts.increment_inplace(int_var.adr)
   assert int_var == 11

   # test increment_via_extfunc()
   ts.adder_mock = lambda ops: ops.op1 + ops.op2   # mock required func
   assert ts.increment_via_extfunc(10) == 11

   # this call is recommended (although it will be done implicitly otherwise)
   ts.__unload__()