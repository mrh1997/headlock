.. _dev-status:

#############################
Current Status Of Development
#############################


.. attention::
    The currently implementation of headlock is an alpha version.
    Although it is already in production use at http://www.baltech.de
    it must be noted that the **the API is not stable yet**!

The current status of the project
(preliminary limitations/not yet implemented features)
is shown in the following list:

 * Works only on Windows
 * Requires MingW64 Toolchain
 * Works only with 32bit Python
 * Requires LLVM
 * Does not support specifying packing of structures in C sources
   (``#pragma pack``).
   As workaround it is possible to specify packing on a per-C-file basis in
   the Testsetup.
 * No Support yet for:
   * enum
   * union
   * float/double
   * calling/mocking inline functions
 * Does not support running testsetups on
   external process / other machine / embdedded system


Begreports/Pullrequests
=======================

Bugreports/Pullrequests can be provided via the page of
`GitHub Page of the project <https://github.com/mrh1997/headlock>`_