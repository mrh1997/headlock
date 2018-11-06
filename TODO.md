Interface changing
------------------
 * subtracting pointers returns int instead of CInt
 * implicit add zero element to .alloc_ptr(...) and .ptr on iterables
 * travis integration + pip deployment automatisieren bei tag
 * rework datamodel:
   - replace all proxies by a single class that refers to a memory
     location and a type object.
   - All methods of the proxies are forwarded to the C type specific
     type object.
   - the type object is "bound" to a "environment"

Small (can be done by occassion)
--------------------------------
* globale (nicht CModule) spezifische settings (preprocessor defines
  sowie compilersettings wie z.B. toolchain selection) in TestSetup
* provide method for non-CObjs to cast itself to a corresponding CObj.
  I.e. ts.task_xyz could be passed directly then (instead of ts.task_xyz.handle)
* add support for further operations to CObj/CInt (i.e. mul / div on int)
* currently obj.ptr.ptr.ref.ref.ptr.ptr.ref.ref creates a very long linked list.
  Could be optimized...
* add all variables/typedefs to a separate namespace .typedef and .globals
* pyplugin and os_mock currently construct cyclic references by storing
  bound functions (for the callbacks). Should be replaced by WeakMethods and
  CFunc has to support these WeakMethods.
* add repr function to CObjTypes
* enums/floats are not supported yet
* Option to make warnings to errors (can only be done if cdecl warning can be moved away)
* Add ``__set__()`` to CObj type which throws error to ensures that 
  ``ts.global = 3`` or ``ts.struct.x.y = 3`` fails
* Replace _global_refs_ dictionary by option during creation of object.
  When settings this option the element is not freed until destruction
  of testsetup
* whitelisting for objects from system headers which shall not be skipped
  (to allow them to be used in a playground). the whitelist has to be
  specified through testsetup
* "const int * array" cannot be used in function parameter
   ("WriteProtectedError" is raised)
* not parsable macros shall be overwritable: "class TS(TestSetup): MACRO = 9"
* Arrays (incomplete or not cannot be passed to funcs): "void func(int p1[], p2[10]);"
* Deny creation of arrays of 'CVoid': "ts.void.array(10)" -> raisey error
* move CompileError display from pytest-plugin to headlock, so that
  creating a testsetup in a playground gives reasonable error messages
* move VarPtr and MemPtr from pytest-plugin to headlock as they are
  not pytest specific (but specific to unittest.mock or similar)
* raise exception when writing a proxy without ".val". i.e.
  "x.ref = 2"
* raise error if detecting "__declspec(dllexport)" (does not work,
  but currently gives no obvious error message)
* add cobj.copy() to allow quick and easy duplicating a C object.
  If I want to duplicate a pointer to a struct currently
  "x = ts.struct.y_t(y)" is necessary.
* currently multiple parse runs (when working with multiple c files)
  are done with different CParser objects.
  This causes multiple definitions of the same type but with different
  IDs. In future the CParser should work with an external database, so
  that already parsed types are reused.
* introduce "permanent reference" as replacement for TestSetup._global_refs_.
  They are done by simply running "obj @ ts". Object may be a python object,
  in which case it is converted to a CObj before adding a permanent reference.
  I.e. ts(b"test") would create a python string. This construct should
  avoid circular references, i.e.: "ts.func_ptr(ts.func) @ ts"
  (via external dictionary?!?)!
  Furthermore a new context could be introdced for "temporary references".
  All references created while the context are released after the context.
  Maybe use functionname instead of __rmatmul__ for clarity?!?



Medium
------
* At the moment TestSetup.get_root_dir() has to be overwitten or the path to
  the C-file has to be specified absolute 
* create PyFunc which derives from CFunc and is used to wrap python funcs
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
  * Make ownership clear:
     - .adr creates owner of myself
     - nested structures created from python objects shall ensure ownership.
       THIS IS NOT THE CASE YET. ie.: ts.strct(b'string') does not work yet,
       as the pointer to b'string' is immediately freed after creation.
* replace logging system by more versatile one (buildin logging framework?!?)
    * possibility to parametrize logging (of calls c/python) by specifying
      funcs/args to be logged/way what exactly shall be logged
* ensure that operators (i.e. ==, +, -, ...) are working only on same/matching
  type (i.e. cannot compare pointer to int)
* CParser cannot read macros with &&, ||, ! operators
  (has to be converted to and/or/not)
* wird "with ts:" verschachtelt aufgerufen, hängt sich headlock auf
* generator for .pyi files, so that type-completion works on testsetups
  (to make it work on testsetups you have to enter "test_xyt(ts:ts):"
   then)
* raise "WriteProtectedError" if trying to write to "const" object
  (note that this must NOT be the case during initialization)


Major/Investigation necessary
-----------------------------
* run C code in separate process and provide generic protocol interface for
  communication
* generate header definitions (CLang support)
  + if a macro is set in the TestSetup it must not be overwritten by the parser
    (= allow overwriting macros)
* test C instrumentalization (address sanitizer, see -f... flags)
* packing pragma (attribute?) is not supported


Needed for publishing
---------------------
* support "static inline" function / macros by making them replacable/callable
  (header file rewriting?, create c funcs that calls macros/inline funcs, ...)
* system API shall be mockable, too. (i.e. network access). Solutions:
  * manually specify a list of sys-API funcs that shall be mocked
