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
    document.querySelectorAll("nav ul li a, .yaml-link").forEach((link) => {
        link.addEventListener("click", (event) => {
            event.preventDefault();
            const file = link.getAttribute("onclick").match(/'([^']+)'/)[1];
            loadContent(file);
        });
    });

    // ✅ Ensure dropdown opens and closes correctly
    document.querySelector(".dropbtn").addEventListener("click", (event) => {
        event.stopPropagation();
        const dropdownContent = event.target.nextElementSibling;
        dropdownContent.classList.toggle("show-dropdown");
    });

    // ✅ Close dropdown when clicking outside
    document.addEventListener("click", (event) => {
        document.querySelectorAll(".dropdown-content").forEach((dropdown) => {
            if (!dropdown.contains(event.target) && !dropdown.previousElementSibling.contains(event.target)) {
                dropdown.classList.remove("show-dropdown");
            }
        });
    });
});
