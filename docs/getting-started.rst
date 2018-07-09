###############
Getting Started
###############


Requirements
============

.. note:: Requirements and installation instructions are preliminary,
   as currently there are a lot of :ref:`preliminary limitations <dev-status>`

The following prerequisites are required by headlock and
thus have to be installed before using it.
Currently it is only explicitly tested  with the minimal version requirements.
Higher versions should work nevertheless.

 * Windows (Linux/Mac are not supported yet)
 * `CPython 3 <https://www.python.org/downloads/release>`_
   Version 3.6 or higher is required (Currently 64bit is not supported!)
 * `LLVM <http://releases.llvm.org/download.html>`_ (Version 4.0.1 or higher).
   32bit Version is currently required and has to be installed to
   ``C:\Program Files (x86)\LLVM``
 * `MinGW64 <http://mingw-w64.org/doku.php/download/mingw-builds>`_
   (Version 6.2.0 or higher).



Installation
============

The easiest way to install headlock is from
`PyPI <https://github.com/pypa/headlock>`_ via pip:

   pip install headlock


Usage
=====

The following sample demonstrates how to automaticially compile and load
a piece of C code, so that it can be called from python.

Lets assume the following C code is stored in ``test.c`` and shall be tested
from python:

.. code-block:: C

   int increment_by_1(int number)
   {
       return number + 1;
   }

Then the following python code will call the *increment_by_1()* function and
test if its result is correct (Attention: Currently 'test.c' has to be
specified relative to the headlock-directory; alternatively an absolute path
has to be passed or get_root_dir() has to be overwritten)::

   from headlock.testsetup import TestSetup, CModule

   @CModule('test.c')
   class TSSample(TestSetup):
       pass   # define mock functions here if needed...

   with TSSample() as ts:   # within this context the C-code is loaded and can be called
       assert ts.increment_by_1(10) == 11

