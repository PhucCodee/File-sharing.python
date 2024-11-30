import os
import socket
import threading
import json
import base64
import time

from function import generate_file_hash, create_magnet_link

FORMAT = "utf-8"
SIZE = 4096


class Node:
    def __init__(self, tracker_host, tracker_port, node_port):
        self.tracker_host = tracker_host
        self.tracker_port = tracker_port
        self.port = node_port
        self.ip_address = self.get_ip_address()
        self.node_id = None  # Node ID will be assigned by the tracker
        self.file_directory = None  # Will be set after registration
        self.file_list = self.get_files()

    def get_ip_address(self):
        # Get the IP address of the node
        hostname = socket.gethostname()
        return socket.gethostbyname(hostname)

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

            self.file_directory = os.path.join(
                os.path.dirname(__file__), f"node{self.node_id}_directory"
            )
            if not os.path.exists(self.file_directory):
                os.makedirs(self.file_directory)
            self.file_list = self.get_files()

            print(f"Registered with tracker, node ID: {self.node_id}")
        else:
            print("Failed to register with tracker:", response["message"])

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

        for index, piece in pieces:
            self.save_piece(file_hash, index, piece)

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

    def divide_file(self, file_path):
        pieces = []
        with open(file_path, "rb") as f:
            chunk_number = 0
            while chunk := f.read(SIZE):
                pieces.append((chunk_number, chunk))
                chunk_number += 1
        return pieces

    def save_piece(self, file_hash, index, piece):
        pieces_dir = os.path.join(self.file_directory, file_hash)
        os.makedirs(pieces_dir, exist_ok=True)

        piece_path = os.path.join(pieces_dir, f"piece_{index}")
        with open(piece_path, "wb") as piece_file:
            piece_file.write(piece)

        print(f"Piece {index} saved successfully!")

    # Downloading file
    def download_file(self, file_name):
        data = {
            "command": "download",
            "file_name": file_name,
        }
        response = self.send_request(data)
        if response["status"] == "success":
            magnet_link = response["magnet_link"]
            file_hash = response["file_hash"]
            total_pieces = response["total_pieces"]
            source_node_id = response["node_id"]
            print(f"Magnet link: {magnet_link}")
            # print(f"File hash: {file_hash}")
            # print(f"Total pieces: {total_pieces}")
            print(f"Source node: {source_node_id}")

            save_location = os.path.join(self.file_directory, file_hash)
            self.download_pieces(file_hash, total_pieces, source_node_id, save_location)
        else:
            print(f"Failed to download file {file_name}: {response['message']}")

    def download_pieces(self, file_hash, total_pieces, source_node_id, save_location):
        source_directory = f"node{source_node_id}_directory"
        pieces_dir = os.path.join(source_directory, file_hash)
        if not os.path.exists(pieces_dir):
            print(f"Pieces directory {pieces_dir} does not exist.")
            return

        with open(save_location, "wb") as output_file:
            for i in range(total_pieces):
                piece_path = os.path.join(pieces_dir, f"piece_{i}")
                if os.path.exists(piece_path):
                    with open(piece_path, "rb") as piece_file:
                        output_file.write(piece_file.read())
                else:
                    print(f"Piece {i} not found in {pieces_dir}.")
                    return

        print(f"File downloaded successfully to {save_location}")

    def run(self):
        self.register_with_tracker()
        while True:
            print(f"Welcome node {self.node_id}!")
            print("------------------------------")
            print("|  Choose an option          |")
            print("|  1. Upload file            |")
            print("|  2. Download file          |")
            print("|  3. Exit                   |")
            print("------------------------------")
            choice = input("Enter command: ")

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

            time.sleep(2)


if __name__ == "__main__":
    # Example usage
    node = Node("127.0.0.1", 3000, 5000)
    node.run()
