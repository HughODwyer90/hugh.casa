document.addEventListener('DOMContentLoaded', () => {
    function loadContent(file) {
        document.getElementById('content-frame').src = file;
        let downloadLink = document.getElementById('download-btn');

        // Always link to the full Git directory ZIP instead of a specific file
        let gitDownloadURL = "https://github.com/HughODwyer90/hugh.casa/archive/refs/heads/main.zip";  // GitHub repo ZIP

        // Update Download button to download the full Git repo
        downloadLink.href = gitDownloadURL;
        downloadLink.download = "hugh_casa.zip"; // Set a friendly file name for the download
    }

    // Set default content
    loadContent('entities.html');

    // Ensure all menu links update correctly
    document.querySelectorAll('nav ul li a').forEach(link => {
        link.addEventListener('click', (event) => {
            event.preventDefault();
            let file = event.target.getAttribute('onclick').match(/'([^']+)'/)[1];
            loadContent(file);
        });
    });
});
