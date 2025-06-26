import os
from openai import OpenAI

client = OpenAI(
    # This is the default and can be omitted
    base_url="https://api.zeroai.link/v1",
    api_key="sk-G4uySLJ8u2jILK3f3aA3Df8e4bE444E682AbD29604F831Ca",
)

prompt_list = os.listdir('/home/liuyi/router-lab/fuzzing-rdma/rdma-fuzzing/prompts/')
func_list = [f.split('.')[0] for f in prompt_list if f.endswith('.prompt.txt')]
func_list.sort()
response_dir = '/home/liuyi/router-lab/fuzzing-rdma/rdma-fuzzing/responses/'
os.makedirs(response_dir, exist_ok=True)

for func in func_list:
    first_message = '我现在要对RDMA进行模糊测试。我想的做法是，RDMA协议中存在很多verbs，这个就像是TCP/IP协议中的syscalls一样，可以控制连接的建立、终止，数据包的发送等。我们以verbs为抓手，生成一系列verbs序列并执行，在客户端、服务器之间建立通信，观察是否会触发异常。这里借鉴syzkaller的思路，但是syzkaller的目标是syscalls，会生成syscalls序列，和verbs还不完全一样。同时，我们还会作为中间人去修改客户端、服务器之间通信的数据包，以触发更多可能的异常。之前和你讨论过这个idea，现在我正在编写 verbs replayer，能够根据一定的verbs序列来生成C代码并执行，这些是我目前的代码内容：'

    first_message += "verbs.py:" 
    with open("verbs.py", "r") as f:
        content = f.read()
        first_message += content
        first_message += "\n\n"

    first_message += "codegen_context.py:"
    with open("codegen_context.py", "r") as f:
        content = f.read()
        first_message += content
        first_message += "\n\n"
        
    first_message += "main.py:"
    with open("main.py", "r") as f:
        content = f.read()
        first_message += content
        first_message += "\n\n"
        
    # print(first_message)

    second_message = f'以上的文件里提供了很多写好的代码，可以为你接下来的任务提供参考。我现在想要生成一个{func}的prompt，能够生成{func}的C代码。请你帮我生成这个prompt。'
    with open(f'/home/liuyi/router-lab/fuzzing-rdma/rdma-fuzzing/prompts/{func}.prompt.txt', 'r') as f:
        prompt = f.read()
        second_message += prompt
    # print(second_message)

    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "你是一个代码助手"},
            {
                "role": "user",
                "content": first_message,
            },
            {
                "role": "user",
                "content": second_message,
            }
        ],
    )

    print(completion.choices[0].message.content)
    print(completion.usage.prompt_tokens)      # 提示词消耗token数
    print(completion.usage.completion_tokens)  # 回答消耗token数
    print(completion.usage.total_tokens)       # 总共消耗token数
    
    response = completion.choices[0].message.content
    with open(os.path.join(response_dir, f'{func}.response.txt'), 'w') as f:
        f.write(response)

    # response = client.responses.create(
    #     model="gpt-4o",
    #     instructions="You are a coding assistant that talks like a pirate.",
    #     input="How do I check if a Python object is an instance of a class?",
    # )

    # print(response)

    # print(response.output_text)