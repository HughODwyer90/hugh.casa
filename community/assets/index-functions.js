document.addEventListener('DOMContentLoaded', () => {
    function loadContent(filename) {
        const iframe = document.getElementById("content-frame");
    
        if (filename.endsWith(".yaml")) {
            // Fetch and display YAML content as text
            fetch(filename)
                .then(response => response.text())
                .then(text => {
                    // Replace iframe content with formatted YAML
                    iframe.srcdoc = `<pre style="
                        white-space: pre-wrap;
                        font-family: monospace;
                        padding: 10px;
                        background-color: #222;
                        color: #ddd;
                        border-radius: 5px;
                        overflow-x: auto;
                        height: 100vh;
                    ">${text}</pre>`;
                })
                .catch(error => console.error("Error loading YAML file:", error));
        } else {
            // Restore the iframe to normal behavior
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
