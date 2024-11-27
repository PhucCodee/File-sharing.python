import os
import socket
import threading
import json
import base64
import time


class Node:
    def __init__(self, tracker_host, tracker_port):
        self.tracker_host = tracker_host
        self.tracker_port = tracker_port
        self.node_id = None  # Node ID will be assigned by the tracker
        self.ip_address = self.get_ip_address()
        self.port = self.get_port()
        self.shared_directory = os.path.join(os.path.dirname(__file__), "shared")
        if not os.path.exists(self.shared_directory):
            os.makedirs(self.shared_directory)
        self.file_list = self.get_shared_files()
        self.neighbor_nodes = []
        self.download_stats = {}
        self.upload_stats = {}

    def get_ip_address(self):
        # Get the IP address of the node
        hostname = socket.gethostname()
        return socket.gethostbyname(hostname)

    def get_port(self):
        # Create a socket and bind it to an available port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))  # Bind to an available port
            port = s.getsockname()[1]  # Retrieve the assigned port number
        return port

    def get_shared_files(self):
        # Get the list of files in the shared directory
        return os.listdir(self.shared_directory)

    def register_with_tracker(self):
        # Register the node with the tracker server
        data = {
            "register": True,
            "ip_address": self.ip_address,
            "port": self.port,
            "file_list": self.file_list,
        }
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((self.tracker_host, self.tracker_port))
            s.sendall(json.dumps(data).encode("utf-8"))
            response = s.recv(1024)
            response_data = json.loads(response.decode("utf-8"))
            if response_data["status"] == "registered":
                self.node_id = response_data["node_id"]
                print(f"Registered with tracker, node ID: {self.node_id}")
            else:
                print("Failed to register with tracker:", response_data["message"])

    def update_tracker(self):
        # Update the tracker with the current file list
        data = {
            "update": True,
            "node_id": self.node_id,
            "file_list": self.file_list,
        }
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((self.tracker_host, self.tracker_port))
            s.sendall(json.dumps(data).encode("utf-8"))
            response = s.recv(1024)
            response_data = json.loads(response.decode("utf-8"))
            if response_data["status"] == "updated":
                print("Updated tracker")
            else:
                print("Failed to update tracker:", response_data["message"])

    def run(self):
        while True:
            print(f"Welcome node {self.node_id}")
            command = input("Enter command: ")


if __name__ == "__main__":
    # Example usage
    node = Node("127.0.0.1", 2901)
    node.register_with_tracker()
    node.run()
