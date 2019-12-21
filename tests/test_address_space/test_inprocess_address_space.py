import pytest
import ctypes as ct
from headlock.address_space.inprocess import InprocessAddressSpace
from pathlib import Path
from contextlib import contextmanager
from tempfile import TemporaryDirectory
from unittest.mock import Mock
from headlock.buildsys_drvs.default import BUILDDESC_CLS


C2PY_BRIDGES_PER_SIG = 2

@contextmanager
def addrspace_for(py2c_retval='1',
                  c2py_sig0_inst0=0, c2py_sig0_inst1=0, c2py_sig1_inst0=0,
                  custom_code=''):
    bridge_code = """
        int _py2c_bridge_(
                int sig_id, void (*func_ptr)(void), unsigned char * params, 
                unsigned char * retval, void * * jmp_dest)
        {
            return """+str(py2c_retval)+""";
        }
        void (* _c2py_bridge_handler)
                    (int, int, unsigned char *, unsigned char *);
        typedef void (* _c2py_bridge_t)(void);
        static _c2py_bridge_t _c2py_bridges_sig0[] = { 
            (_c2py_bridge_t) """+str(c2py_sig0_inst0)+""", 
            (_c2py_bridge_t) """+str(c2py_sig0_inst1)+""" };
        static _c2py_bridge_t _c2py_bridges_sig1[] = { 
            (_c2py_bridge_t) """+str(c2py_sig1_inst0)+""", 
            (_c2py_bridge_t) 0 };
        _c2py_bridge_t * _c2py_bridges[] = { 
            _c2py_bridges_sig0, _c2py_bridges_sig1, };
    """
    with TemporaryDirectory() as tempdir:
        dummy_dll_dir = Path(tempdir)
        c_file = Path(dummy_dll_dir) / 'source.c'
        c_file.write_text(bridge_code + custom_code)
        builddesc = BUILDDESC_CLS('dummy', dummy_dll_dir)
        builddesc.build([c_file])
        addrspace = InprocessAddressSpace(
            str(builddesc.exe_path()),
            ['sigid0', 'sigid1', 'sigid2', 'sigid3'],
            {0, 1},
            C2PY_BRIDGES_PER_SIG)
        try:
            yield addrspace
        finally:
            addrspace.close()

@pytest.fixture
def inproc_addrspace():
    with addrspace_for() as inproc_addrspace:
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
    with addrspace_for(custom_code='char text[] = "HELLO";') \
            as inproc_addrspace:
        text_adr = inproc_addrspace.get_symbol_adr('text')
        assert inproc_addrspace.read_memory(text_adr, 5) == b'HELLO'

def test_getSymbolAdr_onFunction_returnsAddressOfFunc():
    with addrspace_for(custom_code='int ret123(void) { return 123; }')\
            as inproc_addrspace:
        ret123_adr = inproc_addrspace.get_symbol_adr('ret123')
        ret123_func = ct.CFUNCTYPE(ct.c_short)(ret123_adr)
        assert ret123_func() == 123

def test_invokeCFunc_onUnknownSigId_raisesValueError(inproc_addrspace):
    with pytest.raises(ValueError):
        inproc_addrspace.invoke_c_func(0, 'invalid_sigid', 0, 0)

def test_invokeCFunc_onBridgeReturnsFalse_raisesValueError():
    with addrspace_for(py2c_retval='0') as inproc_addrspace:
        with pytest.raises(ValueError):
            inproc_addrspace.invoke_c_func(0, 'sigid0', 0, 0)

def test_invokeCFunc_onBridgeReturnsTrue_passesAllParameters():
    retval_src = 'sig_id == 1 && ' \
                 '(void*) func_ptr == (void*) 123 && ' \
                 '(void*) params == (void*) 456 && '\
                 '(void*) retval == (void*) 789'
    with addrspace_for(py2c_retval=retval_src) as inproc_addrspace:
        inproc_addrspace.invoke_c_func(123, 'sigid1', 456, 789)

def test_createCallback_onUnknownSigId_raisesValueError(inproc_addrspace):
    with pytest.raises(ValueError):
        inproc_addrspace.create_c_callback('invalid_sigid', Mock())

def test_createCallback_returnsAddressOfC2PyBridge():
    with addrspace_for(c2py_sig1_inst0=123456) as inproc_addrspace:
        assert inproc_addrspace.create_c_callback('sigid1', Mock()) \
               == 123456

def test_createCallback_onMultipleCallsOnSameSigId_returnsNextAdr():
    with addrspace_for(c2py_sig0_inst1=123) as inproc_addrspace:
        inproc_addrspace.create_c_callback('sigid0', Mock())
        assert inproc_addrspace.create_c_callback('sigid0', Mock()) == 123

def test_createCallback_onCallsToDifferentSigId_returnsFirstAdrOfEverySigId():
    with addrspace_for(c2py_sig0_inst0=123, c2py_sig1_inst0=456) \
            as inproc_addrspace:
        inproc_addrspace.create_c_callback('sigid0', Mock())
        assert inproc_addrspace.create_c_callback('sigid1', Mock()) == 456

def test_createCallback_onTooMuchInstancesPerSigId_raisesValueError():
    with addrspace_for() as inproc_addrspace:
        for cnt in range(C2PY_BRIDGES_PER_SIG):
            inproc_addrspace.create_c_callback('sigid0', Mock())
        with pytest.raises(ValueError):
            inproc_addrspace.create_c_callback('sigid0', Mock())

def test_createCallback_registersPassedFuncForBeingCalledByC2PyBridgeHandler():
    with addrspace_for() as inproc_addrspace:
        callback = Mock()
        inproc_addrspace.create_c_callback('sigid1', callback)
        c2py_bridge_handler_t = ct.CFUNCTYPE(
            None, ct.c_int, ct.c_int, ct.c_void_p, ct.c_void_p)
        c2py_bridge_handler = c2py_bridge_handler_t.in_dll(
            inproc_addrspace.cdll, '_c2py_bridge_handler')
        c2py_bridge_handler(
            1, 0, ct.cast(123, ct.c_void_p), ct.cast(456, ct.c_void_p))
        callback.assert_called_once_with(123, 456)
