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

    // ✅ Attach event listeners for ALL navbar links
    document.querySelectorAll("nav ul li a, .yaml-link").forEach((link) => {
        link.addEventListener("click", (event) => {
            event.preventDefault();
            const file = link.dataset.file; // ✅ Get the filename from data attribute
            if (file) {
                loadContent(file);
            }
        });
    });

    // ✅ Ensure dropdown opens and closes correctly
    document.querySelector(".dropbtn").addEventListener("click", (event) => {
        event.stopPropagation();
        const dropdownContent = document.querySelector(".dropdown-content");
        dropdownContent.classList.toggle("show-dropdown");
    });

    // ✅ Close dropdown when clicking outside
    document.addEventListener("click", (event) => {
        const dropdownContent = document.querySelector(".dropdown-content");
        if (!dropdownContent.contains(event.target) && !document.querySelector(".dropbtn").contains(event.target)) {
            dropdownContent.classList.remove("show-dropdown");
        }
    });

    // ✅ Set default content
    const iframe = document.getElementById("content-frame");
    if (iframe) {
        loadContent("entities.html");
    }
});
