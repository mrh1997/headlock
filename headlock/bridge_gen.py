"""
This module provides the code to generate the bridge code.
"""
from .c_data_model import CStructType, CFuncType, CPointerType, \
    CFuncPointerType, CIntType, CProxyType
import itertools
from typing import TextIO, Dict, Iterable


def write_required_struct_defs(output:TextIO, ctypes:Iterable[CProxyType]):
    """
    declares all structs that are required directly or indirectly by one of
    the typedefs 'ctypes'.
    """
    for cstruct_type in iter_req_structs_in_dep_order(ctypes):
        output.write(cstruct_type.c_definition() + ';\n')
    for cstruct_type in iter_req_structs_in_dep_order(ctypes,
                                                      only_embedded_types=True):
        output.write(cstruct_type.c_definition_full() + ';\n')
    output.write('\n')


def iter_req_structs_in_dep_order(ctypes, only_embedded_types=False):
    processed = set()
    def emb_struct_only(ctype, parent_ctype):
        return not (isinstance(ctype, CStructType)
                    and isinstance(parent_ctype, CPointerType))
    for ctype in ctypes:
        sub_types = ctype.iter_subtypes(
            top_level_last=True,
            filter=emb_struct_only if only_embedded_types else None,
            processed=processed)
        for sub_type in sub_types:
            if isinstance(sub_type, CStructType) \
                    and not sub_type.is_anonymous_struct():
                yield sub_type


def write_py2c_bridge(output:TextIO, cfuncs:Iterable[CFuncType]):
    output.write(
        'int _py2c_bridge_(int bridge_ndx, void (*func_ptr)(void), '
                        'unsigned char * params, unsigned char * retval)\n'
        '{\n'
        '\tswitch (bridge_ndx)\n'
        '\t{\n')
    bridge_ndxs = {}
    for cfunc in sorted(cfuncs, key=lambda cf:cf.sig_id):
        sig_id = cfunc.sig_id
        if sig_id not in bridge_ndxs:
            bridge_ndx = bridge_ndxs[sig_id] = len(bridge_ndxs)
            output.write('\tcase ' + str(bridge_ndx) + ':\n'
                         '\t{\n')
            write_params_ptrs(output, cfunc.args, indent='\t\t')
            output.write('\t\t')
            if cfunc.returns:
                c_def_retval = cfunc.returns.c_definition('*')
                output.write(f'*({c_def_retval}) retval = ')
            arg_list = ', '.join(map('*pp{}'.format, range(len(cfunc.args))))
            output.write(f'(* ({cfunc.c_definition("(*)")}) func_ptr)'
                                    f'({arg_list});\n')
            output.write('\t\treturn 1;\n'
                         '\t}\n')
    output.write(
        '\tdefault:\n'
        '\t\treturn 0;\n'
        '\t}\n'
        '}\n\n\n')
    return bridge_ndxs


def write_c2py_bridge(output:TextIO, required_funcptrs:Iterable[CFuncType],
                      max_instances:int):
    output.write(
        f'void (* _c2py_bridge_handler)(int bridge_ndx, int instance_ndx, '
                    f'unsigned char * params, unsigned char * retval) '
                    f'= (void *) 0;\n'
        f'\n')
    bridge_ndxs = {}
    bridge_ndx_ctr = itertools.count()
    for cfunc in required_funcptrs:
        sig_id = cfunc.sig_id
        if sig_id not in bridge_ndxs:
            bridge_ndx = next(bridge_ndx_ctr)
            bridge_ndxs[sig_id] = bridge_ndx
            for instance_ndx in range(max_instances):
                write_c2py_bridge_func(output, bridge_ndx, instance_ndx, cfunc)
    output.write(
        f'typedef void (* _c2py_bridge_func_t)(void);\n'
        f'_c2py_bridge_func_t _c2py_bridge_[][{max_instances}] = {{\n')
    for bridge_ndx in range(len(bridge_ndxs)):
        output.write('\t{ ')
        for instance_ndx in range(max_instances):
            output.write(f'(_c2py_bridge_func_t) '
                         f'_c2py_bridge_{bridge_ndx}_{instance_ndx}, ')
        output.write(' },\n')
    output.write('};\n\n')
    return bridge_ndxs



def write_c2py_bridge_func(output, bridge_ndx, instance_ndx, cfunc):
    bridge_func_name = f'_c2py_bridge_{bridge_ndx}_{instance_ndx}'
    output.write('static ' + cfunc.c_definition(bridge_func_name) + '\n')
    output.write('{\n')
    params_size = sum(a.sizeof for a in cfunc.args)
    output.write(f'\tunsigned char params[{params_size}];\n')
    write_params_ptrs(output, cfunc.args, indent='\t')
    if cfunc.returns is not None:
        output.write('\t' + cfunc.returns.c_definition('retval') + ';\n')
        retval_str = '(unsigned char *) &retval'
    else:
        retval_str = '(unsigned char *) 0'
    for arg_ndx in range(len(cfunc.args)):
        output.write(f'\t*pp{arg_ndx} = p{arg_ndx};\n')
    output.write(
        f'\t_c2py_bridge_handler({bridge_ndx}, {instance_ndx}, params, '
        f'{retval_str});\n')
    if cfunc.returns is not None:
        output.write('\treturn retval;\n')
    output.write('}\n\n')



def write_params_ptrs(output, args, indent=''):
    for arg_ndx, arg_ctype in enumerate(args):
        param_type = arg_ctype.ptr.c_definition()
        param_def =arg_ctype.ptr.with_attr('const').c_definition(f'pp{arg_ndx}')
        if arg_ndx == 0:
            output.write(f'{indent}{param_def} = ({param_type}) params;\n')
        else:
            output.write(f'{indent}{param_def} = ({param_type}) ('
                             f'pp{arg_ndx - 1} + 1);\n')
        prev_param_type = arg_ctype.c_definition()


def write_mock_defs(output:TextIO, mocks:Dict[str, CProxyType]):
    for mock_name, mock in sorted(mocks.items()):
        if not isinstance(mock, CFuncType):
            output.write(mock.c_definition(mock_name) + ';\n')
        else:
            output.write(mock.c_definition(f'(* {mock_name}_mock)') + ' = 0;\n')
            write_mock_redirect_func(output, mock, mock_name)
        output.write('\n')
    output.write('\n')


def write_mock_redirect_func(output, mock, name):
    output.write(mock.c_definition(name) + '\n')
    output.write('{\n')
    output.write('\treturn ' if mock.returns is not None else '\t')
    params = ', '.join(f'p{pndx}' for pndx in range(len(mock.args)))
    output.write(f'(* {name}_mock)({params});\n')
    output.write('}\n')



if __name__ == '__main__':
    import sys
    uint8_t = CIntType('uint8_t', 8, False, 'little')
    int32_t = CIntType('int32_t', 32, True, 'little')
    teststruct = CStructType('teststruct',
                             {'member1': uint8_t, 'member2':int32_t})
    functype = CFuncType(uint8_t.ptr,
                         [teststruct.ptr, int32_t, int32_t.array(3)])
    write_py2c_bridge(sys.stdout, [
        functype,
        CFuncType(None, [int32_t.ptr, teststruct])])
    write_c2py_bridge(sys.stdout, [
        functype,
        CFuncType(None, [int32_t.ptr, teststruct]),
        functype],
        2)