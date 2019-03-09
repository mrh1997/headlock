from .integer import CIntType, CInt


class CEnumType(CIntType):
    """This is a dummy implemenetation to make enums parsable"""

    def __init__(self, name=None):
        super().__init__(name or '', 32, False, 'little')

    def c_definition(self, refering_def=''):
        return 'enum ' + self.c_name \
               + (' '+refering_def if refering_def else '')

CEnum = CInt
