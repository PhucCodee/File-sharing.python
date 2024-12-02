import os
import socket
import threading
import json
import base64
import time

FORMAT = "utf-8"
SIZE = 524288
NODES_FILE = "nodes.json"
FILES_FILE = "files.json"


class Tracker:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.nodes = {}  # Dictionary to store node information
        self.node_counter = 0  # Counter for auto-incrementing node IDs
        self.running = True

    def start(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.host, self.port))
            s.listen()
            print(f"Tracker listening on {self.host}:{self.port}")
            # Set a timeout to periodically check the running flag
            s.settimeout(1)
            while self.running:
                try:
                    conn, addr = s.accept()
                    print(f"[{addr}] connected")
                    threading.Thread(target=self.handle_request, args=(conn,)).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Error accepting connection: {e}")

    def handle_request(self, client_socket):
        """Handle incoming requests from nodes."""
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
            elif command == "upload":
                self.upload_node(request, client_socket)
            elif command == "download":
                self.download_node(request, client_socket)
            else:
                response = {"error": "Unknown command"}
                client_socket.send(json.dumps(response).encode(FORMAT))
        except Exception as e:
            print(f"Error handling request: {e}")

    def load_json(self, path):
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
        return {}

    def save_json(self, path, data):
        with open(path, "w") as f:
            json.dump(data, f)

    def register_node(self, request, client_socket):
        self.node_counter += 1
        node_id = self.node_counter

        self.nodes[node_id] = {
            "ip_address": request["ip_address"],
            "port": request["port"],
            "file_list": request["file_list"],
        }

        tracker_directory = "tracker"
        os.makedirs(tracker_directory, exist_ok=True)

        node_registry_path = os.path.join(tracker_directory, NODES_FILE)
        node_registry = self.load_json(node_registry_path)

        node_registry[node_id] = {
            "ip_address": request["ip_address"],
            "port": request["port"],
            "file_list": request["file_list"],
        }

        self.save_json(node_registry_path, node_registry)

        response = {"status": "registered", "node_id": node_id}
        print(f"Registered node {node_id}")
        client_socket.send(json.dumps(response).encode(FORMAT))

    def upload_node(self, request, client_socket):
        node_id = request["node_id"]
        file_name = request["file_name"]
        file_hash = request["file_hash"]
        magnet_link = request["magnet_link"]
        total_pieces = request["total_pieces"]

        if node_id not in self.nodes:
            response = {"status": "error", "message": "Node ID not found"}
            client_socket.send(json.dumps(response).encode(FORMAT))
            return

        self.nodes[node_id]["file_list"].append(file_name)

        tracker_directory = "tracker"
        os.makedirs(tracker_directory, exist_ok=True)

        file_registry_path = os.path.join(tracker_directory, FILES_FILE)
        file_registry = self.load_json(file_registry_path)
        file_registry[file_name] = file_hash
        self.save_json(file_registry_path, file_registry)

        metadata = {
            "file_name": file_name,
            "file_hash": file_hash,
            "magnet_link": magnet_link,
            "total_pieces": total_pieces,
            "node_id": node_id,
        }
        metadata_file_path = os.path.join(
            tracker_directory, f"{file_hash}_metadata.json"
        )
        self.save_json(metadata_file_path, metadata)

        response = {"status": "uploaded"}
        print(f"Node {node_id} uploaded file {file_name}")
        client_socket.send(json.dumps(response).encode(FORMAT))

    def download_node(self, request, client_socket):
        file_name = request["file_name"]
        file_registry_path = os.path.join("tracker", FILES_FILE)
        node_registry_path = os.path.join("tracker", NODES_FILE)

        if not os.path.exists(file_registry_path):
            response = {"status": "error", "message": "File registry not found"}
            client_socket.send(json.dumps(response).encode(FORMAT))
            return

        if not os.path.exists(node_registry_path):
            response = {"status": "error", "message": "Node registry not found"}
            client_socket.send(json.dumps(response).encode(FORMAT))
            return

        # Load the file registry
        file_registry = self.load_json(file_registry_path)

        # Get the file hash from the file registry
        file_hash = file_registry.get(file_name)
        if not file_hash:
            response = {"status": "error", "message": "File hash not found"}
            client_socket.send(json.dumps(response).encode(FORMAT))
            return

        # Load the metadata file
        metadata_file_path = os.path.join("tracker", f"{file_hash}_metadata.json")
        metadata = self.load_json(metadata_file_path)
        if not metadata:
            response = {"status": "error", "message": "Metadata file not found"}
            client_socket.send(json.dumps(response).encode(FORMAT))
            return

        # Load the node registry
        node_registry = self.load_json(node_registry_path)

        # Get the source node information
        source_node = node_registry.get(str(metadata["node_id"]))
        if not source_node:
            response = {"status": "error", "message": "Source node not found"}
            client_socket.send(json.dumps(response).encode(FORMAT))
            return

        # Prepare the response
        response = {
            "status": "success",
            "file_hash": file_hash,
            "magnet_link": metadata["magnet_link"],
            "total_pieces": metadata["total_pieces"],
            "node_id": metadata["node_id"],
            "ip_address": source_node["ip_address"],
            "port": source_node["port"],
        }
        requester_id = request["requester_id"]
        print(f"Node {requester_id} downloaded file {file_name}")

        client_socket.send(json.dumps(response).encode(FORMAT))


if __name__ == "__main__":
    tracker = Tracker("10.128.86.17", 3000)
    # tracker = Tracker("14.241.225.112", 3000)

    # Start the tracker in a separate thread
    threading.Thread(target=tracker.start).start()
    time.sleep(1)
    print("Press enter to terminate!")
    while True:
        command = input("")
        if command == "":
            print("Exiting...")
            tracker.running = False
            break
