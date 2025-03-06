document.addEventListener('DOMContentLoaded', () => {
    function loadContent(filename) {
        const iframe = document.getElementById("content-frame");
    
        if (filename.endsWith(".yaml")) {
            // Show the YAML file as plain text
            fetch(filename)
                .then(response => response.text())
                .then(text => {
                    iframe.srcdoc = `<pre style="white-space: pre-wrap; font-family: monospace; padding: 10px;">${text}</pre>`;
                })
                .catch(error => console.error("Error loading YAML file:", error));
        } else {
            // Load HTML files normally
            iframe.src = filename;
        }
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
