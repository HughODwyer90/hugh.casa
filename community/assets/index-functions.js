document.addEventListener("DOMContentLoaded", () => {
    function loadContent(filename) {
        if (!filename) {
            console.error("Error: filename is null or undefined.");
            return;
        }

        const iframe = document.getElementById("content-frame");

        // ✅ Dynamically adjust path based on current location
        const basePath = window.location.pathname.includes("/yaml_previews/") ? "../" : "";

        // ✅ If switching **from a YAML preview** back to a normal page, force a full navigation
        if (iframe.src.includes("/yaml_previews/") && !filename.includes("/yaml_previews/")) {
            window.location.href = basePath + filename;
            return;
        }

        // ✅ Properly handle YAML file display
        if (filename.includes("/yaml_previews/")) {
            fetch(basePath + filename)
                .then(response => response.text())
                .then(text => {
                    iframe.srcdoc = `<pre class="yaml-content">${text}</pre>`;
                })
                .catch(error => console.error("Error loading YAML file:", error));
        } else {
            iframe.src = basePath + filename;
        }
    }

    // ✅ Attach event listeners for ALL navbar links (including YAML)
    document.querySelectorAll(".nav-link, .yaml-link").forEach((link) => {
        link.addEventListener("click", (event) => {
            event.preventDefault();
            const file = link.dataset.file;
            if (file) {
                loadContent(file);
            }
        });
    });

    // ✅ Ensure dropdown opens and closes correctly (works for multiple dropdowns)
    document.querySelectorAll(".dropbtn").forEach((button) => {
        button.addEventListener("click", (event) => {
            event.stopPropagation();
            const dropdownContent = button.nextElementSibling;
            dropdownContent.classList.toggle("show-dropdown");
        });
    });

    // ✅ Close dropdown when clicking outside
    document.addEventListener("click", (event) => {
        document.querySelectorAll(".dropdown-content").forEach((dropdown) => {
            if (!dropdown.contains(event.target) && !dropdown.previousElementSibling.contains(event.target)) {
                dropdown.classList.remove("show-dropdown");
            }
        });
    });

    // ✅ Set default content (Ensures correct path resolution)
    const defaultPage = window.location.pathname.includes("/yaml_previews/") ? "../entities.html" : "entities.html";
    const iframe = document.getElementById("content-frame");
    if (iframe) {
        loadContent(defaultPage);
    }
});
