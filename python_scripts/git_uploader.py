import os
import base64
import requests


class GitHubUploader:
    """A class to manage file uploads to a GitHub repository."""
    
    def __init__(self, github_token, repo_name, branch="main"):
        """
        Initialize the uploader with authentication and repository details.
        
        :param github_token: GitHub personal access token.
        :param repo_name: Repository name (e.g., "username/repo").
        :param branch: Target branch for the uploads (default: "main").
        """
        self.github_token = github_token
        self.repo_name = repo_name
        self.branch = branch
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


    def upload_file(self, local_file_path, github_file_path, commit_message=None):
        """
        Upload or update a file in the repository.
        
        :param local_file_path: Path to the local file to be uploaded.
        :param github_file_path: Path in the repository where the file will be uploaded.
        :param commit_message: Commit message for the upload. If not provided, a default message is used.
        """
        try:
            with open(local_file_path, "r", encoding="utf-8") as file:
                content = file.read()
            encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

            # Get the SHA if the file already exists
            sha = self._get_file_sha(github_file_path)

            # Prepare the data for the API request
            data = {
                "message": commit_message or f"Update {os.path.basename(local_file_path)}",
                "content": encoded_content,
                "branch": self.branch,
            }
            if sha:
                data["sha"] = sha  # Include SHA to overwrite the file

            # Make the API request to upload/update the file
            response = requests.put(f"{self.base_api_url}/{github_file_path}", headers=self.headers, json=data)
            response.raise_for_status()

            print(f"File uploaded successfully: {github_file_path}")
        except requests.RequestException as e:
            raise ConnectionError(f"GitHub upload failed: {e}")
        except Exception as e:
            raise Exception(f"Error uploading file to GitHub: {e}")
