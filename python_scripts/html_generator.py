class HTMLGenerator:
    """A class to generate various types of HTML content."""

    @staticmethod
    def generate_index_html(html_files, yaml_files):
        """Generate the index HTML with links to HTML and YAML files."""
        if not html_files:
            raise ValueError("No HTML files found in the directory.")

        html_files = sorted(html_files)
        yaml_files = sorted(yaml_files)

        navbar_links = ''.join(
            [f'<li><a href="#" onclick="loadContent(\'{file}\')">{file.replace(".html", "").title()}</a></li>' for file in html_files]
        )
        navbar_links += ''.join(
            [f'<li><a href="#" onclick="loadContent(\'{file}\')">{file.replace(".yaml", "").title()}</a></li>' for file in yaml_files]
        )

        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>File Dashboard</title>
            <link rel="stylesheet" href="/assets/table-styles.css">
            <script defer src="/assets/table-functions.js"></script>
            <script>
                function loadContent(file) {{
                    document.getElementById('content-frame').src = file;
                    let downloadLink = document.getElementById('download-btn');
                    if (file.endsWith(".html")) {{
                        downloadLink.href = file.replace('.html', '.json');
                        downloadLink.download = file.replace('.html', '.json');
                    }} else if (file.endsWith(".yaml")) {{
                        downloadLink.href = file;
                        downloadLink.download = file;
                    }}
                }}
                document.addEventListener('DOMContentLoaded', () => {{
                    loadContent('{html_files[0]}'); // Default content
                }});
            </script>
        </head>
        <body>
            <nav>
                <ul>{navbar_links}</ul>
                <a id="download-btn" class="download-btn" href="#" download="">Download File</a>
            </nav>
            <iframe id="content-frame" src=""></iframe>
        </body>
        </html>
        """

    @staticmethod
    def generate_entities_html(entities, total_entities, version, prefixes, hidden_entities):
        """Generate HTML for Home Assistant entities."""
        filters = ''.join(f'<div id="filter-{prefix}" class="filter">{prefix}</div>' for prefix in prefixes)
        rows = ''.join(f"""
            <tr>
                <td>{entity['entity_id']}</td>
                <td>{entity['attributes'].get('friendly_name', 'N/A')}</td>
                <td>{entity['attributes'].get('unit_of_measurement', 'N/A')}</td>
                <td>{"on, off" if entity['state'] in ['on', 'off'] else "N/A"}</td>
                <td>{"Yes" if entity.get('state', 'unavailable') != 'unavailable' else "No"}</td>
            </tr>
        """ for entity in sorted(entities, key=lambda x: x['entity_id']))

        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Home Assistant Entities</title>
            <link rel="stylesheet" href="/assets/table-styles.css">
            <script defer src="/assets/table-functions.js"></script>
        </head>
        <body>
            <h1>Home Assistant Entities</h1>
            <p>Total Entities: {total_entities} (Hidden: {hidden_entities})</p>
            <p>Version: {version}</p>
            <input type="text" id="searchBox" placeholder="Search entities..." />
            <div class="filters">
                <div id="filter-All" class="filter active">All</div>
                {filters}
            </div>
            <table id="entitiesTable">
                <thead>
                    <tr>
                        <th>Entity</th>
                        <th>Friendly Name</th>
                        <th>Unit of Measurement</th>
                        <th>Acceptable Values</th>
                        <th>Enabled</th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
        </body>
        </html>
        """

    @staticmethod
    def generate_integrations_html(integrations_data, total_entries, version):
        """Generate HTML for Home Assistant integrations."""
        prefixes = sorted({integration.get('Integration ID', '')[0].upper() for integration in integrations_data if integration.get('Integration ID', '')})
        filters = ''.join(f'<button id="filter-{prefix}" class="filter">{prefix}</button>' for prefix in prefixes)
        rows = ''.join(f"""
            <tr>
                <td>{integration.get('Integration ID', 'N/A')}</td>
                <td>{integration.get('Config Entry ID', 'N/A')}</td>
                <td>{integration.get('Title', 'N/A')}</td>
                <td>{integration.get('State', 'N/A')}</td>
                <td>{integration.get('Source', 'N/A')}</td>
            </tr>
        """ for integration in integrations_data)

        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Home Assistant Integrations</title>
            <link rel="stylesheet" href="/assets/table-styles.css">
            <script defer src="/assets/table-functions.js"></script>
        </head>
        <body>
            <h1>Home Assistant Integrations</h1>
            <p>Total Integrations: {total_entries}</p>
            <p>Version: {version}</p>
            <input type="text" id="searchBox" placeholder="Search integrations..." />
            <div class="filters">
                <button id="filter-All" class="filter active">All</button>
                {filters}
            </div>
            <table id="integrationsTable">
                <thead>
                    <tr>
                        <th>Integration ID</th>
                        <th>Config Entry ID</th>
                        <th>Title</th>
                        <th>State</th>
                        <th>Source</th>
                    </tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
        </body>
        </html>
        """
