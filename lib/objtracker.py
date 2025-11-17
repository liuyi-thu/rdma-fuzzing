import collections
import random
import string

# from .value import Value


class ObjectTracker:
    """
    RDMA对象生命周期与依赖管理器。
    支持PD、CQ、QP、MR、SRQ、MW、AH、DM、TD、XRC等资源。
    """

    SUPPORTED_TYPES = [
        "context",
        "pd",
        "cq",
        "qp",
        "mr",
        "srq",
        "mw",
        "ah",
        "dm",
        "td",
        "xrcd",
        "parent_pd",
        "wq",
        "channel",
        "cq_ex",
        "flow",
    ]

    def __init__(self):
        # 各类对象池，字典：类型->名字->属性字典
        self.objs = {typ: {} for typ in self.SUPPORTED_TYPES}
        self.counters = collections.defaultdict(int)  # 类型->下一个序号

    def alloc_name(self, typ):  # 手动编写trace时不用
        """自动分配唯一资源名"""
        n = self.counters[typ]
        self.counters[typ] += 1
        return f"{typ}{n}"

    def create(self, typ, name, **attrs):
        """登记一个对象为活跃状态，并可添加依赖关系属性"""
        if name in self.objs[typ]:
            raise ValueError(f"Object '{name}' of type '{typ}' already exists.")
        self.objs[typ][name] = {"alive": True, **attrs}

    def alloc(self, typ, name, **attrs):  # alias for create
        """分配并创建一个对象，等同于create"""
        self.create(typ, name, **attrs)

    def destroy(self, typ, name):
        """标记对象为已销毁"""
        if name in self.objs[typ]:
            self.objs[typ][name]["alive"] = False

    def is_alive(self, typ, name):
        return self.objs[typ].get(name, {}).get("alive", False)

    def all_alive(self, typ):
        """返回当前活跃的对象名列表"""
        return [k for k, v in self.objs[typ].items() if v.get("alive", False)]

    def all_objs(self, typ):
        """返回当前所有对象名列表（包括已销毁的）"""
        return list(self.objs[typ].keys())

    def get_attr(self, typ, name, attr):
        """获取对象某个属性（如所属pd/cq等）"""
        return self.objs[typ][name].get(attr, None)

    def set_attr(self, typ, name, attr, value):
        """为某对象设置属性"""
        if name in self.objs[typ]:
            self.objs[typ][name][attr] = value

    def find_by_attr(self, typ, attr, value):
        """查找指定属性等于某值的所有活跃对象名"""
        return [k for k, v in self.objs[typ].items() if v.get("alive", False) and v.get(attr, None) == value]

    def find_by_type(self, typ):
        """查找指定类型的所有活跃对象名"""
        return [k for k, v in self.objs[typ].items()]
        # return [
        #     k for k,v in self.objs[typ].items()
        #     if v.get('alive', False)
        # ]

    def get_dependencies(self, typ, name):
        """返回对象的所有属性（可用于依赖追溯/资源关系可视化）"""
        return self.objs[typ][name] if name in self.objs[typ] else {}

    def use(self, typ, name, **attrs):
        """标记对象为使用中（可用于资源分配/使用追踪）"""
        # if isinstance(name, Value):
        #     name = name.get_value()
        if name is None:
            # print(f"Warning: No object name specified for type '{typ}'. Skipping use operation.")
            return  # 如果没有指定对象名，则不进行任何操作
        if name not in self.objs[typ]:
            raise ValueError(f"Object '{name}' of type '{typ}' does not exist.")
        self.objs[typ][name]["used"] = True
        self.objs[typ][name].update(attrs)  # 更新其他属性

    def is_used(self, typ, name):
        """检查对象是否被使用"""
        return self.objs[typ].get(name, {}).get("used", False)

    def reset(self):
        """重置所有对象状态"""
        for typ in self.SUPPORTED_TYPES:
            self.objs[typ].clear()
        self.counters.clear()

    # def find_dependencies(self, typ, name): # type = 类型（如qp），name = 名称（如qp0） # 我依赖于谁
    #     """
    #     查找对象的所有依赖关系。
    #     返回一个字典，包含所有相关对象的类型和名称。
    #     """
    #     if name not in self.objs[typ]:
    #         return {}

    #     dependencies = {}
    #     for attr, value in self.objs[typ][name].items():
    #         if attr in self.SUPPORTED_TYPES and value in self.objs[attr]:
    #             dependencies[attr] = value
    #     return dependencies

    def find_dependents(self, typ, name):
        """
        查找所有依赖于指定对象(typ, name)的对象。
        返回一个列表，每个元素为(依赖类型, 依赖对象名)。
        """
        dependents = []
        for t in self.SUPPORTED_TYPES:
            for obj_name, attrs in self.objs[t].items():
                for attr, val in attrs.items():
                    if attr == typ and val == name:
                        dependents.append((t, obj_name))
        return dependents

    def random_name(self, typ):
        """生成一个随机的对象名"""
        return f"{typ}_{''.join(random.choices(string.ascii_letters + string.digits, k=8))}"

    def random_choose(self, typ, exclude=None):
        """随机选择一个活跃对象"""
        # alive_objs = self.all_alive(typ)
        # # print(alive_objs)
        # if exclude is not None:
        #     alive_objs = [obj for obj in alive_objs if obj != exclude]
        # if not alive_objs:
        #     return None
        # return random.choice(alive_objs)
        # 暂时去除alive
        objs = self.all_objs(typ)
        if exclude is not None:
            objs = [obj for obj in objs if obj != exclude]
        if not objs:
            return None
        return random.choice(objs)

    # 可以根据实际情况增加更多辅助函数


# 示例用法
if __name__ == "__main__":
    tracker = ObjectTracker()
    ctx = tracker.alloc_name("context")
    tracker.create("context", ctx)

    pd = tracker.alloc_name("pd")
    tracker.create("pd", pd, context=ctx)

    cq = tracker.alloc_name("cq")
    tracker.create("cq", cq, context=ctx)

    qp = tracker.alloc_name("qp")
    tracker.create("qp", qp, pd=pd, cq=cq)

    # 查询活跃PD
    print(tracker.all_alive("pd"))
    # 查询属于pd的所有QP
    print(tracker.find_by_attr("qp", "pd", pd))

    # 销毁pd
    tracker.destroy("pd", pd)
    print(tracker.is_alive("pd", pd))  # False

    # print(tracker.find_dependencies('qp', qp))  # {'pd': 'pd0', 'cq': 'cq0'}

    print(tracker.random_name("qp"))
    print(tracker.find_dependents("pd", pd))  # 查找依赖于pd的所有对象
    print(tracker.random_choose("qp"))  # 随机选择一个活跃的QP
