# 最好写个simulator，模拟client和server的行为

import socket
import threading
import json
import time
import os

PORT = 12345
HOST = '0.0.0.0'

selected_server_qp_index = [2, 0, 1, 3]  # 用于server端的QP索引池

class Endpoint:
    def __init__(self, name):
        self.name = name
        self.global_meta = None  # 包含 lid, gid
        self.qps = []            # 每个包含 qpn, rkey, addr
        self.qpns = []          # 只包含 qpn
        self.ready = False  # 是否准备好接收数据
        self.disconnected = False  # 是否断开连接
        self.conn = None  # 用于存储连接对象

endpoints = {
    'server': Endpoint('server'),
    'client': Endpoint('client')
}
lock = threading.Lock()


def monitor_exit():
    while True:
        if endpoints['client'].disconnected and endpoints['server'].disconnected:
            print("[Controller] All connections closed. Exiting.")
            # sock.close()
            os._exit(0)
        time.sleep(1)
        
def handle_connection(conn, addr):
    print(f"[+] Connection from {addr}")
    buffer = b''
    role = None
    flag = True  # 用于控制循环

    while flag:
        data = conn.recv(4096)
        if not data:
            break
        buffer += data
        try:
            while b'\n' in buffer: # 是不是处理一次性多行
                line, buffer = buffer.split(b'\n', 1)
                # print(f"Received line: {line.decode()}")
                if not line.strip() or 'END' in line.decode():
                    flag = False
                    break
                obj = json.loads(line.decode())
                # print(obj)
                if obj['type'] == 'global_metadata': # the first message
                    if role is None:
                        role = obj.get('role')
                        print(f"[*] {role} connected")
                        endpoints[role].conn = conn
                    # if role is None:
                    #     role = 'server' if endpoints['server'].global_meta is None else 'client'
                    #     print(f"[*] {role} connected")
                    endpoints[role].global_meta = obj
                elif obj['type'] == 'qp_metadata':
                    endpoints[role].qps.append(obj)
                    if obj['qpn'] not in endpoints[role].qpns:
                        endpoints[role].qpns.append(obj['qpn'])
        except Exception as e:
            print("[!] Error parsing data:", e)
            break

    print(f"[Controller] {role} metadata received. Ready to proceed.")
    endpoints[role].ready = True

    if role == 'server': # 向服务器端发送数据
        while not endpoints['client'].ready:
            print("[*] Waiting for client to be ready...")
            threading.Event().wait(1)
        if endpoints['client'].global_meta:
            print("[*] Client is ready, sending data to server...")
            # send_all(conn, endpoints['client'])
            conn.sendall((json.dumps(endpoints['client'].global_meta) + '\n').encode()) # 向服务器发送客户端的一些信息
            # for i in range(len(selected_server_qp_index)):
            #     # qp_index = selected_server_qp_index[i]
            #     local_qpn = endpoints['server'].qpns[selected_server_qp_index[i]]
            #     remote_qpn = endpoints['client'].qpns[i]
            #     # print((json.dumps({'type': 'pair', 'qp_index': qp_index, 'qpn': qpn}) + '\n'))
            #     conn.sendall((json.dumps({'type': 'pair', 'local_qpn': local_qpn, 'remote_qpn': remote_qpn}) + '\n').encode())
            # 需要进行处理：只保留QPN，并进行排序
            conn.sendall('END\n'.encode())  # 发送结束标志

    elif role == 'client': # 向客户端发送数据
        while not endpoints['server'].ready:
            print("[*] Waiting for server to be ready...")
            threading.Event().wait(1)
        if endpoints['server'].global_meta:
            print("[*] Server is ready, sending data to client...")
            conn.sendall((json.dumps(endpoints['server'].global_meta) + '\n').encode()) # 向客户端发送服务器的一些信息

            for i in range(len(endpoints['server'].qps)):
                qp = endpoints['server'].qps[i] # 注意 QPN 可以重复，因为这里其实是每一个 MR
                conn.sendall((json.dumps({'type': 'mr_metadata', 'addr': qp['addr'], 'rkey': qp['rkey']}) + '\n').encode())
            conn.sendall('END\n'.encode())  # 发送结束标志
            # 这些都是固定信息

            print("[*] Entering pair request handling loop")
            while True: # 认为这是一个持久化的socket连接（暂定）
                req = conn.recv(4096)
                if not req:
                    break
                for line in req.split(b'\n'):
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line.decode())
                        if obj.get('type') == 'pair_request':
                            local_qpn = obj['local_qpn']
                            remote_index = obj['remote_qp_index']
                            if remote_index >= len(endpoints['server'].qpns):
                                continue
                            remote_qpn = endpoints['server'].qpns[remote_index]
                            pair_msg = json.dumps({
                                "type": "pair",
                                "local_qpn": local_qpn,
                                "remote_qpn": remote_qpn
                            }) + '\n'
                            conn.sendall(pair_msg.encode())
                            conn.sendall('END\n'.encode())  # 发送结束标志
                            if endpoints['server'].conn:
                                pair_msg_server = json.dumps({
                                "type": "pair",
                                "local_qpn": remote_qpn,
                                "remote_qpn": local_qpn
                                }) + '\n'
                                endpoints['server'].conn.sendall(pair_msg_server.encode())
                    except Exception as e:
                        print("[!] Error handling pair request:", e)

            # for i in range(len(selected_server_qp_index)):
            #     # qp_index = i
            #     # qpn = endpoints['server'].qpns[selected_server_qp_index[i]]
            #     local_qpn = endpoints['client'].qpns[i]
            #     remote_qpn = endpoints['server'].qpns[selected_server_qp_index[i]]
            #     conn.sendall((json.dumps({'type': 'pair', 'local_qpn': local_qpn, 'remote_qpn': remote_qpn}) + '\n').encode())
            # # send_all(conn, endpoints['server'])

            # # 还需要 MR 信息
            # for i in range(len(endpoints['server'].qps)):
            #     qp = endpoints['server'].qps[i] # 注意 QPN 可以重复，因为这里其实是每一个 MR
            #     conn.sendall((json.dumps({'type': 'mr_metadata', 'addr': qp['addr'], 'rkey': qp['rkey']}) + '\n').encode())
            # conn.sendall('END\n'.encode())  # 发送结束标志

    time.sleep(30)

    print(f"[-] Connection from {addr}, {role} closed")
    conn.close()
    
    if role == 'server':
        endpoints['server'].disconnected = True
    elif role == 'client':
        endpoints['client'].disconnected = True


def send_all(conn, endpoint):
    conn.sendall((json.dumps(endpoint.global_meta) + '\n').encode())
    for qp in endpoint.qps:
        conn.sendall((json.dumps(qp) + '\n').encode())


def main():
    print(f"[Controller] Listening on {HOST}:{PORT}")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((HOST, PORT))
    sock.listen(5)
    
    threading.Thread(target=monitor_exit, daemon=True).start()
    while True:
        conn, addr = sock.accept()
        threading.Thread(target=handle_connection, args=(conn, addr), daemon=True).start()


if __name__ == '__main__':
    main()
