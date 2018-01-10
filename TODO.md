Small (can be done by occassion)
--------------------------------
* provide method for allowing any object to be cast to a CObj of a specific type
  I.e. ts.task_xyz could be passed directly then (instead of ts.task_xyz.handle)
* implicit cast buf() objects to pointers/array of type void/uint8_t
* add support for further operations to CObj/CInt (i.e. mul / div on int)
* currently obj.ptr.ptr.ref.ref.ptr.ptr.ref.ref creates a very long linked list.
  Could be optimized...
* support relative filenames in SOURCEFILES
* add all variables/typedefs to a separate namespace .typedef and .globals
* switch testsetup.py to pathlib
* pyplugin and os_mock currently construct cyclic references by storing
  bound functions (for the callbacks). Should be replaced by WeakMethods and
  CFunc has to support these WeakMethods.
* Provide alternative to CFunc.typedef:
  ts.rettype(ts.argtype1, ts.argtype2, ...)?
* .cstr functions shall always operate bytewise
* .val shall not accept .raw any more
* when only a single test was run, "rerun_first_failed_pytest" shall repeat this
  test no matter if it succeded or not
  (otherwise it is hard to debug into a passing test that should fail)
* replace value of LOGGER from stream to bool (simpler usage).
* CPointer initialization with python iterables should create a new object, that
  is referred by the CPointer (in contrary to pointer.val assignment, where the
  existing object is overwritten). Attention: should also work on void pointers.
* compiler warnings are currently not displayed
  (i.e. "X declared but never referenced")
* add repr function to CObjTypes
* Plugin callbacks sollen von CustomPattern gemockt werden können
   + Plugins callbacks sollen weggelassen werden können
     (und müssen dann von CustomPattern gemockt werden)
* introduce shortcut for ts.malloc(b'1234') => b'1234'
* autofind LLVM path (its hardcoded now)
* set CMAKE_RUNTIME_OUTPUT_DIRECTORY in CMakefile
  (and check if CLion takes it over; see https://blog.jetbrains.com/clion/2014/09/clion-answers-frequently-asked-questions/)
* enums are not supported yet
* Option to make warnings to errors (can only be done if cdecl warning can be moved away)
* Add ``__set__()`` to CObj type which throws error to ensures that 
  ``ts.global = 3`` or ``ts.struct.x.y = 3`` fails 


Medium
------
* create PyFunc which derives from CFunc and is used to wrap python funcs
* revert c_mixin() to decorator for classes (``@link(c_lib(*srcs, **defs))``).
  provide "delayed_link()" for linking at first instantiation.
  Furtermore provide ``c_lib().derive(*srcs, **defs)`` for creating slightly 
  modified versions 
* when passing parameters to C-functions, do allow only correct implicit casts
  (i.e. int.ptr -> int.ptr.ptr is allowed now). explicit PyObj casts shall be
  always OK. "cobj.val = cobj" shall correspond to explicit casts
  (same as "ctype(cobj)"")
* on exceptions within mocks jump directly to calling python code via setjmp
* depends_on:
  * remove _depends_on_ out of constructor (shall be set via member access
  * _depends_on_ should be checked for correctness again, as errors can be
    very tedious (i.e. CPointer does not reset _depends_on_ when setting to a
    different value currently)
  * INTRODUCE OWNER-SHIP CONCEPT!!! (how???)
* pyplugin has circle references (ts -> bound-funcs -> ts)
* Make dependency to pytest optional:
    - "test_" is removed from the test-filename when gererating the DLL-name
* replace logging system by more versatile one (buildin logging framework?!?)
* ensure that operators (i.e. ==, +, -, ...) are working only on same/matching
  type (i.e. cannot compare pointer to int)
* if only 'cmake-build-debug' will be deleted but not 'CMakeList.txt',
  the project does not compile any more if a directory contains more than one
  teststep (as mocks.c files are not created when CMakeFile will be processed)
* distinguish public and private dependencies in modules_defs
  (defines from public dependencies need to be included no matter if the
  file is mocked or  not).
* CParser cannot read macros with &&, ||, ! operators
  (has to be converted to and/or/not)


Major/Investigation necessary
-----------------------------
* run C code in separate process and provide generic protocol interface for
  communication
* generate header definitions (CLang support)
  + if a macro is set in the TestSetup it must not be overwritten by the parser
    (= allow overwriting macros)
* possibility to parametrize logging (of calls c/python) by specifying
  funcs/args to be logged/way what exactly shall be logged
* test C instrumentalization (address sanitizer, see -f... flags)
* clang fixes:
    - packing pragma (attribute?) is not supported
    - cdecl is not supported (the current workaround causes warnings)


Needed for publishing
---------------------
* abstract away buildsystem in separate class, to allow simple replacement of
  CMake by different compiling infrastructure.
* extract testsetup to git
* support "static inline" function / macros by making them replacable/callable
  (header file rewriting?, create c funcs that calls macros/inline funcs, ...)
* remove dependency to <rootpath> and Bros2 in TestSetup()
* PARSER_CACHE in testsetup.py currenty does not check if any of the
  source files was changed. This is fatal for interactive usage, as a c file
  could be edited during a python session.
* system API shall be mockable, too. (i.e. network access). Solutions:
  * manually specify a list of sys-API funcs that shall be mocked
  * search for .*_mock() funcs named as sys-.API funcs and automagically mock
    them
