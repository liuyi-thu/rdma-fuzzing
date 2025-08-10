import re

def replace_required_resources(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        code = f.read()

    # 支持空格、单引号、双引号、变量等简单情况
    pattern = re.compile(
        r"self\.required_resources\.append\(\(\s*([\"']?)(\w+)\1\s*,\s*self\.(\w+)\s*\)\)"
    )

    def repl(match):
        type_str = match.group(2)
        var_name = match.group(3)
        # position就是变量名
        return f"self.required_resources.append({{'type': '{type_str}', 'name': self.{var_name}, 'position': '{var_name}'}})"

    code_new = pattern.sub(repl, code)

    with open(filename + 'new.py', 'w', encoding='utf-8') as f:
        f.write(code_new)

# 用法
replace_required_resources('verbs.py')