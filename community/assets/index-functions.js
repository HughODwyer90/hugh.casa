document.addEventListener("DOMContentLoaded", () => {
    function loadContent(filename) {
        if (!filename) {
            console.error("Error: filename is null or undefined.");
            return;
        }

        const iframe = document.getElementById("content-frame");

        // ✅ If currently viewing a YAML file, reset srcdoc before loading new content
        if (iframe.srcdoc !== "" && !filename.includes("/yaml_previews/")) {
            iframe.srcdoc = "";
            iframe.src = filename;
            return;
        }

        // ✅ Load YAML files correctly inside iframe
        if (filename.includes("/yaml_previews/")) {
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
    document.querySelectorAll(".nav-link, .yaml-link").forEach((link) => {
        link.addEventListener("click", (event) => {
            event.preventDefault();
            const file = link.dataset.file;
            if (file) {
                loadContent(file);
            }
        });
    });

    // ✅ Ensure dropdown opens and closes correctly
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

    // ✅ Handle direct URL navigation (e.g., index.html?load=integrations.html)
    const urlParams = new URLSearchParams(window.location.search);
    const pageToLoad = urlParams.get("load") || "community/entities.html";  // ✅ Default to Entities

    const iframe = document.getElementById("content-frame");
    if (iframe) {
        loadContent(pageToLoad);
    }
});
