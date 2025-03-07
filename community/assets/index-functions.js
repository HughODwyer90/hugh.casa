document.addEventListener("DOMContentLoaded", () => {
    function loadContent(filename) {
        if (!filename) {
            console.error("Error: filename is null or undefined.");
            return;
        }

        const iframe = document.getElementById("content-frame");

        // ✅ Correctly handle YAML file display
        if (filename.endsWith(".yaml")) {
            fetch(filename)
                .then(response => response.text())
                .then(text => {
                    iframe.srcdoc = `<pre class="yaml-content">${text}</pre>`;
                })
                .catch(error => console.error("Error loading YAML file:", error));
        } else {
            iframe.src = filename;
        }
    }

    // ✅ Attach event listeners for ALL navbar links (including YAML)
    document.querySelectorAll("nav ul li a").forEach((link) => {
        link.addEventListener("click", (event) => {
            event.preventDefault();
            const file = link.getAttribute("onclick").match(/'([^']+)'/)[1];
            loadContent(file);
        });
    });
});
