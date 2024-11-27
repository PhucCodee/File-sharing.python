import os
import socket
import threading
import json
import base64
import time


class Tracker:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.nodes = {}  # Dictionary to store node information
        self.node_counter = 0  # Counter for auto-incrementing node IDs

    def start(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.host, self.port))
            s.listen()
            print(f"Tracker listening on {self.host}:{self.port}")
            while True:
                conn, addr = s.accept()
                threading.Thread(target=self.handle_node, args=(conn, addr)).start()

    def handle_node(self, conn, addr):
        with conn:
            print(f"Connected by {addr}")
            data = conn.recv(1024)
            if not data:
                return
            request = json.loads(data.decode("utf-8"))
            if "register" in request:
                self.node_counter += 1
                node_id = self.node_counter
                self.nodes[node_id] = {
                    "ip_address": request["ip_address"],
                    "port": request["port"],
                    "file_list": request["file_list"],
                }
                response = {"status": "registered", "node_id": node_id}
                print(f"Registered node {node_id} from {addr}")
            elif "update" in request:
                node_id = request["node_id"]
                if node_id in self.nodes:
                    self.nodes[node_id]["file_list"] = request["file_list"]
                    response = {"status": "updated"}
                    print(f"Updated node {node_id} from {addr}")
                else:
                    response = {"status": "error", "message": "Node ID not found"}
            else:
                response = {"status": "error", "message": "Invalid request"}
            conn.sendall(json.dumps(response).encode("utf-8"))


if __name__ == "__main__":
    tracker = Tracker("127.0.0.1", 2901)
    tracker.start()
