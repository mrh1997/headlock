import pytest
import ctypes as ct
from headlock.address_space.inprocess import InprocessAddressSpace
from pathlib import Path
from contextlib import contextmanager
from tempfile import TemporaryDirectory
from unittest.mock import Mock
from headlock.buildsys_drvs.default import BUILDDESC_CLS


MAX_C2PY_BRIDGE_INSTANCES = 4
MAX_SIG_CNT = 3

def bridge_src(bridge_array=None, py2c_retval='1'):
    bridge_array = bridge_array or ([[0] * MAX_C2PY_BRIDGE_INSTANCES])
    max_bridge_inst_str = str(MAX_C2PY_BRIDGE_INSTANCES).encode('ascii')
    return (
        b'int _py2c_bridge_(int bridge_ndx, void (*func_ptr)(void), '
                          b'unsigned char * params, unsigned char * retval)\n'
        b'{\n'
        b'\treturn ' + py2c_retval.encode('ascii') + b';\n' +
        b'}\n'
        b'void (* _c2py_bridge_handler)'
                            b'(int, int, unsigned char *, unsigned char *);\n'
        b'typedef void (* _c2py_bridge_t)(void);\n'
        b'_c2py_bridge_t _c2py_bridge_[][' + max_bridge_inst_str + b'] = {\n' +
        b''.join(
            b'\t{ ' + b', '.join(b'(_c2py_bridge_t) ' + str(v).encode('ascii')
                                 for v in insts) +b'},\n'
            for insts in bridge_array) +
        b'};')

@contextmanager
def addrspace_for(content):
    with TemporaryDirectory() as tempdir:
        dummy_dll_dir = Path(tempdir)
        c_file = Path(dummy_dll_dir) / 'source.c'
        c_file.write_bytes(content)
        builddesc = BUILDDESC_CLS('dummy', dummy_dll_dir)
        builddesc.build([c_file])
        addrspace = InprocessAddressSpace(
            str(builddesc.exe_path()),
            {f'py2c_sigid{ndx}': ndx for ndx in range(MAX_SIG_CNT)},
            {f'c2py_sigid{ndx}': ndx for ndx in range(MAX_SIG_CNT)},
            MAX_C2PY_BRIDGE_INSTANCES)
        try:
            yield addrspace
        finally:
            addrspace.close()

@pytest.fixture
def inproc_addrspace():
    with addrspace_for(bridge_src()) as inproc_addrspace:
        yield inproc_addrspace

def test_readMemory_returnsDataAtAddress(inproc_addrspace):
    adr = ct.addressof(ct.create_string_buffer(b'ABCDE'))
    assert inproc_addrspace.read_memory(adr, 5) == b'ABCDE'

def test_writeMemory_modifiesDataAtAddress(inproc_addrspace):
    buffer = ct.create_string_buffer(5)
    inproc_addrspace.write_memory(ct.addressof(buffer) + 1, b'ABC')
    assert buffer[:5] == b'\x00ABC\x00'

def test_writeMemory_onBytearray_ok(inproc_addrspace):
    buffer = ct.create_string_buffer(3)
    inproc_addrspace.write_memory(ct.addressof(buffer), bytearray(b'ABC'))
    assert buffer[:3] == b'ABC'

def test_allocMemory_returnsInt(inproc_addrspace):
    adr = inproc_addrspace.alloc_memory(12345)
    assert inproc_addrspace.read_memory(adr, 12345) == b'\x00' * 12345

def test_allocMemory_onMultipleCalls_returnsNewBlocks(inproc_addrspace):
    adrs = {inproc_addrspace.alloc_memory(10) for c in range(10000)}
    assert len(adrs) == 10000  # *.address are disjunct

def test_getSymbolAdr_onInvalidSymbol_raisesValueError(inproc_addrspace):
    with pytest.raises(ValueError):
        inproc_addrspace.get_symbol_adr('not_existing_symbol')

