import os

input_file = 'clang_output.txt'
output_dir = 'split_functions'

# 创建输出目录
os.makedirs(output_dir, exist_ok=True)

with open(input_file, 'r', encoding='utf-8') as f:
    content = f.read()

# 按Function分割
functions = content.split('Function Name: ')[1:]  # 跳过开头的空白
print(functions)
for func in functions:
    lines = func.splitlines()
    func_name = lines[0].strip()
    # 合法文件名处理
    safe_func_name = func_name.replace('*', 'ptr').replace(' ', '_').replace('(', '').replace(')', '').replace(',', '')
    out_file = os.path.join(output_dir, f'{safe_func_name}.txt')
    with open(out_file, 'w', encoding='utf-8') as fout:
        fout.write('Function Name: ' + func)  # 保留原始开头
print(f"已保存 {len(functions)} 个函数文件到 {output_dir}/")
