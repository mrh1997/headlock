.. _dev-status:

#############################
Current Status Of Development
#############################

.. image:: https://readthedocs.org/projects/headlock/badge/?version=stable
   :alt: Documentation Generation Status

.. image:: https://api.travis-ci.com/mrh1997/headlock.svg?branch=master
   :target: https://travis-ci.com/mrh1997/headlock

.. attention::
    The currently implementation of headlock is an alpha version.
    Although it is already in production use at http://www.baltech.de
    it must be noted that the **the API is not stable yet**!

The current status of the project
(preliminary limitations/not yet implemented features)
is shown in the following list:

 * Works only with GCC/Clang (Linux/macOS) or MinGW (Windows)
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


Bugreports/Pullrequests
=======================

Bugreports/Pullrequests can be provided via the page of
`GitHub Page of the project <https://github.com/mrh1997/headlock>`_