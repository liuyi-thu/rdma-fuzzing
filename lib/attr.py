from typing import Dict, List

try:
    from .codegen_context import CodeGenContext
except ImportError:
    from codegen_context import CodeGenContext

try:
    from .contracts import Contract, InstantiatedContract
except ImportError:
    from contracts import Contract, InstantiatedContract

# ===== 在文件开头加一个全局开关和工具函数 =====
DEBUG = False  # 改成 True 就能打开所有调试信息


def debug_print(*args, **kwargs):
    """只在 DEBUG=True 时输出"""
    if DEBUG:
        print(*args, **kwargs)


class Attr:
    MUTABLE_FIELDS = []
    EXPORT_FIELDS = []

    def to_cxx(self, ctx: CodeGenContext) -> str:  # pylint: disable=unused-argument
        raise NotImplementedError

    def _contract(self):
        return Contract(
            requires=[],
            produces=[],
            transitions=[],
        )

    def get_contract(self):
        return self.CONTRACT if hasattr(self, "CONTRACT") else self._contract()

    def instantiate_contract(self):
        # print("why")
        """Instantiate the contract for this verb call."""
        # return InstantiatedContract.instantiate(self, self.get_contract())
        instantiate_contracts = [InstantiatedContract.instantiate(self, self.get_contract())]
        for field in getattr(self, "MUTABLE_FIELDS", []):
            # print(f"Checking field: {field}")
            if hasattr(self, field):
                # 递归调用
                c = getattr(self, field).instantiate_contract()
                if c:
                    instantiate_contracts.append(c)
        contract = InstantiatedContract.merge(instantiate_contracts)
        return contract

    def set_resource(self, res_type: str, old_res_name: str, new_res_name: str):
        """Set a resource for this verb call, used for replacing resources."""
        pass  # 有问题
        # if hasattr(self, 'tracker') and self.tracker:
        #     self.tracker.set_attr(res_type, old_res_name, 'name', new_res_name)
        #     # 更新已分配资源列表
        #     if hasattr(self, 'allocated_resources'):
        #         self.allocated_resources.append((res_type, new_res_name))

    def get_required_resources(self) -> List[Dict[str, str]]:
        """Get the list of required resources for this verb call."""
        if hasattr(self, "required_resources"):
            return self.required_resources
        return []

    def get_required_resources_recursively(self) -> List[Dict[str, str]]:
        """Get all required resources recursively."""
        resources = self.get_required_resources()
        # if hasattr(self, 'tracker') and self.tracker:
        #     for res in resources:
        #         # 如果资源是一个对象，递归获取其所需资源
        #         if hasattr(res, 'get_required_resources_recursively'):
        #             resources.extend(res.get_required_resources_recursively())
        return resources

    def set_resource(self, res_type: str, old_res_name: str, new_res_name: str):
        """Set a resource for this verb call, used for replacing resources."""
        for res in self.get_required_resources():
            if res.get("type") == res_type and res.get("name") == old_res_name:
                position = res.get("position", "unknown")  # 位置可能是 'cq', 'pd', 'qp' 等
                debug_print("Position:", position)
                if position == "unknown":
                    # 如果位置未知，可能是因为这个资源没有被追踪
                    # 这时我们可以选择忽略这个资源，或者抛出异常
                    raise ValueError(f"Resource {old_res_name} of type {res_type} has unknown position.")
                else:
                    setattr(self, position, new_res_name)  # 更新对应位置的资源名

    def set_resource_recursively(self, res_type: str, old_res_name: str, new_res_name: str):
        """Set a resource for this verb call, used for replacing resources."""
        self.set_resource(res_type, old_res_name, new_res_name)

    def mutate(self, snap, contract, rng, path):
        """Mutate the attributes of this object."""
        # 默认实现：不做任何变更
        # for field in self.MUTABLE_FIELDS:
        field = rng.choice(self.MUTABLE_FIELDS or [])

        if hasattr(self, field):
            value = getattr(self, field)
            if hasattr(value, "mutate"):
                sub_path = f"{path}.{field}" if path else field
                debug_print(f"Mutating field '{field}' with value: {value}")
                try:
                    value.mutate(snap=snap, contract=contract, rng=rng, path=sub_path)
                except TypeError:
                    # 兼容老 wrapper：回退一次（但会丢 path，尽量把 wrapper 也做成宽容签名）
                    value.mutate(snap, contract, rng)
        pass

    def is_none(self):
        """Check if this attribute is None."""
        # return all(getattr(self, field) is None for field in self.FIELD_LIST if hasattr(self, field))
        return False

    def to_dict(self):
        """Convert the verb call to a dictionary representation."""
        d = {"verb": self.__class__.__name__}
        # for field in self.FIELD_LIST:
        for field in self.EXPORT_FIELDS:
            if hasattr(self, field):
                value = getattr(self, field)
                if hasattr(value, "to_dict"):
                    d[field] = value.to_dict()
                else:
                    d[field] = value
        return d
