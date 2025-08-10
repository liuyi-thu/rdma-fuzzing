
from typing import List, Dict
from .codegen_context import CodeGenContext

class Attr:
    def to_cxx(self, ctx: CodeGenContext) -> str:  # pylint: disable=unused-argument
        raise NotImplementedError
    
    def set_resource(self, res_type: str, old_res_name: str, new_res_name: str):
        """Set a resource for this verb call, used for replacing resources."""
        pass # 有问题
        # if hasattr(self, 'tracker') and self.tracker:
        #     self.tracker.set_attr(res_type, old_res_name, 'name', new_res_name)
        #     # 更新已分配资源列表
        #     if hasattr(self, 'allocated_resources'):
        #         self.allocated_resources.append((res_type, new_res_name))

    def get_required_resources(self) -> List[Dict[str, str]]:
        """Get the list of required resources for this verb call."""
        if hasattr(self, 'required_resources'):
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
            if res.get('type') == res_type and res.get('name') == old_res_name:
                position = res.get('position', 'unknown')  # 位置可能是 'cq', 'pd', 'qp' 等
                print("Position:", position)
                if position == 'unknown':
                    # 如果位置未知，可能是因为这个资源没有被追踪
                    # 这时我们可以选择忽略这个资源，或者抛出异常
                    raise ValueError(f"Resource {old_res_name} of type {res_type} has unknown position.")
                else:
                    setattr(self, position, new_res_name)  # 更新对应位置的资源名
        
    
    def set_resource_recursively(self, res_type: str, old_res_name: str, new_res_name: str):
        """Set a resource for this verb call, used for replacing resources."""
        self.set_resource(res_type, old_res_name, new_res_name)