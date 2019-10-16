from . import AddressSpace


class VirtualAddressSpace(AddressSpace):
    """
    This is a dummy address space implementation. Maps all memory operations
    to the python bytearray .content and all bridging operations to .funcs.
    Its main purpose is for testing.
    """

    CODE_ADR_OFFSET = 100000000

    def __init__(self, content=b'', symbols=None):
        super().__init__()
        self.content = bytearray(content)
        self.symbols = {}
        self.funcs = {}
        for sym_name, sym_content in (symbols or {}).items():
            self.simulate_symbol(sym_name, sym_content)

    def simulate_symbol(self, sym_name, sym_content):
        if isinstance(sym_content, bytes):
            adr = len(self.content)
            self.symbols[sym_name] = adr
            self.content += sym_content
        elif callable(sym_content):
            adr = self.CODE_ADR_OFFSET + len(self.funcs)
            self.symbols[sym_name] = adr
            self.funcs[adr] = sym_content
        else:
            raise TypeError('symbol has to be of type bytes or callable')
        return adr

    def simulate_c_code(self, funcname, exp_sig_id:str=None,
                   exp_params:bytes=None, retval:bytes=None):
        """
        This helper allows to create functions, that can be passed to the
        symbols paramater of __init__. They will verify that invoke_c_func
        was called correctly
        """
        def c_code(sig_id, args_adr, retval_adr):
            assert exp_sig_id is None or exp_sig_id == sig_id
            assert exp_params is None \
                   or exp_params == self.read_memory(args_adr, len(exp_params))
            if retval is not None:
                self.write_memory(retval_adr, retval)
        return self.simulate_symbol(funcname, c_code)

    def read_memory(self, address, length):
        assert address >= 0 and length > 0
        assert address + length <= len(self.content)
        return bytes(self.content[address:address+length])

    def write_memory(self, address, data):
        data = bytes(data)
        assert address >= 0
        assert address + len(data) <= len(self.content)
        self.content[address:address+len(data)] = data

    def alloc_memory(self, length:int):
        address = len(self.content)
        self.content += b'\0'*length
        return address

    def get_symbol_adr(self, symbol_name):
        return self.symbols[symbol_name]

    def get_symbol_name(self, adr):
        for sym_name, sym_adr in self.symbols.items():
            if adr == sym_adr:
                return sym_name
        else:
            raise ValueError()

    def invoke_c_func(self, func_adr:int, sig_id:str,
                      args_adr:int, retval_adr:int):
        func = self.funcs[func_adr]
        return func(sig_id, args_adr, retval_adr)

    def create_c_callback(self, sig_id:str, pyfunc):
        adr = self.CODE_ADR_OFFSET + len(self.funcs)
        def callback_wrapper(act_sig_id, param_adr, retval_adr):
            assert act_sig_id == sig_id
            return pyfunc(param_adr, retval_adr)
        self.funcs[adr] = callback_wrapper
        return adr
