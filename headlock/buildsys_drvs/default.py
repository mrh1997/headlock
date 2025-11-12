"""
This module selects a default BuildDescription class for the current platform

ATTENTION: This module might be monkey patched
"""
import sys
import platform

if sys.platform == 'win32':
    from . import mingw
    if platform.architecture()[0] == '32bit':
        BUILDDESC_CLS = mingw.MinGW32BuildDescription
    else:
        BUILDDESC_CLS = mingw.MinGW64BuildDescription
elif sys.platform == 'linux':
    from . import gcc
    if platform.architecture()[0] == '32bit':
        BUILDDESC_CLS = gcc.GccLinux32BuildDescription
    else:
        BUILDDESC_CLS = gcc.GccLinux64BuildDescription
elif sys.platform == 'darwin':
    from . import gcc
    if platform.machine() == 'arm64':
        BUILDDESC_CLS = gcc.GccMacOSArm64BuildDescription
    else:
        BUILDDESC_CLS = gcc.GccMacOS64BuildDescription
else:
    raise NotImplementedError('This OS is currently not supported')
