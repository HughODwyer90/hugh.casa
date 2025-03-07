document.addEventListener("DOMContentLoaded", () => {
    function loadContent(filename) {
        if (!filename) {
            console.error("Error: filename is null or undefined.");
            return;
        }

        const iframe = document.getElementById("content-frame");

        if (filename.endsWith(".yaml.html")) {
            fetch(filename)
                .then(response => response.text())
                .then(text => {
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
            iframe.src = filename;
        }
    }

    // Set default content
    loadContent("entities.html");

    // Ensure all menu links update correctly
    document.querySelectorAll("nav ul li a").forEach((link) => {
        link.addEventListener("click", (event) => {
            event.preventDefault();
            const file = link.getAttribute("href");
            if (file) loadContent(file);
        });
    });

    // Handle dropdown button click
    document.querySelectorAll(".dropbtn").forEach((button) => {
        button.addEventListener("click", (event) => {
            event.stopPropagation();
            const dropdownContent = button.nextElementSibling;
            dropdownContent.style.display =
                dropdownContent.style.display === "block" ? "none" : "block";
        });
    });

    // Close the dropdown when clicking outside (but not when clicking inside)
    document.addEventListener("click", (event) => {
        document.querySelectorAll(".dropdown-content").forEach((dropdown) => {
            if (!dropdown.contains(event.target) && !dropdown.previousElementSibling.contains(event.target)) {
                dropdown.style.display = "none";
            }
        });
    });
});
