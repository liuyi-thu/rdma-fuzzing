import importlib
import inspect
import os

VERBS_MODULE = os.environ.get("VERBS_MODULE", "lib.verbs")
verbs = importlib.import_module(VERBS_MODULE)

# --- Test Helpers ---


class FakeTracker:
    def __init__(self):
        self.calls = []

    def use(self, typ, name):
        self.calls.append(("use", typ, name))

    def create(self, typ, name, **kwargs):
        self.calls.append(("create", typ, name, kwargs))

    def destroy(self, typ, name):
        self.calls.append(("destroy", typ, name))


class FakeCtx:
    def __init__(self, ib_ctx="ctx"):
        self.tracker = FakeTracker()
        self.ib_ctx = ib_ctx
        self._vars = []

    def alloc_variable(self, name, ty):
        self._vars.append((name, ty))


def assert_contains(s, token):
    assert token in s, f"expected {token!r} in generated code, got:\\n{s}"


def generic_mutate(obj):
    """
    Attempt to mutate a parameter wrapper or raw value.
    Strategy order:
      1) If obj has .mutate(), call it in-place.
      2) If type(obj) has classmethod random_mutation(), replace with that.
      3) If obj has .value (typical Value wrapper):
          - If .value is int/str, tweak in-place if allowed, else replace.
          - If .value is list and obj has .factory, append a new factory() item.
      4) If obj is raw int/str, tweak directly.
    Return the possibly replaced object (so caller can re-assign the field).
    """
    # 1) In-place mutate if available
    if hasattr(obj, "mutate") and callable(getattr(obj, "mutate")):
        try:
            obj.mutate()
            return obj
        except Exception:
            pass

    # 2) class-level random mutation
    rand_mut = getattr(type(obj), "random_mutation", None)
    if callable(rand_mut):
        try:
            return rand_mut()
        except Exception:
            pass

    # 3) Try .value/.factory pattern
    if hasattr(obj, "value"):
        val = getattr(obj, "value")
        # ints
        if isinstance(val, int):
            try:
                setattr(obj, "value", val + 1 if val < 2**31 - 2 else val - 1)
                return obj
            except Exception:
                # replace whole object if fails
                try:
                    return type(obj)(val + 1)
                except Exception:
                    pass
        # strings
        if isinstance(val, str):
            try:
                setattr(obj, "value", val + "_m")
                return obj
            except Exception:
                try:
                    return type(obj)(val + "_m")
                except Exception:
                    pass
        # lists
        if isinstance(val, (list, tuple)):
            fac = getattr(obj, "factory", None)
            if callable(fac):
                try:
                    val2 = list(val)
                    val2.append(fac())
                    setattr(obj, "value", val2)
                    return obj
                except Exception:
                    pass

    # 4) raw primitives
    if isinstance(obj, int):
        return obj + 1
    if isinstance(obj, str):
        return obj + "_m"

    # fallback: return as-is
    return obj


# --- Mutation tests for representative verbs ---


def _mutate_all_fields(verb):
    mp = verb.get_mutable_params()
    for k, v in mp.items():
        mutated = generic_mutate(v)
        try:
            setattr(verb, k, mutated)
        except Exception:
            # If direct setattr fails (some wrappers may require .value set only),
            # try to write into .value where possible.
            if hasattr(getattr(verb, k), "value") and hasattr(mutated, "value"):
                getattr(verb, k).value = mutated.value


def test_mutation_advise_mr_smoke():
    ctx = FakeCtx()
    v = verbs.AdviseMR(pd="pd0", advice=1, flags=0, sg_list=[], num_sge=1)
    v.apply(ctx)
    _mutate_all_fields(v)
    code = v.generate_c(ctx)
    assert_contains(code, "ibv_advise_mr")


def test_mutation_reg_mr_smoke():
    ctx = FakeCtx()
    v = verbs.RegMR(pd="pd0", mr="mr0", addr="addr", length=64, access="IBV_ACCESS_LOCAL_WRITE")
    v.apply(ctx)
    _mutate_all_fields(v)
    code = v.generate_c(ctx)
    assert_contains(code, "ibv_reg_mr")


def test_mutation_create_cq_smoke():
    ctx = FakeCtx()
    v = verbs.CreateCQ(cq="cq0", cqe=8, comp_vector=0)
    v.apply(ctx)
    _mutate_all_fields(v)
    code = v.generate_c(ctx)
    assert_contains(code, "ibv_create_cq")
