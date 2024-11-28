import hashlib


def generate_file_hash(file_path):
    """Generate a file hash (SHA-1) from the file content."""
    hasher = hashlib.sha1()
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):  # Read file in chunks of 8192 bytes
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        print(f"Error generating hash for {file_path}: {e}")
        return None


def create_magnet_link(file_hash, file_name):
    """Create a magnet link using the file hash and file name."""
    return f"magnet:?xt=urn:btih:{file_hash}&dn={file_name}"
