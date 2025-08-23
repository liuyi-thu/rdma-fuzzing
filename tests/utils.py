class _DummyContracts:
    def apply_contract(self, verb, contract):
        pass

    def snapshot(self):
        return {}


class FakeCtx:
    def __init__(self):
        self.vars = {}
        self.tracker = None
        self.contracts = _DummyContracts()
        self.ib_ctx = "ctx"

    def alloc_variable(self, name, ctype, init=None):
        self.vars[name] = (ctype, init)
