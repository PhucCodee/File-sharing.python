import os
import socket
import threading
import json
import base64
import time

from function import generate_file_hash, create_magnet_link

FORMAT = "utf-8"
SIZE = 524288


class Node:
    def __init__(self, tracker_host, tracker_port):
        self.tracker_host = tracker_host
        self.tracker_port = tracker_port
        self.ip_address = self.get_ip_address()
        self.port = self.get_port()
        self.node_id = None  # Node ID will be assigned by the tracker
        self.file_directory = None  # Will be set after registration
        self.file_list = self.get_files()
        self.running = True

    def get_ip_address(self):
        hostname = socket.gethostname()
        return socket.gethostbyname(hostname)

    def get_port(self):
        # Create a socket and bind it to an available port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.ip_address, 0))
            port = s.getsockname()[1]
        return port

    def get_files(self):
        if self.file_directory and os.path.exists(self.file_directory):
            return os.listdir(self.file_directory)
        return []

    def send_request(self, data):
        """Send a JSON request to the tracker and return the response."""
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
        """Send a JSON request to another node and return the response."""
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
        data = {
            "command": "register",
            "ip_address": self.ip_address,
            "port": self.port,
            "file_list": self.file_list,
        }
        response = self.send_request(data)
        if response["status"] == "registered":
            self.node_id = response["node_id"]

            # Create a unique directory for the node
            self.file_directory = os.path.join(
                os.path.dirname(__file__),
                "node",
            )
            os.makedirs(self.file_directory, exist_ok=True)
            self.file_list = self.get_files()

            print(f"Registered with tracker, node ID: {self.node_id}")
        else:
            print("Failed to register with tracker:", response["message"])

    def node_start(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.ip_address, self.port))
            s.listen()
            print(f"Node listening on {self.ip_address}:{self.port}")
            # Set a timeout to periodically check the running flag
            s.settimeout(1)
            while self.running:
                try:
                    conn, addr = s.accept()
                    print(f"[{addr}] connected")
                    threading.Thread(
                        target=self.handle_node_request, args=(conn,)
                    ).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"Error accepting connection: {e}")

    def handle_node_request(self, client_socket):
        """Handle incoming requests from other nodes."""
        try:
            data = client_socket.recv(SIZE).decode(FORMAT)
            if not data:
                print("Received empty data. Closing connection.")
                return

            request = json.loads(data)
            command = request.get("command")
            print(f"Received command: {command}")

            if command == "download_piece":
                self.send_piece(request, client_socket)
            else:
                response = {"error": "Unknown command"}
                client_socket.send(json.dumps(response).encode(FORMAT))
        except Exception as e:
            print(f"Error handling request: {e}")
        finally:
            client_socket.close()

    # Uploading file
    def upload_file(self, file_path, file_name):
        if not os.path.exists(file_path):
            print("File does not exist!")
        if not os.path.isfile(file_path):
            print("File type is not valid!")

        print(f"Uploading file: {file_path}")

        file_hash = generate_file_hash(file_path)
        magnet_link = create_magnet_link(file_hash, file_name)
        pieces = self.divide_file(file_path)

        self.save_pieces(file_hash, pieces)

        self.file_list.append(file_name)
        data = {
            "command": "upload",
            "node_id": self.node_id,
            "file_name": file_name,
            "file_hash": file_hash,
            "magnet_link": magnet_link,
            "total_pieces": len(pieces),
            "file_list": self.file_list,
        }
        response = self.send_request(data)
        if response["status"] == "uploaded":
            print(f"File {file_name} uploaded successfully.")
        else:
            print(f"Failed to upload file {file_name}: {response['message']}")

        print(f"Node: {self.node_id}, port: {self.port}")

    def divide_file(self, file_path):
        pieces = []
        with open(file_path, "rb") as f:
            chunk_number = 0
            while chunk := f.read(SIZE):
                pieces.append((chunk_number, chunk))
                chunk_number += 1
        return pieces

    def save_pieces(self, file_hash, pieces):
        pieces_directory = os.path.join(self.file_directory, file_hash)
        os.makedirs(pieces_directory, exist_ok=True)

        for index, piece in pieces:
            piece_path = os.path.join(pieces_directory, f"piece_{index}")
            with open(piece_path, "wb") as piece_file:
                piece_file.write(piece)
            print(f"Piece {index} saved successfully!")

    # Downloading file
    def download_file(self, file_name):
        data = {
            "command": "download",
            "file_name": file_name,
            "requester_id": self.node_id,
        }
        response = self.send_request(data)
        if response["status"] == "success":
            file_hash = response["file_hash"]
            total_pieces = response["total_pieces"]
            source_node_ip_address = response["ip_address"]
            source_node_port = response["port"]

            print(f"Source node: {
                  source_node_ip_address} - {source_node_port}")

            save_location = os.path.join(self.file_directory, file_name)
            self.download_pieces(
                file_hash,
                total_pieces,
                source_node_ip_address,
                source_node_port,
                save_location,
            )
        else:
            print(f"Failed to download file {
                  file_name}: {response['message']}")

        print(f"Node: {self.node_id}, port: {self.port}")

    def download_pieces(
        self,
        file_hash,
        total_pieces,
        source_node_ip_address,
        source_node_port,
        save_location,
    ):
        pieces = [None] * total_pieces  # Initialize a list to store the pieces
        for i in range(total_pieces):
            piece_data = self.request_piece(
                source_node_ip_address, source_node_port, file_hash, i
            )
            if piece_data:
                pieces[i] = piece_data
            else:
                print(f"Piece {i} not found or failed to download.")
                return

        # Write all pieces to the output file
        with open(save_location, "wb") as output_file:
            for piece in pieces:
                output_file.write(piece)

        print(f"File downloaded successfully to {save_location}")

    def request_piece(self, target_ip, target_port, file_hash, piece_index):
        """Request a file piece from another node."""
        data = {
            "command": "download_piece",
            "file_hash": file_hash,
            "piece_index": piece_index,
        }
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((target_ip, target_port))
                s.sendall(json.dumps(data).encode(FORMAT))

                # Receive data in chunks until the complete response is received
                response = b""
                while True:
                    chunk = s.recv(SIZE)
                    if not chunk:
                        break
                    response += chunk

                # print(f"Received raw response: {response}")  # Log the raw response
                response_data = json.loads(response.decode(FORMAT))
                if response_data["status"] == "success":
                    piece_data = bytes.fromhex(
                        response_data["piece_data"]
                    )  # Convert hex string back to binary
                    return piece_data
                else:
                    print(f"Error: {response_data['message']}")
                    return None
        except ConnectionResetError:
            print(
                f"Connection reset by peer when requesting piece {
                    piece_index} from {target_ip}:{target_port}"
            )
            return None
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
            # print(
            # f"Received raw response: {response}"
            # )  # Log the raw response again for debugging
            return None
        except Exception as e:
            print(
                f"Error requesting piece {piece_index} from {
                    target_ip}:{target_port} - {e}"
            )
            return None

    def send_piece(self, request, client_socket):
        """Send a file piece to another node."""
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
                "piece_data": piece_data.hex(),  # Convert binary data to hex string
            }
        else:
            response = {"status": "error", "message": "Piece not found"}
        client_socket.send(json.dumps(response).encode(FORMAT))

    def run(self):
        self.register_with_tracker()
        threading.Thread(target=self.node_start).start()
        time.sleep(1)
        while True:
            print("----------------------------")
            print("|   Choose an option       |")
            print("|  1. Upload file          |")
            print("|  2. Download file        |")
            print("|  3. Exit                 |")
            print("----------------------------")
            choice = input("Enter options: ")

            if choice == "1":
                file_path = input("Enter the path of the file to upload: ")
                file_name = input("Enter the name of the file to upload: ")
                print("-------------------------------------------")
                threading.Thread(
                    target=self.upload_file,
                    args=(file_path, file_name),
                ).start()
            elif choice == "2":
                file_name = input("Enter the name of the file you want: ")
                print("-------------------------------------------")
                threading.Thread(
                    target=self.download_file,
                    args=(file_name,),
                ).start()
            elif choice == "3":
                print("Exiting...")
                self.running = False
                break
            else:
                print("Invalid option. Please choose a valid option.")

            time.sleep(2.5)


if __name__ == "__main__":
    # Example usage
    node = Node("10.128.86.17", 3000)
    node.run()
