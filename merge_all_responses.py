import os

response_list = os.listdir('/home/liuyi/router-lab/fuzzing-rdma/rdma-fuzzing/responses/')
response_list = [f for f in response_list if f.endswith('.response.txt')]
response_list.sort()

output_file = '/home/liuyi/router-lab/fuzzing-rdma/rdma-fuzzing/merged_responses.txt'

with open(output_file, 'w') as outfile:
    for response_file in response_list:
        with open(os.path.join('/home/liuyi/router-lab/fuzzing-rdma/rdma-fuzzing/responses/', response_file), 'r') as infile:
            content = infile.read()
            # outfile.write(f'--- {response_file} ---\n')
            func_name = response_file.replace('.response.txt', '')
            outfile.write(f'--- Function: {func_name} ---\n')
            outfile.write(content + '\n\n')