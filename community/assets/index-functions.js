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
                    iframe.srcdoc = `<pre class="yaml-content">${text}</pre>`;
                })
                .catch(error => console.error("Error loading YAML file:", error));
        } else {
            iframe.src = filename;
        }
    }

    // ✅ Attach event listeners for all navbar and dropdown links
    document.querySelectorAll("nav ul li a, .dropdown-content a").forEach((link) => {
        link.addEventListener("click", (event) => {
            event.preventDefault();

            // ✅ Extract filename from href instead of onclick
            const file = link.getAttribute("href");
            if (file) {
                loadContent(file);
            } else {
                console.error("Error: href is missing on the link.");
            }
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
