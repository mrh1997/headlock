.. _about:

#####
About
#####

Headlock is designed as an adapter for testing C code
via tests written in python.
When being combined i.e. with pytest it provides a very powerful and
convenient way of writing (unit-/integration-) tests for C code.

This results in differents goals when being compared to other (excellent)
C/Python bridges like ctypes, cffi, swig, cython, ...:

 * All the extra steps usually required for C are done under the hood.
   For the user adding a C file to a project is as simple as adding a
   python file.
   These steps done by headlock include:

    * No need to create Makefiles/Buildscripts.
    * No need to run extra build steps before using the C code.
    * No need to rewrite the C moduels interface definition (the header file)
      in Python.

 * Provide a simple, intuitive API for accessing C objects.
   The philosophy of this API is to be as orthogonal as possible and
   stick as near as possible to the corresponding C language operators/objects.
   Thus the effort for learning it should be kept low.

 * As being specially designed for unittesting, headlock includes
   support for typical testing tasks:

    * mock the underlying C modules in Python without any line of extra
      wrapper code
    * Vary not only the variables modifyable during runtime for testing
      corner cases but also the preprocessor defines.

 * **[PLANNED]** Run the C code in a separate address space to guarentee
   real test isolation. This will not only prevent a crashing test from
   crashing the whole test-runner, but especially avoids
   that a misbehaving Module Under Test leaves the test process
   in an undefined state. Otherwise in the worst case this could cause one of
   the following tests to return different results than when being
   run separately.

 * Especially make it work with embedded systems, so that

    * **[PLANNED]** C code can be executed on destination hardware.
      This is primary useful for integration tests as it allows to
      detect architecture specific problems (for non x86 hardware)
      and timing issues.
      Furthermore it allows to communicating with external components
      instead of mocking them which might show problems that where
      hidden by the mocks.
    * development of (non-device-driver) embedded C code can be
      done (via unittest) on a PC without the need to struggle
      with embedded hardware.

 * Integrates well with Testing tools (like unittest, pytest, ...)

 * **[PLANNED]** Being ToolChain agnostic via a plugin infrastructure.
   This includes not only the compiler, but for example on embedded systems
   also the infrastructure to load the firwmare into a device or communicate
   with it.

Explicitly Non-Goals Are:

   * Support for C++

   * High Performance (This does not mean that it is slow.
     But if speed conflicts with one of the goals of this project,
     there will be no compromises in favour of speed).

   * Being self-contained
     (At least A C-compiler will always be required to be installed).

   * Support for Python < 3.6
