###############
Getting Started
###############


Requirements
============

The following prerequisites are required by headlock and
thus have to be installed before using it.
Currently it is only explicitly tested  with the minimal version requirements.
Higher versions should work nevertheless.

 * Windows (Linux/Mac are :ref:`not supported yet <dev-status>`)
 * `CPython 3 <https://www.python.org/downloads/release>`_
   Version 3.6 or higher is required 
   (Currently 64bit is :ref:`not supported <dev-status>`!)
 * `LLVM <http://releases.llvm.org/download.html>`_ (Version 4.0.1 or higher).
   32bit Version is currently required and has to be installed to
   (Later this requirement shall :ref:`be optional <dev-status>`!)
   ``C:\Program Files (x86)\LLVM``
 * `MinGW64 <http://mingw-w64.org/doku.php/download/mingw-builds>`_
   (Later other C compilers shall :ref:`be supported <dev-status>`!)



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
    extern int adder(struct add_operands_t * ops);

    int increment_via_extfunc(int number)
    {
        // adder_from_other_module() is not part of this file!
        struct add_operands_t ops = { number, INCREMENT_OFFSET);
        return external_adder(&ops);
    }

Lets assume this code is stored in ``test.c`` and shall be tested from python.
Then the following python file (in this case in the same directory)
will call the ``increment*()`` functions and
test if their result is correct::

   from headlock.testsetup import TestSetup, CModule

   @CModule('test.c', INCREMENT_OFFSET=1)
   class TSSample(TestSetup):
       pass

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
