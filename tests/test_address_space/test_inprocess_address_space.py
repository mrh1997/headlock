import pytest
import ctypes as ct
from headlock.address_space.inprocess import InprocessAddressSpace
from headlock.toolchains import TransUnit
from pathlib import Path


def create_tool_chain():
    import sys, platform
    if sys.platform == 'win32':
        if platform.architecture()[0] == '32bit':
            from headlock.toolchains.mingw import MinGW32ToolChain as ToolChain
        else:
            from headlock.toolchains.mingw import MinGW64ToolChain as ToolChain
    else:
        if platform.architecture()[0] == '32bit':
            from headlock.toolchains.gcc import Gcc32ToolChain as ToolChain
        else:
            from headlock.toolchains.gcc import Gcc64ToolChain as ToolChain
    return ToolChain()

def dummy_clib(name, content):
    dummy_dll_dir = Path(__file__).parent / 'dummy_clibs' / name
    dummy_dll_dir.mkdir(exist_ok=True, parents=True)
    c_file = Path(dummy_dll_dir) / 'source.c'
    c_file.write_bytes(content)
    tool_chain = create_tool_chain()
    trans_unit = TransUnit(name, c_file)
    tool_chain.build(name, dummy_dll_dir, [trans_unit], [], [])
    return ct.CDLL(str(tool_chain.exe_path(name, Path(dummy_dll_dir))))

@pytest.fixture
def inproc_addrspace():
    return InprocessAddressSpace([])

def test_readMemory_returnsDataAtAddress(inproc_addrspace):
    adr = ct.addressof(ct.create_string_buffer(b'ABCDE'))
    assert inproc_addrspace.read_memory(adr, 5) == b'ABCDE'

def test_writeMemory_modifiesDataAtAddress(inproc_addrspace):
    buffer = ct.create_string_buffer(5)
    inproc_addrspace.write_memory(ct.addressof(buffer) + 1, b'ABC')
    assert buffer[:5] == b'\x00ABC\x00'

def test_allocMemory_returnsInt(inproc_addrspace):
    adr = inproc_addrspace.alloc_memory(12345)
    assert isinstance(adr, int)

def test_allocMemory_onMultipleCalls_returnsNewBlocks(inproc_addrspace):
    adrs = {inproc_addrspace.alloc_memory(10) for c in range(10000)}
    assert len(adrs) == 10000  # *.address are disjunct

def test_getSymbolAdr_onInvalidSymbol_raisesValueError(inproc_addrspace):
    with pytest.raises(ValueError):
        inproc_addrspace.get_symbol_adr('not_existing_symbol')

def test_getSymbolAdr_onVariable_returnsAddressOfVariable():
    clib_with_var456 = dummy_clib('var456',
                                  b'short var456 = 456;')
    inproc_addrspace = InprocessAddressSpace([clib_with_var456])
    var456_adr = inproc_addrspace.get_symbol_adr('var456')
    assert ct.c_short.from_address(var456_adr).value == 456

def test_getSymbolAdr_onMultipleDlls_searchesAllDlls():
    clib_empty = dummy_clib('empty', b'')
    clib_with_symbol = dummy_clib('symbol', b'short symbol = 11;')
    inproc_addrspace = InprocessAddressSpace([clib_empty, clib_with_symbol])
    symbol_adr = inproc_addrspace.get_symbol_adr('symbol')
    assert ct.c_short.from_address(symbol_adr).value == 11

def test_getSymbolAdr_onFunction_returnsAddressOfFunc():
    clib_with_ret123 = dummy_clib('ret123',
                                  b'short ret123(void) { return 123; }\n'
                                  b'short (*ret123_ptr)(void) = ret123;')
    inproc_addrspace = InprocessAddressSpace([clib_with_ret123])
    ret123_adr = inproc_addrspace.get_symbol_adr('ret123')
    ret123_func = ct.CFUNCTYPE(ct.c_short)(ret123_adr)
    assert ret123_func() == 123
