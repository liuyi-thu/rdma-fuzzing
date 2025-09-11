import os
import re

def process_ibv_py_file(filepath):
    with open(filepath, encoding='utf-8') as f:
        code = f.read()

    # 1. 插入import
    if "from .attr import Attr" not in code:
        code = "from .attr import Attr\n" + code

    # 2. 替换class定义（支持单行和多基类情况）
    def replace_class(match):
        class_name = match.group(1)
        bases = match.group(2)
        if not bases:
            return f"class {class_name}(Attr):"
        else:
            # 可能已包含Attr基类（防重复），如果没有就加
            base_list = [b.strip() for b in bases[1:-1].split(',') if b.strip()]
            if 'Attr' not in base_list:
                base_list = ['Attr'] + base_list
            bases_new = '(' + ', '.join(base_list) + ')'
            return f"class {class_name}{bases_new}:"

    class_pattern = re.compile(r'class\s+(\w+)\s*(\([^\)]*\))?:')
    code = class_pattern.sub(replace_class, code)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(code)

# 遍历所有Ibv*.py文件
for fn in os.listdir('.'):
    if fn.startswith('Ibv') and fn.endswith('.py'):
        process_ibv_py_file(fn)
        print(f"Processed {fn}")
