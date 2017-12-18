Interface changing
------------------
 * Replace ts.__mem__ can ts.void.alloc_ptr(3)
   (does not work yet; furthermore the keywork "alloc" has to be
   implemented for pointers: ts.void.ptr.alloc(10)
 * rework datamodel:
   - replace all proxies by a single class that refers to a memory
     location and a type object.
   - All methods of the proxies are forwarded to the C type specific
     type object.
   - the type object is "bound" to a "environment"
 * run __startup__ in __init__ instead of context (same with __shutdown__)
   This allows much simpler demos.

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
  * INTRODUCE OWNER-SHIP CONCEPT!!! (how???)
* replace logging system by more versatile one (buildin logging framework?!?)
    * possibility to parametrize logging (of calls c/python) by specifying
      funcs/args to be logged/way what exactly shall be logged
* ensure that operators (i.e. ==, +, -, ...) are working only on same/matching
  type (i.e. cannot compare pointer to int)
* CParser cannot read macros with &&, ||, ! operators
  (has to be converted to and/or/not)
* wird "with ts:" verschachtelt aufgerufen, hängt sich headlock auf


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
