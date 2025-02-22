document.addEventListener('DOMContentLoaded', () => {
    let entityFilter = 'All';
    let integrationFilter = 'All';

    function updateTableCount() {
        const iframe = document.getElementById('content-frame'); // Access the iframe
        if (!iframe || !iframe.contentDocument) return;

        const table = iframe.contentDocument.getElementById('entitiesTable');
        if (table) {
            let visibleRows = table.querySelectorAll("tbody tr:not([style*='display: none'])").length;
            document.getElementById("search-total").textContent = `Search total: ${visibleRows}`;
        }
    }

    function sortTable(tableId, columnIndex) {
        const iframe = document.getElementById('content-frame');
        if (!iframe || !iframe.contentDocument) return;

        const table = iframe.contentDocument.getElementById(tableId);
        if (!table) return;

        const tbody = table.querySelector('tbody');
        const header = table.querySelectorAll('th')[columnIndex];
        const order = header.dataset.order === 'desc' ? 'asc' : 'desc';
        header.dataset.order = order;

        const rows = Array.from(tbody.querySelectorAll('tr'));
        rows.sort((a, b) => {
            const aText = a.children[columnIndex].textContent.trim().toLowerCase();
            const bText = b.children[columnIndex].textContent.trim().toLowerCase();
            return order === 'asc' ? aText.localeCompare(bText) : bText.localeCompare(aText);
        });

        tbody.innerHTML = '';
        rows.forEach(row => tbody.appendChild(row));

        updateTableCount(); // Update count after sorting
    }

    function filterEntities() {
        const iframe = document.getElementById('content-frame');
        if (!iframe || !iframe.contentDocument) return;

        const query = document.getElementById('entitySearch')?.value.toLowerCase();
        const entityTable = iframe.contentDocument.getElementById('entitiesTable');

        if (entityTable) {
            entityTable.querySelectorAll('tbody tr').forEach(row => {
                const entityId = row.cells[0].textContent.trim().toLowerCase();
                const matchesFilter = entityFilter === 'All' || entityId.startsWith(entityFilter.toLowerCase());
                const matchesQuery = Array.from(row.cells).some(cell => cell.textContent.toLowerCase().includes(query));
                row.style.display = matchesFilter && matchesQuery ? '' : 'none';
            });

            updateTableCount(); // Update count after filtering
        }
    }

    function filterIntegrations() {
        const iframe = document.getElementById('content-frame');
        if (!iframe || !iframe.contentDocument) return;

        const query = document.getElementById('integrationSearch')?.value.toLowerCase();
        const integrationTable = iframe.contentDocument.getElementById('integrationsTable');

        if (integrationTable) {
            integrationTable.querySelectorAll('tbody tr').forEach(row => {
                const integrationId = row.cells[0].textContent.trim().toLowerCase();
                const matchesFilter = integrationFilter === 'All' || integrationId.startsWith(integrationFilter.toLowerCase());
                const matchesQuery = Array.from(row.cells).some(cell => cell.textContent.toLowerCase().includes(query));
                row.style.display = matchesFilter && matchesQuery ? '' : 'none';
            });

            updateTableCount(); // Update count after filtering
        }
    }

    // Attach event listeners for entity filters
    document.getElementById('entitySearch')?.addEventListener('input', filterEntities);
    document.querySelectorAll('.entity-filter').forEach(filter => {
        filter.addEventListener('click', () => {
            document.querySelectorAll('.entity-filter.active').forEach(f => f.classList.remove('active'));
            filter.classList.add('active');
            entityFilter = filter.textContent.trim();
            filterEntities();
        });
    });

    // Attach event listeners for integration filters
    document.getElementById('integrationSearch')?.addEventListener('input', filterIntegrations);
    document.querySelectorAll('.integration-filter').forEach(filter => {
        filter.addEventListener('click', () => {
            document.querySelectorAll('.integration-filter.active').forEach(f => f.classList.remove('active'));
            filter.classList.add('active');
            integrationFilter = filter.textContent.trim();
            filterIntegrations();
        });
    });

    // Ensure table count updates after iframe loads
    document.getElementById('content-frame').addEventListener('load', () => {
        updateTableCount();
        filterEntities();
        filterIntegrations();
    });

    // Initialize Filters
    filterEntities();
    filterIntegrations();
});
