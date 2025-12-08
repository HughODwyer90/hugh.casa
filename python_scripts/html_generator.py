import html
import datetime
ASSET_PATH = "assets"  # ✅ Ensure assets load correctly

class HTMLGenerator:
    """A class to generate various types of HTML content."""

    @staticmethod
    def generate_index_html(html_files, yaml_files):
        """Generate the index HTML with a YAML dropdown and working links."""
        if not html_files:
            raise ValueError("No HTML files found in the directory.")

        html_files = sorted(html_files)
        yaml_files = sorted(yaml_files)

        # ✅ Generate navbar links for **actual HTML files** (excluding YAML previews)
        navbar_links = ''.join(
            f'<li><a href="#" class="nav-link" data-file="{file}">{file.replace(".html", "").title()}</a></li>'
            for file in html_files if not file.endswith(".yaml.html")
        )

        # ✅ Generate dropdown for YAML previews
        yaml_dropdown = ''.join(
            f'<a href="#" class="yaml-link" data-file="{file}">'  # ✅ Correct `data-file` path
            + (
                file.replace("yaml_previews/", "")  # ✅ Remove folder prefix
                    .replace(".yaml.html", "")  # ✅ Remove file extension
                    .replace("_", " ")  # ✅ Convert underscores to spaces
                    .title()  # ✅ Capitalize properly
                    .replace("Ir ", "IR ")  # ✅ Ensure "IR Receiver" remains correct
                    .replace("Ip ", "IP ")
                    .replace("Espn ", "ESPN ")
            )
            + '</a>'
            for file in yaml_files
        )

        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <meta http-equiv="X-Content-Type-Options" content="nosniff">
            <meta name="referrer" content="no-referrer-when-downgrade">
            <meta http-equiv="Permissions-Policy" content="geolocation=(), microphone=(), camera=()">
            <title>Living Backup</title>
            <link rel="stylesheet" href="{ASSET_PATH}/index-styles.css">
            <link rel="icon" type="image/x-icon" href="{ASSET_PATH}/favicon.ico">
        </head>
        <body>
            <nav>
                <ul>
                    {navbar_links}
                    <li class="dropdown">
                        <a href="#" class="dropbtn">YAML ▾</a>
                        <div class="dropdown-content">
                            {yaml_dropdown}
                        </div>
                    </li>
                </ul>
                <a id="download-btn" class="download-btn" href="https://github.com/HughODwyer90/hugh.casa/archive/refs/heads/main.zip" download>
                    Download ZIP
                </a>
            </nav>
            <iframe id="content-frame" src="entities.html"></iframe>
            <script defer src="{ASSET_PATH}/index-functions.js"></script>
        </body>
        </html>
        """

    @staticmethod
    def generate_yaml_html(yaml_filename, yaml_content):
        """Generate an HTML page to display YAML content with syntax highlighting."""
        formatted_yaml = html.escape(yaml_content)

        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{yaml_filename}</title>
            <link rel="stylesheet" id="dynamic-styles">
            <link rel="icon" id="dynamic-favicon">
        </head>
        <body>
            <div class="fixed-header">
                <h1>Viewing: {yaml_filename}</h1>
            </div>
            <div class="scrollable-content">
                <pre class="yaml-content">{formatted_yaml}</pre>
            </div>
            <script>
                (function fixPaths() {{
                    // ✅ If inside yaml_previews, use "../assets/", otherwise use "assets/"
                    var basePath = window.location.pathname.includes("/yaml_previews/") ? "../assets/" : "assets/";

                    // ✅ Apply correct asset paths
                    document.getElementById("dynamic-styles").href = basePath + "table-styles.css";
                    document.getElementById("dynamic-favicon").href = basePath + "favicon.ico";

                    var script = document.createElement("script");
                    script.src = basePath + "table-functions.js";
                    document.body.appendChild(script);
                }})();
            </script>
        </body>
        </html>
        """


    @staticmethod
    def generate_entities_html(entities, total_entities, version, prefixes, redacted_entities):

        def format_state(state):
            """Format state if it's a valid ISO 8601 datetime, otherwise return as is."""
            if isinstance(state, str):
                try:
                    return datetime.datetime.fromisoformat(state).strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass  # If parsing fails, return the original state
            return state

        """Generate HTML for Home Assistant entities."""
        prefixes = sorted(set(entity["entity_id"].split(".")[0] for entity in entities))
        filters = ''.join(f'<div id="filter-{prefix}" class="filter entity-filter">{prefix}</div>' for prefix in prefixes)

        rows = ''.join(f"""
            <tr>
                <td>{entity['entity_id']}</td>
                <td>{entity['attributes'].get('friendly_name', 'N/A')}</td>
                <td>{entity['attributes'].get('unit_of_measurement', 'N/A')}</td>
                <td>{format_state(entity['state'])}</td>
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
            <link rel="stylesheet" href="{ASSET_PATH}/table-styles.css">
            <link rel="icon" type="image/x-icon" href="{ASSET_PATH}/favicon.ico">
        </head>
        <body>
            <div class="fixed-header">
                <h1>Home Assistant Entities</h1>
                <p>Total Entities: {total_entities} (Redacted: {redacted_entities})</p>
                <p>Version: {version}</p>
                <div class="search-container">
                    <input type="text" id="entitySearch" class="search-box" placeholder="🔍 Search entities...">
                </div>
                <div>
                    <p id="table-count">Search total: {total_entities}</p>
                </div>
                <div class="filters">
                    <div id="filter-All" class="filter entity-filter active">All</div>
                    {filters}
                </div>
            </div>
            <div class="scrollable-content">
                <table id="entitiesTable">
                    <thead>
                        <tr>
                            <th>Entity</th>
                            <th>Friendly Name</th>
                            <th>Unit of Measurement</th>
                            <th>State (ToU)</th>
                            <th>Enabled</th>
                        </tr>
                    </thead>
                    <tbody>{rows}</tbody>
                </table>
            </div>
            <script defer src="{ASSET_PATH}/table-functions.js"></script>
        </body>
        </html>
        """

    @staticmethod
    def generate_integrations_html(integrations_data, total_entries, version):
        """Generate HTML for Home Assistant integrations."""
        prefixes = sorted(set(integration.get('domain', '') for integration in integrations_data if integration.get('domain', '')))
        filters = ''.join(f'<div id="filter-{prefix}" class="filter integration-filter">{prefix}</div>' for prefix in prefixes)

        rows = ''.join(f"""
            <tr>
                <td>{integration.get('domain', 'N/A')}</td>
                <td>{integration.get('entry_id', 'N/A')}</td>
                <td>{integration.get('title', 'N/A')}</td>
                <td>{integration.get('state', 'unknown')}</td>
                <td>{integration.get('source', 'unknown')}</td>
            </tr>
        """ for integration in integrations_data)

        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Home Assistant Integrations</title>
            <link rel="stylesheet" href="{ASSET_PATH}/table-styles.css">
            <link rel="icon" type="image/x-icon" href="{ASSET_PATH}/favicon.ico">
        </head>
        <body>
            <div class="fixed-header">
                <h1>Home Assistant Integrations</h1>
                <p>Total Integrations: {total_entries}</p>
                <p>Version: {version}</p>
                <div class="search-container">
                    <input type="text" id="integrationSearch" class="search-box" placeholder="🔍 Search integrations...">
                </div>
                <div>
                    <p id="table-count">Search total: {total_entries}</p>
                </div>
                <div class="filters">
                    <div id="filter-All" class="filter integration-filter active">All</div>
                    {filters}
                </div>
            </div>
            <div class="scrollable-content">
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
            </div>
            <script defer src="{ASSET_PATH}/table-functions.js"></script>
        </body>
        </html>
        """
