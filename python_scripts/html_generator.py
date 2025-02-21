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
            <style>
                body {{ font-family: Arial, sans-serif; }}
                nav {{ background-color: #333; color: white; padding: 10px; display: flex; justify-content: space-between; align-items: center; }}
                nav ul {{ list-style: none; margin: 0; padding: 0; display: flex; }}
                nav ul li {{ margin-right: 20px; }}
                nav ul li a {{ color: white; text-decoration: none; cursor: pointer; }}
                iframe {{ width: 100%; height: calc(100vh - 50px); border: none; }}
                .download-btn {{ background-color: #4CAF50; color: white; border: none; padding: 10px 20px; cursor: pointer; border-radius: 5px; }}
            </style>
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
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1 {{ text-align: center; color: #333; }}
                #searchBox {{ width: 100%; padding: 8px; margin-bottom: 12px; border: 1px solid #ccc; border-radius: 4px; }}
                .filters {{ display: flex; flex-wrap: wrap; margin-bottom: 12px; }}
                .filter {{ margin: 4px; padding: 6px 12px; border: 1px solid #ccc; border-radius: 4px; background-color: #f4f4f4; cursor: pointer; }}
                .filter.active {{ background-color: #333333; color: white; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
                th {{ background-color: #f4f4f4; cursor: pointer; }}
                tr:nth-child(even) {{ background-color: #f9f9f9; }}
                tr:hover {{ background-color: #f1f1f1; }}
            </style>
            <script>
                let currentFilter = 'All';
                document.addEventListener('DOMContentLoaded', () => {{
                    const filterButtons = document.querySelectorAll('.filter');
                    filterButtons.forEach(button => {{
                        button.addEventListener('click', () => {{
                            document.querySelectorAll('.filter.active').forEach(el => el.classList.remove('active'));
                            button.classList.add('active');
                            currentFilter = button.id.replace('filter-', '');
                            searchTable();
                        }});
                    }});
                }});
                function searchTable() {{
                    const query = document.getElementById('searchBox').value.toLowerCase();
                    const rows = document.querySelectorAll('#entitiesTable tr');
                    rows.forEach((row, index) => {{
                        if (index === 0) return;
                        const entity = row.cells[0].textContent.toLowerCase();
                        const matchFilter = currentFilter === 'All' || entity.startsWith(currentFilter.toLowerCase());
                        row.style.display = matchFilter ? '' : 'none';
                    }});
                }}
            </script>
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
        # Generate a list of unique first characters (prefixes) from Integration IDs
        prefixes = sorted({integration.get('Integration ID', '')[0].upper() for integration in integrations_data if integration.get('Integration ID', '')})

        # Create filters dynamically
        filters = ''.join(
            f'<button id="filter-{prefix}" class="filter">{prefix}</button>' for prefix in prefixes
        )

        # Create table rows dynamically, ensuring missing data is replaced with "N/A"
        rows = ''.join(f"""
            <tr>
                <td>{integration.get('Integration ID', 'N/A')}</td>
                <td>{integration.get('Config Entry ID', 'N/A')}</td>
                <td>{integration.get('Title', 'N/A')}</td>
                <td>{integration.get('State', 'N/A')}</td>
                <td>{integration.get('Source', 'N/A')}</td>
            </tr>
        """ for integration in integrations_data)

        # HTML Content
        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Home Assistant Integrations</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    margin: 20px;
                    background-color: #f9f9f9;
                }}
                h1 {{
                    text-align: center;
                    color: #333;
                }}
                #searchBox {{
                    width: 100%;
                    padding: 10px;
                    margin: 12px 0;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    font-size: 16px;
                }}
                .filters {{
                    display: flex;
                    flex-wrap: wrap;
                    margin-bottom: 12px;
                }}
                .filter {{
                    margin: 4px;
                    padding: 6px 12px;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    background-color: #f4f4f4;
                    cursor: pointer;
                }}
                .filter.active {{
                    background-color: #0056b3;
                    color: white;
                    font-weight: bold;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 20px;
                    background-color: white;
                    box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
                }}
                th, td {{
                    border: 1px solid #ccc;
                    padding: 10px;
                    text-align: left;
                }}
                th {{
                    background-color: #f8f9fa;
                    color: #333;
                }}
                tr:nth-child(even) {{
                    background-color: #f9f9f9;
                }}
                tr:hover {{
                    background-color: #e9ecef !important;
                }}
            </style>
            <script>
                document.addEventListener('DOMContentLoaded', () => {{
                    let currentFilter = 'All';

                    // Handle filter button clicks
                    const filters = document.querySelectorAll('.filter');
                    filters.forEach(filter => {{
                        filter.addEventListener('click', () => {{
                            document.querySelectorAll('.filter.active').forEach(f => f.classList.remove('active'));
                            filter.classList.add('active');
                            currentFilter = filter.textContent.trim();  // Update current filter
                            filterTable(currentFilter);
                        }});
                    }});

                    // Handle search input
                    const searchBox = document.getElementById('searchBox');
                    searchBox.addEventListener('input', () => filterTable(currentFilter));

                    // Function to filter the table
                    function filterTable(filter = 'All') {{
                        const query = searchBox.value.toLowerCase();
                        const rows = document.querySelectorAll('#integrationsTable tbody tr');
                        rows.forEach(row => {{
                            const integrationID = row.cells[0].textContent.trim();  // Get Integration ID
                            const matchesFilter = filter === 'All' || integrationID.charAt(0).toUpperCase() === filter;
                            const matchesQuery = Array.from(row.cells).some(cell => cell.textContent.toLowerCase().includes(query));
                            row.style.display = matchesFilter && matchesQuery ? '' : 'none';
                        }});
                    }}

                    // Default: Show all rows
                    filterTable('All');
                }});
            </script>
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
