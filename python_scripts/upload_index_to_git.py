<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>File Dashboard</title>
    <link rel="stylesheet" href="assets/table-styles.css">
    <script>
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
        document.addEventListener('DOMContentLoaded', () => {
            loadContent('entities.html'); // Default content
        });
    </script>
</head>
<body>
    <nav>
        <ul>
            <li><a href="#" onclick="loadContent('entities.html')">Entities</a></li>
            <li><a href="#" onclick="loadContent('integrations.html')">Integrations</a></li>
            <li><a href="#" onclick="loadContent('automations.yaml')">Automations</a></li>
            <li><a href="#" onclick="loadContent('configuration.yaml')">Configuration</a></li>
            <li><a href="#" onclick="loadContent('custom_command.yaml')">Custom_Command</a></li>
            <li><a href="#" onclick="loadContent('custom_sensor.yaml')">Custom_Sensor</a></li>
            <li><a href="#" onclick="loadContent('notifications.yaml')">Notifications</a></li>
            <li><a href="#" onclick="loadContent('scenes.yaml')">Scenes</a></li>
            <li><a href="#" onclick="loadContent('scripts.yaml')">Scripts</a></li>
            <li><a href="#" onclick="loadContent('shell_commands.yaml')">Shell_Commands</a></li>
        </ul>
        <a id="download-btn" class="download-btn" href="#" download="">Download File</a>
    </nav>
    <iframe id="content-frame" src="" style="width: 100%; height: calc(100vh - 50px); border: none;"></iframe>
</body>
</html>
