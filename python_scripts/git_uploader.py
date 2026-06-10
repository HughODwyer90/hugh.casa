import base64
import requests
import time
import os

class GitHubUploader:
    """A class to manage file uploads to a GitHub repository."""

    def __init__(self, github_token, repo_name, branch="main", max_retries=3):
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
                print(f"Existing SHA: {sha}")
                return sha
            elif response.status_code == 404:
                print(f"No existing file found at {github_file_path}")
                return None
            else:
                response.raise_for_status()
        except requests.RequestException as e:
            print(f"Failed to fetch SHA for {github_file_path}: {e}")
            return None

    def upload_file(self, local_file_path=None, content=None, github_file_path=None, commit_message=None):
        if not github_file_path:
            print("❌ Skipping upload: No GitHub file path provided.")
            return

        if local_file_path and os.path.exists(local_file_path):
            is_binary = local_file_path.endswith((".png", ".jpg", ".jpeg", ".gif", ".ico"))
            with open(local_file_path, "rb" if is_binary else "r", encoding=None if is_binary else "utf-8") as file:
                content = file.read()

        if content is None:
            print(f"❌ Skipping {github_file_path}: No content provided.")
            return

        for attempt in range(self.max_retries):
            try:
                encoded_content = base64.b64encode(
                    content if isinstance(content, bytes) else content.encode("utf-8")
                ).decode("utf-8")

                sha = self._get_file_sha(github_file_path)

                data = {
                    "message": commit_message or f"Update {os.path.basename(github_file_path)}",
                    "content": encoded_content,
                    "branch": self.branch,
                }
                if sha:
                    data["sha"] = sha

                response = requests.put(
                    f"{self.base_api_url}/{github_file_path}",
                    headers=self.headers,
                    json=data
                )
                response.raise_for_status()

                print(f"✅ File uploaded successfully: {github_file_path}")
                return

            except requests.RequestException as e:
                print(f"❌ Attempt {attempt + 1} failed for {github_file_path}: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    print(f"Response body: {e.response.text}")
                if attempt < self.max_retries - 1:
                    print("Retrying in 5 seconds...")
                    time.sleep(5)
                else:
                    print(f"❌ All attempts failed for {github_file_path}. Skipping.")

    def upload_content(self, github_file_path, content, commit_message=None, is_binary=False):
        for attempt in range(self.max_retries):
            try:
                if isinstance(content, bytes) or is_binary:
                    encoded_content = base64.b64encode(content).decode("utf-8")
                else:
                    encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")

                sha = self._get_file_sha(github_file_path)

                data = {
                    "message": commit_message or f"Update {github_file_path}",
                    "content": encoded_content,
                    "branch": self.branch,
                }
                if sha:
                    data["sha"] = sha

                response = requests.put(
                    f"{self.base_api_url}/{github_file_path}",
                    headers=self.headers,
                    json=data
                )
                response.raise_for_status()

                print(f"✅ File uploaded successfully: {github_file_path}")
                return

            except requests.RequestException as e:
                print(f"❌ Attempt {attempt + 1} failed for {github_file_path}: {e}")
                if hasattr(e, 'response') and e.response is not None:
                    print(f"Response body: {e.response.text}")
                if attempt < self.max_retries - 1:
                    print("Retrying in 5 seconds...")
                    time.sleep(5)
                else:
                    print(f"❌ All attempts failed for {github_file_path}. Skipping.")