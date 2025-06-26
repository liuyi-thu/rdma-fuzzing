import os
import re

input_dir = "/home/liuyi/router-lab/fuzzing-rdma/rdma-fuzzing/responses"  # 比如: "./txts"
output_file = "merged_code.py"

all_code = []

for fname in sorted(os.listdir(input_dir)):
    if not fname.endswith(".txt"):
        continue
    with open(os.path.join(input_dir, fname), encoding="utf-8") as f:
        content = f.read()
        # 用正则匹配所有```python ... ``` 之间的内容
        matches = re.findall(r"```python(.*?)```", content, re.DOTALL)
        for m in matches:
            # 去除前后空行
            code = m.strip()
            all_code.append(code)

with open(output_file, "w", encoding="utf-8") as out:
    for code in all_code:
        out.write(code)
        out.write("\n\n")  # 代码之间用空行分隔

print(f"合并完成，所有代码已写入 {output_file}")
