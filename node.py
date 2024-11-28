import os
import socket
import threading
import json
import base64
import time

from function import generate_file_hash, create_magnet_link

FORMAT = "utf-8"
SIZE = 8192


class Node:
    def __init__(self, tracker_host, tracker_port):
        self.tracker_host = tracker_host
        self.tracker_port = tracker_port
        self.ip_address = self.get_ip_address()
        self.port = self.get_port()
        self.node_id = None  # Node ID will be assigned by the tracker
        self.upload_directory = None  # Will be set after registration
        self.download_directory = None
        self.uploaded_file_list = self.get_uploaded_files()
        self.downloaded_file_list = self.get_downloaded_files()

    def get_ip_address(self):
        # Get the IP address of the node
        hostname = socket.gethostname()
        return socket.gethostbyname(hostname)

    def get_port(self):
        # Create a socket and bind it to an available port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((self.ip_address, 0))  # Bind to an available port
            port = s.getsockname()[1]  # Retrieve the assigned port number
        return port

    def get_uploaded_files(self):
        # Get the list of files in the shared directory
        if self.upload_directory and os.path.exists(self.upload_directory):
            return os.listdir(self.upload_directory)
        return []

    def get_downloaded_files(self):
        # Get the list of files in the shared directory
        if self.download_directory and os.path.exists(self.download_directory):
            return os.listdir(self.download_directory)
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
        # Register the node with the tracker server
        data = {
            "command": "register",
            "ip_address": self.ip_address,
            "port": self.port,
            "uploaded_file_list": self.uploaded_file_list,
        }
        response = self.send_request(data)
        if response["status"] == "registered":
            self.node_id = response["node_id"]

            # Create upload and download directory
            self.upload_directory = os.path.join(
                os.path.dirname(__file__), f"node{self.node_id}_upload"
            )
            if not os.path.exists(self.upload_directory):
                os.makedirs(self.upload_directory)
            self.uploaded_file_list = self.get_uploaded_files()

            self.download_directory = os.path.join(
                os.path.dirname(__file__), f"node{self.node_id}_download"
            )
            if not os.path.exists(self.download_directory):
                os.makedirs(self.download_directory)
            self.downloaded_file_list = self.get_downloaded_files()

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

        self.uploaded_file_list.append(file_name)
        data = {
            "command": "upload",
            "node_id": self.node_id,
            "file_name": file_name,
            "file_hash": file_hash,
            "magnet_link": magnet_link,
            "total_pieces": len(pieces),
            "uploaded_file_list": self.uploaded_file_list,
        }
        response = self.send_request(data)
        if response["status"] == "uploaded":
            print(f"File {file_name} uploaded successfully and tracker updated.")
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
        # Define the directory to save the pieces
        pieces_dir = os.path.join(self.upload_directory, file_hash)
        os.makedirs(pieces_dir, exist_ok=True)

        # Save the piece to a file
        piece_path = os.path.join(pieces_dir, f"piece_{index}")
        with open(piece_path, "wb") as piece_file:
            piece_file.write(piece)

        print(f"Piece {index} saved successfully!")

    # Downloading file
    def download_file(self, file_name, save_location):
        data = {
            "command": "download",
            "file_name": file_name,
        }
        response = self.send_request(data)
        if response["status"] == "success":
            magnet_link = response["magnet_link"]
            file_hash = response["file_hash"]
            total_pieces = response["total_pieces"]
            print(f"Magnet link: {magnet_link}")
            print(f"File hash: {file_hash}")
            print(f"Total pieces: {total_pieces}")

            # Proceed with downloading the file using the magnet link and metadata
            self.download_pieces(file_hash, total_pieces, save_location)
        else:
            print(f"Failed to download file {file_name}: {response['message']}")

    def download_pieces(self, file_hash, total_pieces, save_location):
        pieces_dir = os.path.join(self.upload_directory, file_hash)
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
                save_location = input("Enter the location to save the file: ")
                print("-------------------------------------------")
                threading.Thread(
                    target=self.download_file,
                    args=(file_name, save_location),
                ).start()

            time.sleep(2)


if __name__ == "__main__":
    # Example usage
    node = Node("127.0.0.1", 2901)
    node.run()
    # node.register_with_tracker()
    # node.upload_file("/Users/tranhoangphuc/Downloads/test.cpp", "test.cpp")
    # time.sleep(1)
    # node.upload_file("/Users/tranhoangphuc/Downloads/test1.txt", "test1.txt")
