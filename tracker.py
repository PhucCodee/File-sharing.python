import os
import socket
import threading
import json
import base64
import time

FORMAT = "utf-8"
SIZE = 8192
NODES_FILE = "nodes.json"


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
                print(f"[{addr}] connected")
                threading.Thread(target=self.handle_request, args=(conn,)).start()

    def handle_request(self, client_socket):
        """Handle incoming requests from clients (register, update, etc.)."""
        try:
            data = client_socket.recv(SIZE).decode(FORMAT)
            if not data:
                print("Received empty data. Closing connection.")
                return

            request = json.loads(data)
            command = request.get("command")
            print(f"Received command: {command}")

            if command == "register":
                self.register_node(request, client_socket)
            # elif command == "update":
            #     self.update_node(request, client_socket)
            # elif command == "query":
            #     self.query_file(request, client_socket)
            # elif command == "deregister":
            #     self.deregister_node(request, client_socket)
            elif command == "upload":
                self.upload_node(request, client_socket)
            elif command == "download":
                self.download_node(request, client_socket)
            else:
                response = {"error": "Unknown command"}
                client_socket.send(json.dumps(response).encode(FORMAT))
        except Exception as e:
            print(f"Error handling request: {e}")

    def register_node(self, request, client_socket):
        self.node_counter += 1
        node_id = self.node_counter
        self.nodes[node_id] = {
            "ip_address": request["ip_address"],
            "port": request["port"],
            "uploaded_file_list": request["uploaded_file_list"],
        }
        # self.save_nodes()
        response = {"status": "registered", "node_id": node_id}
        print(f"Registered node {node_id}")
        client_socket.send(json.dumps(response).encode(FORMAT))

    # def update_node(self, request, client_socket):
    #     node_id = request["node_id"]
    #     if node_id in self.nodes:
    #         self.nodes[node_id]["uploaded_file_list"] = request["uploaded_file_list"]
    #         response = {"status": "updated"}
    #         print(f"Updated node {node_id}")
    #     else:
    #         response = {"status": "error", "message": "Node ID not found"}
    #     client_socket.send(json.dumps(response).encode(FORMAT))

    # def query_file(self, request, client_socket):
    #     file_name = request["file_name"]
    #     nodes_with_file = [
    #         {"node_id": node_id, "ip_address": node["ip_address"], "port": node["port"]}
    #         for node_id, node in self.nodes.items()
    #         if file_name in node["uploaded_file_list"]
    #     ]
    #     response = {"status": "success", "nodes": nodes_with_file}
    #     client_socket.send(json.dumps(response).encode(FORMAT))

    # def deregister_node(self, request, client_socket):
    #     node_id = request["node_id"]
    #     if node_id in self.nodes:
    #         del self.nodes[node_id]
    #         response = {"status": "deregistered"}
    #         print(f"Deregistered node {node_id}")
    #     else:
    #         response = {"status": "error", "message": "Node ID not found"}
    #     client_socket.send(json.dumps(response).encode(FORMAT))

    def upload_node(self, request, client_socket):
        node_id = request["node_id"]
        file_name = request["file_name"]
        file_hash = request["file_hash"]
        magnet_link = request["magnet_link"]
        total_pieces = request["total_pieces"]

        if node_id in self.nodes:
            # Update the node's file list
            self.nodes[node_id]["uploaded_file_list"].append(file_name)

            tracker_directory = "tracker"
            if not os.path.exists(tracker_directory):
                os.makedirs(tracker_directory)

            # Update the file registry
            file_registry_path = os.path.join(tracker_directory, "file_registry.json")
            if os.path.exists(file_registry_path):
                with open(file_registry_path, "r") as f:
                    file_registry = json.load(f)
            else:
                file_registry = {}

            file_registry[file_name] = file_hash

            with open(file_registry_path, "w") as f:
                json.dump(file_registry, f)

            # Create metadata file for the uploaded file
            metadata = {
                "file_name": file_name,
                "file_hash": file_hash,
                "magnet_link": magnet_link,
                "total_pieces": total_pieces,
            }
            metadata_file_path = os.path.join(
                tracker_directory, f"{file_hash}_metadata.json"
            )
            with open(metadata_file_path, "w") as f:
                json.dump(metadata, f)

            response = {"status": "uploaded"}
            print(f"Node {node_id} uploaded file {file_name}")
        else:
            response = {"status": "error", "message": "Node ID not found"}

        client_socket.send(json.dumps(response).encode(FORMAT))

    def download_node(self, request, client_socket):
        file_name = request["file_name"]
        file_registry_path = os.path.join("tracker", "file_registry.json")

        if os.path.exists(file_registry_path):
            with open(file_registry_path, "r") as f:
                file_registry = json.load(f)
            file_hash = file_registry.get(file_name)
            if file_hash:
                metadata_file_path = os.path.join(
                    "tracker", f"{file_hash}_metadata.json"
                )
                if os.path.exists(metadata_file_path):
                    with open(metadata_file_path, "r") as f:
                        metadata = json.load(f)
                    response = {
                        "status": "success",
                        "file_hash": file_hash,
                        "magnet_link": metadata["magnet_link"],
                        "total_pieces": metadata["total_pieces"],
                    }
                else:
                    response = {"status": "error", "message": "Metadata file not found"}
            else:
                response = {"status": "error", "message": "File hash not found"}
        else:
            response = {"status": "error", "message": "File registry not found"}

        client_socket.send(json.dumps(response).encode(FORMAT))


if __name__ == "__main__":
    tracker = Tracker("127.0.0.1", 2901)
    tracker.start()
