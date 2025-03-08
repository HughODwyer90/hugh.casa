import base64
import requests
import time
import os

class GitHubUploader:
    """A class to manage file uploads to a GitHub repository."""

    def __init__(self, github_token, repo_name, branch="main", max_retries=3):
        """
        Initialize the uploader with authentication and repository details.

        :param github_token: GitHub personal access token.
        :param repo_name: Repository name (e.g., "username/repo").
        :param branch: Target branch for the uploads (default: "main").
        :param max_retries: Number of retry attempts for failed uploads.
        """
        self.github_token = github_token
        self.repo_name = repo_name
        self.branch = branch
        self.max_retries = max_retries
        self.base_api_url = f"https://api.github.com/repos/{self.repo_name}/contents"
        self.headers = {"Authorization": f"token {self.github_token}"}

    def _get_file_sha(self, github_file_path):
        """Retrieve the SHA of the file in the repository (if it exists)."""
        try:
            response = requests.get(f"{self.base_api_url}/{github_file_path}", headers=self.headers)
            print(f"Checking SHA for {github_file_path}, Status Code: {response.status_code}")
            if response.status_code == 200:
                sha = response.json().get("sha")
                print(f"Existing SHA: {sha}")  # Debugging
                return sha
            elif response.status_code == 404:
                print(f"No existing file found at {github_file_path}")
                return None  # File does not exist
            else:
                response.raise_for_status()
        except requests.RequestException as e:
            print(f"Failed to fetch SHA for {github_file_path}: {e}")
            return None  # Treat as a missing file

    def upload_file(self, local_file_path=None, content=None, github_file_path=None, commit_message=None):
        """
        Upload or update a file in the repository.
        
        - If `local_file_path` is provided, it reads the file.
        - If `content` is provided, it uploads directly.
        - Handles both **text and binary** files properly.
        """
        if not github_file_path:
            print("❌ Skipping upload: No GitHub file path provided.")
            return

        # ✅ Read file **only if** no direct content is provided
        if local_file_path and os.path.exists(local_file_path):
            is_binary = local_file_path.endswith((".png", ".jpg", ".jpeg", ".gif", ".ico"))

            with open(local_file_path, "rb" if is_binary else "r", encoding=None if is_binary else "utf-8") as file:
                content = file.read()

        if content is None:
            print(f"❌ Skipping {github_file_path}: No content provided.")
            return

        for attempt in range(self.max_retries):
            try:
                # ✅ Convert binary to Base64, and keep text as UTF-8
                encoded_content = base64.b64encode(content if isinstance(content, bytes) else content.encode("utf-8")).decode("utf-8")

                # Get the SHA if the file already exists
                sha = self._get_file_sha(github_file_path)

                # Prepare API request
                data = {
                    "message": commit_message or f"Update {os.path.basename(github_file_path)}",
                    "content": encoded_content,
                    "branch": self.branch,
                }
                if sha:
                    data["sha"] = sha  # Include SHA to overwrite the file

                # Upload to GitHub
                response = requests.put(f"{self.base_api_url}/{github_file_path}", headers=self.headers, json=data)
                response.raise_for_status()

                print(f"✅ File uploaded successfully: {github_file_path}")
                return  # ✅ Stop retrying if successful

            except requests.RequestException as e:
                print(f"❌ Attempt {attempt + 1} failed for {github_file_path}: {e}")
                if attempt < self.max_retries - 1:
                    print("Retrying in 5 seconds...")
                    time.sleep(5)
                else:
                    print(f"❌ All attempts failed for {github_file_path}. Skipping.")



    def upload_content(self, github_file_path, content, commit_message=None, is_binary=False):
        """
        Upload or update a file in the repository **directly from memory**.

        :param github_file_path: Path in the repository where the file will be uploaded.
        :param content: The content to upload (str for text files, bytes for binary files).
        :param commit_message: Commit message for the upload.
        :param is_binary: Boolean flag to indicate if the content is binary.
        """
        for attempt in range(self.max_retries):
            try:
                # Determine encoding
                if isinstance(content, bytes) or is_binary:
                    encoded_content = base64.b64encode(content).decode("utf-8")  # Encode binary
                else:
                    encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")  # Encode text

                # Get the SHA if the file already exists
                sha = self._get_file_sha(github_file_path)

                # Prepare the data for the API request
                data = {
                    "message": commit_message or f"Update {github_file_path}",
                    "content": encoded_content,
                    "branch": self.branch,
                }
                if sha:
                    data["sha"] = sha  # Include SHA to overwrite the file

                # Make the API request to upload/update the file
                response = requests.put(f"{self.base_api_url}/{github_file_path}", headers=self.headers, json=data)
                response.raise_for_status()

                print(f"✅ File uploaded successfully: {github_file_path}")
                return  # Stop retrying if successful

            except requests.RequestException as e:
                print(f"❌ Attempt {attempt + 1} failed for {github_file_path}: {e}")
                if attempt < self.max_retries - 1:
                    print("Retrying in 5 seconds...")
                    time.sleep(5)
                else:
                    print(f"❌ All attempts failed for {github_file_path}. Skipping.")