def test_getSymbolAdr_onVariable_returnsAddressOfVariable():
    with addrspace_for(bridge_src() + b'char text[] = "HELLO";') \
            as inproc_addrspace:
        text_adr = inproc_addrspace.get_symbol_adr('text')
        assert inproc_addrspace.read_memory(text_adr, 5) == b'HELLO'

def test_getSymbolAdr_onFunction_returnsAddressOfFunc():
    with addrspace_for(bridge_src() + b'int ret123(void) { return 123; }')\
            as inproc_addrspace:
        ret123_adr = inproc_addrspace.get_symbol_adr('ret123')
        ret123_func = ct.CFUNCTYPE(ct.c_short)(ret123_adr)
        assert ret123_func() == 123

def test_invokeCCode_onUnknownSigId_raisesValueError(inproc_addrspace):
    with pytest.raises(ValueError):
        inproc_addrspace.invoke_c_code(0, 'invalid_sigid', 0, 0)

def test_invokeCCode_onBridgeReturnsFalse_raisesValueError():
    with addrspace_for(bridge_src(py2c_retval='0')) as inproc_addrspace:
        with pytest.raises(ValueError):
            inproc_addrspace.invoke_c_code(0, 'py2c_sigid0', 0, 0)

def test_invokeCCode_onBridgeReturnsTrue_passesAllParameters():
    src = bridge_src(py2c_retval='bridge_ndx == 2 && '
                                 '(void*) func_ptr == (void*) 123 && '
                                 '(void*) params == (void*) 456 && '
                                 '(void*) retval == (void*) 789')
    with addrspace_for(src) as inproc_addrspace:
        inproc_addrspace.invoke_c_code(123, 'py2c_sigid2', 456, 789)

def test_createCCode_onUnknownSigId_raisesValueError(inproc_addrspace):
    with pytest.raises(ValueError):
        inproc_addrspace.create_c_code('invalid_sigid', Mock())

def test_createCCode_returnsAddressOfC2PyBridge():
    with addrspace_for(bridge_src([[], [], [123456]])) as inproc_addrspace:
        assert inproc_addrspace.create_c_code('c2py_sigid2', Mock()) == 123456

def test_createCCode_onMultipleCallsOnSameSigId_returnsNextAdr():
    with addrspace_for(bridge_src([[0, 123]])) as inproc_addrspace:
        inproc_addrspace.create_c_code('c2py_sigid0', Mock())
        assert inproc_addrspace.create_c_code('c2py_sigid0', Mock()) == 123

def test_createCCode_onCallsToDifferentSigId_returnsFirstAdrOfEverySigId():
    with addrspace_for(bridge_src([[123], [456]])) as inproc_addrspace:
        inproc_addrspace.create_c_code('c2py_sigid0', Mock())
        assert inproc_addrspace.create_c_code('c2py_sigid1', Mock()) == 456

def test_createCCode_onTooMuchInstancesPerSigId_raisesValueError():
    bridge_array = [list(range(MAX_C2PY_BRIDGE_INSTANCES))]
    with addrspace_for(bridge_src(bridge_array)) as inproc_addrspace:
        for cnt in range(MAX_C2PY_BRIDGE_INSTANCES):
            inproc_addrspace.create_c_code('c2py_sigid0', Mock())
        with pytest.raises(ValueError):
            inproc_addrspace.create_c_code('c2py_sigid0', Mock())

def test_createCCode_registersPassedFuncForBeingCalledByC2PyBridgeHandler():
    with addrspace_for(bridge_src([[], []])) as inproc_addrspace:
        callback = Mock()
        inproc_addrspace.create_c_code('c2py_sigid1', callback)
        c2py_bridge_handler_t = ct.CFUNCTYPE(
            None, ct.c_int, ct.c_int, ct.c_void_p, ct.c_void_p)
        c2py_bridge_handler = c2py_bridge_handler_t.in_dll(
            inproc_addrspace.cdll, '_c2py_bridge_handler')
        c2py_bridge_handler(
            1, 0, ct.cast(123, ct.c_void_p), ct.cast(456, ct.c_void_p))
        callback.assert_called_once_with(123, 456)
