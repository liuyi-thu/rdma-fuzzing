import socket
import threading
import json

if __name__ == '__main__':
    message_list = [
        '{"type": "global_metadata", "lid":0, "role": "server", "gid":"00:00:00:00:00:00:00:00:00:00:ff:ff:c0:a8:38:0a"}',
        '{"type": "qp_metadata","qpn":99164,"addr":93924665998624,"rkey":234723}',
        '{"type": "qp_metadata","qpn":99165,"addr":93924665998625,"rkey":234724}',
        '{"type": "qp_metadata","qpn":99166,"addr":93924665998625,"rkey":234724}'
    ]

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('127.0.0.1', 12345))
    for message in message_list:
        sock.sendall((message + '\n').encode())
    sock.sendall(b'\n')  # 发送一个空行表示结束
    while True:
        data = sock.recv(4096)
        # print("raw data:", data)
        if not data:
            break
        print(data.decode().strip())
    sock.close()
