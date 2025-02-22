document.addEventListener('DOMContentLoaded', () => {
    function loadContent(file) {
        document.getElementById('content-frame').src = file;
        let downloadLink = document.getElementById('download-btn');
        
        if (file.endsWith(".html")) {
            downloadLink.href = file.replace('.html', '.json');
            downloadLink.download = file.replace('.html', '.json');
        } else if (file.endsWith(".yaml")) {
            downloadLink.href = file;
            downloadLink.download = file;
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
