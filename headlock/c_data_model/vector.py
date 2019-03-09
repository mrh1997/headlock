from .integer import CIntType, CInt


class CVectorType(CIntType):
    """This is a dummy yet"""

    name = 'vector'

    def __init__(self, name=None):
        super().__init__(name or '', 32, False, 'little')

CVector = CInt
