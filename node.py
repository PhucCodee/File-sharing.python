import os
import socket
import threading
import json
import time

from function import generate_file_hash, create_magnet_link

FORMAT = "utf-8"
SIZE = 1024 * 1024


class Node:
    def __init__(self, tracker_host, tracker_port):
        self.tracker_host = tracker_host
        self.tracker_port = tracker_port
        self.ip_address = self.get_ip_address()
        self.port = self.get_port()
        self.node_id = None
        self.file_directory = None
        self.running = True

    def get_ip_address(self):
        # Get the IP address of the current machine
        hostname = socket.gethostname()
        return socket.gethostbyname(hostname)

    def get_port(self):
        # Get an available port on the current machine
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.ip_address, 0))
            port = s.getsockname()[1]
        return port

    def send_request(self, data):
        # Send a JSON request to the tracker and return the response
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((self.tracker_host, self.tracker_port))
                s.sendall(json.dumps(data).encode(FORMAT))
                response = s.recv(SIZE)
                return json.loads(response.decode(FORMAT))
        except Exception as e:
            print(f"Error sending request: {e}")
            return {"status": "error", "message": str(e)}

    def send_node_request(self, data):
        # Send a JSON request to another node and return the response
        source_node_ip_address = data["source_node_ip_address"]
        source_node_port = data["source_node_port"]
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((source_node_ip_address, source_node_port))
                s.sendall(json.dumps(data).encode(FORMAT))
                response = s.recv(SIZE)
                return json.loads(response.decode(FORMAT))
        except Exception as e:
            print(f"Error sending request: {e}")
            return {"status": "error", "message": str(e)}

    def register_with_tracker(self):
        # Register the node with the tracker
        data = {
            "command": "register",
            "ip_address": self.ip_address,
            "port": self.port,
        }
        response = self.send_request(data)
        if response["status"] == "registered":
            self.node_id = response["node_id"]
            self.file_directory = os.path.join(
                os.path.dirname(__file__),
                f"node{self.node_id}",
            )
            os.makedirs(self.file_directory, exist_ok=True)
            print(f"\033[1;31mRegistered with tracker, node ID: {self.node_id}\033[0m")
        else:
            print("Failed to register with tracker:", response["message"])

    def node_start(self):
        # Start the node server to listen for incoming connections
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.ip_address, self.port))
            s.listen()
            print(f"\033[1;32mNode listening on [{self.ip_address}:{self.port}]\033[0m")
            s.settimeout(1)
            while self.running:
                try:
                    conn, addr = s.accept()
                    print("")
                    print(f"\033[1;36m[{addr}] connected\033[0m")
                    threading.Thread(
                        target=self.handle_node_request, args=(conn,)
                    ).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Error accepting connection: {e}")

    def handle_node_request(self, client_socket):
        # Handle incoming requests from other nodes
        try:
            data = client_socket.recv(SIZE).decode(FORMAT)
            if not data:
                print("Received empty data. Closing connection.")
                return

            request = json.loads(data)
            command = request.get("command")
            print(f"\033[1;33mReceived command: {command}\033[0m")

            if command == "upload_piece":
                self.receive_piece_upload(request, client_socket)
            elif command == "download_piece":
                self.send_piece(request, client_socket)
            else:
                response = {"status": "error", "message": "Unknown command"}
                client_socket.send(json.dumps(response).encode(FORMAT))
        except Exception as e:
            print(f"Error handling request: {e}")
        finally:
            self.display_interface()
            client_socket.close()

    def upload_file(self, file_path, file_name):
        # Upload a file by dividing it into pieces and sending to active nodes
        if not os.path.exists(file_path):
            print("File does not exist!")
            return
        if not os.path.isfile(file_path):
            print("File type is not valid!")
            return

        print(f"Node: {self.node_id}, port: {self.port}")
        print(f"Uploading file: {file_path}")

        file_hash = generate_file_hash(file_path)
        magnet_link = create_magnet_link(file_hash, file_name)
        pieces = self.divide_file(file_path)
        active_nodes = self.get_active_nodes()
        if not active_nodes:
            print("No active nodes available for file distribution.")
            return

        node_ids = list(active_nodes.keys())
        piece_distribution = {}

        for index, piece in enumerate(pieces):
            piece_distribution[index] = []

            target_node_id_1 = node_ids[index % len(node_ids)]
            target_node_1 = active_nodes[target_node_id_1]
            self.send_piece_upload(
                target_node_id_1, target_node_1, file_hash, index, piece
            )
            piece_distribution[index].append(target_node_id_1)

            target_node_id_2 = node_ids[(index + 1) % len(node_ids)]
            target_node_2 = active_nodes[target_node_id_2]
            self.send_piece_upload(
                target_node_id_2, target_node_2, file_hash, index, piece
            )
            piece_distribution[index].append(target_node_id_2)

        data = {
            "command": "upload",
            "node_id": self.node_id,
            "file_name": file_name,
            "file_hash": file_hash,
            "magnet_link": magnet_link,
            "total_pieces": len(pieces),
            "piece_distribution": piece_distribution,
        }
        response = self.send_request(data)
        if response["status"] == "uploaded":
            print(f"File {file_name} uploaded successfully.")
        else:
            print(f"Failed to upload file {file_name}: {response['message']}")

    def divide_file(self, file_path):
        # Divide the file into pieces of size SIZE
        file_size = os.path.getsize(file_path)
        num_pieces = (file_size + SIZE - 1) // SIZE
        pieces = [None] * num_pieces
        with open(file_path, "rb") as f:
            for i in range(num_pieces):
                pieces[i] = f.read(SIZE)
        return pieces

    def get_active_nodes(self):
        # Request the list of active nodes from the tracker
        data = {"command": "get_nodes"}
        response = self.send_request(data)
        if response["status"] == "success":
            return response["nodes"]
        else:
            print("Failed to get list of active nodes:", response["message"])
            return {}

    def send_piece_upload(
        self, target_node_id, target_node, file_hash, piece_index, piece
    ):
        # Send a file piece to another node
        data = {
            "command": "upload_piece",
            "node_id": target_node_id,
            "file_hash": file_hash,
            "piece_index": piece_index,
            "piece_data": piece.hex(),
        }
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((target_node["ip_address"], target_node["port"]))
                s.sendall(json.dumps(data).encode(FORMAT))

                response = b""
                while True:
                    chunk = s.recv(SIZE)
                    if not chunk:
                        break
                    response += chunk

                response_data = json.loads(response.decode(FORMAT))
                if response_data["status"] == "success":
                    print(f"Piece {piece_index} sent to node {target_node_id}")
                else:
                    print(
                        f"Failed to send piece {piece_index} to node {target_node_id}: {response_data['message']}"
                    )
        except Exception as e:
            print(f"Error sending piece {piece_index} to node {target_node_id}: {e}")

    def receive_piece_upload(self, request, client_socket):
        # Receive a file piece from another node and save it
        node_id = request["node_id"]
        file_hash = request["file_hash"]
        piece_index = request["piece_index"]
        piece_data = bytes.fromhex(request["piece_data"])

        pieces_directory = os.path.join(self.file_directory, file_hash)
        os.makedirs(pieces_directory, exist_ok=True)

        piece_path = os.path.join(pieces_directory, f"piece_{piece_index}")
        with open(piece_path, "wb") as piece_file:
            piece_file.write(piece_data)
        print(
            f"Node {node_id}: piece {piece_index} saved successfully in {pieces_directory}!"
        )

        response = {"status": "success"}
        client_socket.send(json.dumps(response).encode(FORMAT))

    def download_file(self, file_name):
        # Request to download a file
        data = {
            "command": "download",
            "file_name": file_name,
            "requester_id": self.node_id,
        }
        response = self.send_request(data)
        if response["status"] == "success":
            file_hash = response["file_hash"]
            total_pieces = response["total_pieces"]
            piece_distribution = response["piece_distribution"]
            active_nodes = self.get_active_nodes()
            print(f"Downloading file: {file_name}")

            save_location = os.path.join(self.file_directory, file_name)
            self.download_pieces(
                file_hash, total_pieces, piece_distribution, save_location, active_nodes
            )
        else:
            print(f"Failed to download file {file_name}: {response['message']}")

    def download_pieces(
        self, file_hash, total_pieces, piece_distribution, save_location, active_nodes
    ):
        # Download all pieces of a file from active nodes
        pieces = [None] * total_pieces
        for i in range(total_pieces):
            piece_data = None
            for node_id in piece_distribution[str(i)]:
                if node_id in active_nodes:
                    node_info = active_nodes[node_id]
                    piece_data = self.request_piece(
                        node_info["ip_address"], node_info["port"], file_hash, i
                    )
                    if piece_data:
                        break
            if piece_data:
                pieces[i] = piece_data
            else:
                print(f"Piece {i} not found or failed to download.")
                return

        with open(save_location, "wb") as output_file:
            for piece in pieces:
                output_file.write(piece)

        print(f"File downloaded successfully to {save_location}")

    def request_piece(self, target_ip, target_port, file_hash, piece_index):
        # Request a specific piece of a file from another node
        data = {
            "command": "download_piece",
            "file_hash": file_hash,
            "piece_index": piece_index,
        }
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((target_ip, target_port))
                s.sendall(json.dumps(data).encode(FORMAT))

                response = b""
                while True:
                    chunk = s.recv(SIZE)
                    if not chunk:
                        break
                    response += chunk

                response_data = json.loads(response.decode(FORMAT))
                if response_data["status"] == "success":
                    piece_data = bytes.fromhex(response_data["piece_data"])
                    return piece_data
                else:
                    print(f"Error: {response_data['message']}")
                    return None
        except Exception as e:
            print(
                f"Error requesting piece {piece_index} from {target_ip}:{target_port} - {e}"
            )
            return None

    def send_piece(self, request, client_socket):
        # Send a specific piece of a file to another node
        file_hash = request["file_hash"]
        piece_index = request["piece_index"]
        piece_path = os.path.join(
            self.file_directory, file_hash, f"piece_{piece_index}"
        )
        if os.path.exists(piece_path):
            with open(piece_path, "rb") as piece_file:
                piece_data = piece_file.read()
            response = {
                "status": "success",
                "piece_data": piece_data.hex(),
            }
        else:
            response = {"status": "error", "message": "Piece not found"}
        client_socket.send(json.dumps(response).encode(FORMAT))

    def disconnect(self):
        # Disconnect the node from the tracker
        data = {
            "command": "disconnect",
            "node_id": self.node_id,
        }
        self.send_request(data)

    def display_interface(self):
        print("\033[1;34m----------------------------\033[0m")
        print("\033[1;34m|   Choose an option       |\033[0m")
        print("\033[1;34m|  1. Upload file          |\033[0m")
        print("\033[1;34m|  2. Download file        |\033[0m")
        print("\033[1;34m|  3. Exit                 |\033[0m")
        print("\033[1;34m----------------------------\033[0m")
        print("\033[1;33mEnter option: \033[0m")

    def run(self):
        # Run the node and handle user input
        self.register_with_tracker()
        threading.Thread(target=self.node_start).start()
        time.sleep(1)
        try:
            while True:
                self.display_interface()
                choice = input()
                if choice == "1":
                    file_path = input(
                        "\033[1;33mEnter the path of the file to upload: \033[0m"
                    )
                    file_name = input(
                        "\033[1;33mEnter the name of the file to upload: \033[0m"
                    )
                    print(
                        "\033[1;34m-------------------------------------------\033[0m"
                    )
                    threading.Thread(
                        target=self.upload_file,
                        args=(file_path, file_name),
                    ).start()
                elif choice == "2":
                    file_name = input(
                        "\033[1;33mEnter the name of the file you want: \033[0m"
                    )
                    print(
                        "\033[1;34m-------------------------------------------\033[0m"
                    )
                    threading.Thread(
                        target=self.download_file,
                        args=(file_name,),
                    ).start()
                elif choice == "3":
                    print("\033[1;31mExiting...\033[0m")
                    self.running = False
                    self.disconnect()
                    break
                else:
                    print(
                        "\033[1;31mInvalid option. Please choose a valid option.\033[0m"
                    )
                time.sleep(2)
        finally:
            if self.running:
                self.disconnect()


if __name__ == "__main__":
    # print("192.168.2.5")
    # ip_address = input("Enter node ip address: ")
    # port = int(input("Enter node port: "))
    node = Node("192.168.2.5", 4000)
    node.run()
