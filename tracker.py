import os
import socket
import threading
import json
import time

FORMAT = "utf-8"
SIZE = 1024 * 1024
NODES_FILE = "nodes.json"
FILES_FILE = "files.json"


class Tracker:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.nodes = {}
        self.node_counter = 0
        self.running = True

    def start(self):
        # Start the tracker server to listen for incoming connections
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.host, self.port))
            s.listen()
            print(f"\033[1;32mTracker listening on [{self.host}:{self.port}]\033[0m")
            s.settimeout(1)
            while self.running:
                try:
                    conn, addr = s.accept()
                    print(f"\033[1;36m[{addr}] connected\033[0m")
                    threading.Thread(target=self.handle_request, args=(conn,)).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Error accepting connection: {e}")

    def handle_request(self, client_socket):
        # Handle incoming requests from nodes
        try:
            data = client_socket.recv(SIZE).decode(FORMAT)
            if not data:
                print("Received empty data. Closing connection.")
                return

            request = json.loads(data)
            command = request.get("command")
            if command != "get_nodes":
                print(f"\033[1;33mReceived command: {command}\033[0m")

            if command == "register":
                self.register_node(request, client_socket)
            elif command == "upload":
                self.upload_node(request, client_socket)
            elif command == "download":
                self.download_node(request, client_socket)
            elif command == "disconnect":
                self.disconnect_node(request, client_socket)
            elif command == "get_nodes":
                self.get_nodes(request, client_socket)
            else:
                response = {"error": "Unknown command"}
                client_socket.send(json.dumps(response).encode(FORMAT))
        except Exception as e:
            print(f"Error handling request: {e}")

    def load_json(self, path):
        # Load JSON data from a file
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
        return {}

    def save_json(self, path, data):
        # Save JSON data to a file
        with open(path, "w") as f:
            json.dump(data, f)

    def register_node(self, request, client_socket):
        # Register a new node with the tracker
        self.node_counter += 1
        node_id = self.node_counter

        self.nodes[node_id] = {
            "ip_address": request["ip_address"],
            "port": request["port"],
        }

        tracker_directory = "tracker"
        os.makedirs(tracker_directory, exist_ok=True)

        node_registry_path = os.path.join(tracker_directory, NODES_FILE)
        node_registry = self.load_json(node_registry_path)

        node_registry[node_id] = {
            "ip_address": request["ip_address"],
            "port": request["port"],
        }

        self.save_json(node_registry_path, node_registry)

        response = {"status": "registered", "node_id": node_id}
        print(f"Registered node {node_id}")
        client_socket.send(json.dumps(response).encode(FORMAT))

    def upload_node(self, request, client_socket):
        # Handle file upload from a node
        node_id = request["node_id"]
        file_name = request["file_name"]
        file_hash = request["file_hash"]
        magnet_link = request["magnet_link"]
        total_pieces = request["total_pieces"]
        piece_distribution = request["piece_distribution"]

        if node_id not in self.nodes:
            response = {"status": "error", "message": "Node ID not found"}
            client_socket.send(json.dumps(response).encode(FORMAT))
            return

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
            "piece_distribution": piece_distribution,
        }
        metadata_file_path = os.path.join(
            tracker_directory, f"{file_hash}_metadata.json"
        )
        self.save_json(metadata_file_path, metadata)

        response = {"status": "uploaded"}
        print(f"Node {node_id} uploaded file {file_name}")
        client_socket.send(json.dumps(response).encode(FORMAT))

    def download_node(self, request, client_socket):
        # Handle file download request from a node
        file_name = request["file_name"]
        file_registry_path = os.path.join("tracker", FILES_FILE)

        if not os.path.exists(file_registry_path):
            response = {"status": "error", "message": "File registry not found"}
            client_socket.send(json.dumps(response).encode(FORMAT))
            return

        file_registry = self.load_json(file_registry_path)

        file_hash = file_registry.get(file_name)
        if not file_hash:
            response = {"status": "error", "message": "File hash not found"}
            client_socket.send(json.dumps(response).encode(FORMAT))
            return

        metadata_file_path = os.path.join("tracker", f"{file_hash}_metadata.json")
        metadata = self.load_json(metadata_file_path)
        if not metadata:
            response = {"status": "error", "message": "Metadata file not found"}
            client_socket.send(json.dumps(response).encode(FORMAT))
            return

        response = {
            "status": "success",
            "file_hash": file_hash,
            "magnet_link": metadata["magnet_link"],
            "total_pieces": metadata["total_pieces"],
            "piece_distribution": metadata["piece_distribution"],
        }
        requester_id = request["requester_id"]
        print(f"Node {requester_id} downloaded file {file_name}")

        client_socket.send(json.dumps(response).encode(FORMAT))

    def disconnect_node(self, request, client_socket):
        # Handle node disconnection
        node_id = request["node_id"]
        if node_id in self.nodes:
            del self.nodes[node_id]
            print(f"\033[1;31mNode {node_id} disconnected\033[0m")

            tracker_directory = "tracker"
            node_registry_path = os.path.join(tracker_directory, NODES_FILE)
            node_registry = self.load_json(node_registry_path)

            if str(node_id) in node_registry:
                del node_registry[str(node_id)]
                self.save_json(node_registry_path, node_registry)

        response = {"status": "disconnected"}
        client_socket.send(json.dumps(response).encode(FORMAT))

    def get_nodes(self, request, client_socket):
        # Provide the list of active nodes
        node_registry_path = os.path.join("tracker", NODES_FILE)
        node_registry = self.load_json(node_registry_path)
        response = {"status": "success", "nodes": node_registry}
        client_socket.send(json.dumps(response).encode(FORMAT))


if __name__ == "__main__":
    # print("192.168.2.5")
    # ip_address = input("Enter tracker ip address: ")
    # port = int(input("Enter tracker port: "))
    tracker = Tracker("192.168.2.5", 4000)

    print("\033[1;31mPRESS ENTER TO TERMINATE!\033[0m")
    threading.Thread(target=tracker.start).start()
    time.sleep(1)
    while True:
        command = input("")
        if command == "":
            print("Exiting...")
            tracker.running = False
            break
