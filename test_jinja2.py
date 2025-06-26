from jinja2 import Environment, FileSystemLoader
import json

# # 加载 trace
# with open('trace.json') as f:
#     trace = json.load(f)

env = Environment(loader=FileSystemLoader('.'))
template = env.get_template('rdma_client_with_qp_pool.cpp.j2')
rendered = template.render(body='hello world')

with open('rdma_replay.cpp', 'w') as f:
    f.write(rendered)